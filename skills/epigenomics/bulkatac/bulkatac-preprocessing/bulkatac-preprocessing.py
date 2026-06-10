#!/usr/bin/env python3
"""
bulkatac-preprocessing.py — Bulk ATAC-seq preprocessing entry point.

Current scope (Step 1)
--------------------------
  Step 1a  Load sample sheet, parse metadata, validate files
           → skills/epigenomics/_lib/preprocessing.py
  Step 1b  Raw FASTQ QC (FastQC) + adapter trimming (fastp / Trim Galore)
           → skills/epigenomics/_lib/preprocessing.py

Planned steps (not yet implemented)
--------------------------------------
  Step 2a  Alignment, BAM filtering, deduplication, downsampling
  Step 2b  Post-alignment QC (NRF/PBC1/PBC2, TSS, fragment length, bigWig)
  Step 3a  Peak calling (MACS2) + consensus peak set
  Step 3b  Post-peak QC (FRiP, IDR, reproducible peak sets)
  Step 3c  Peak annotation
  Step 4a  Differential accessibility (DESeq2)
  Step 4b  Motif enrichment / footprinting (HOMER, TOBIAS)

Use --demo to test with GSE66386 (S. cerevisiae T0 vs T15 osmotic stress, sacCer3 PE).
"""

from __future__ import annotations

import argparse
import json
import logging
import shlex
import sys
from pathlib import Path
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_SKILL_DIR    = Path(__file__).resolve().parent       # .../bulkatac-preprocessing/
_BULKATAC_DIR = _SKILL_DIR.parent                            # .../bulkatac/
_PROJECT_ROOT = _BULKATAC_DIR.parent.parent.parent           # OmicsClaw/

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkatac-preprocessing"
SKILL_VERSION = "0.1.0"
# SCRIPT_REL: path relative to project root — used in commands.sh for reproducibility
try:
    SCRIPT_REL = str(Path(__file__).resolve().relative_to(_PROJECT_ROOT))
except ValueError:
    SCRIPT_REL = "skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py"

# ---------------------------------------------------------------------------
# _lib imports
# ---------------------------------------------------------------------------
# Relocate into the omicsclaw_bulkatac sub-env before the tool-backed _lib imports.
from skills.epigenomics.bulkatac._lib.subenv_bootstrap import ensure_bulkatac_env  # noqa: E402
from skills.epigenomics.bulkatac._lib.progress import tty_write  # noqa: E402
ensure_bulkatac_env()

from skills.epigenomics.bulkatac._lib.preprocessing import (             # noqa: E402
    get_data,
    sample_sheet_to_dict,
    SampleSheet,
    run_all_preprocessing,
    build_preprocessing_summary,
    PreprocessResult,
    MIN_READ_LENGTH_AFTER_TRIM,
    BASE_QUALITY_THRESHOLD,
    NEXTERA_ADAPTER,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402


# ---------------------------------------------------------------------------
# Report + result.json
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    sheet: SampleSheet,
    preprocess_results: list[PreprocessResult],
    params: dict[str, Any],
) -> None:
    lines: list[str] = [
        "# ATAC-seq Preprocessing Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Step 1a — Data Loading", "",
        f"- **Samples**: {len(sheet)}",
        f"- **Layout**: {sheet.layout}",
        f"- **Genome**: {sheet.genome}",
        f"- **Conditions**: {', '.join(sheet.conditions)}",
        "- **Replicates per condition**:",
    ]
    for cond, reps in sheet.replicates_per_condition.items():
        lines.append(f"  - {cond}: {len(reps)} replicate(s) {reps}")
    lines += [
        f"- **Replicated**: {sheet.is_replicated}",
        "",
        "## Step 1b — Adapter Trimming", "",
        # params["tool"] is already resolved to the actual tool at this point
        f"- **Tool**: {params.get('tool', 'unknown')}",
        f"- **Adapter**: `{params.get('adapter', NEXTERA_ADAPTER)}`",
        f"- **Min length after trim**: {params.get('min_length', MIN_READ_LENGTH_AFTER_TRIM)} bp",
        f"- **Base quality**: Q{params.get('quality', BASE_QUALITY_THRESHOLD)}",
        "",
    ]

    if preprocess_results:
        try:
            import pandas as pd
            df = build_preprocessing_summary(preprocess_results)
            lines.append("### Trimming summary\n")
            lines.append(df.to_markdown(index=False))
            lines.append("")
        except Exception:
            pass

    lines += [
        "## Next Steps", "",
        "- **Step 2a**: Alignment → ENCODE BAM filtering → deduplication"
        " → chrM removal → mapping stats → downsampling",
        "- **Step 2b**: Post-alignment QC (NRF/PBC1/PBC2, TSS enrichment, fragment length)",
        "- **Step 3a**: Peak calling (MACS2) → consensus peak set",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation.",
    ]

    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill":           SKILL_NAME,
        "version":         SKILL_VERSION,
        "log":             str(output_dir / f"{SKILL_NAME}.log"),
        "steps_completed": ["data_loading", "preprocessing"],
        "steps_pending":   [
            "mapping", "qc_after_mapping",
            "peak_calling", "qc_after_peak_calling", "peak_annotation",
            "differential_analysis", "motif_and_footprinting",
        ],
        "params":       params,
        "sample_sheet": sample_sheet_to_dict(sheet),
        "preprocessing": [
            {
                "sample":     r.sample_name,
                "tool":       r.tool,
                "r1_trimmed": str(r.r1_trimmed),
                "r2_trimmed": str(r.r2_trimmed) if r.r2_trimmed else None,
                "stats":      r.stats,
            }
            for r in preprocess_results
        ],
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


# ---------------------------------------------------------------------------
# Reproducibility
# ---------------------------------------------------------------------------

def write_reproducibility(
    output_dir: Path,
    params: dict[str, Any],
    *,
    demo_mode: bool = False,
) -> None:
    """Write commands.sh and requirements.txt under output_dir/reproducibility/.

    output_dir — the skill's output directory (the path passed to --output);
                 also used in commands.sh so reruns recreate the same layout.
    """
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)

    cmd = (
        f"python {SCRIPT_REL} "
        f"{'--demo' if demo_mode else '--input <samplesheet.tsv>'} "
        f"--wd {shlex.quote(str(output_dir))}"
    )
    # Only Step-1 parameters.
    # params["tool"] is the resolved actual tool ("fastp" or "trim_galore"), never "auto".
    for key, flag in [
        ("genome",     "--genome"),
        ("tool",       "--tool"),
        ("threads",    "--threads"),
        ("min_length", "--min-length"),
        ("quality",    "--quality"),
    ]:
        v = params.get(key)
        if v is not None:
            cmd += f" {flag} {shlex.quote(str(v))}"

    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Pinned package versions → reproducibility/requirements.txt, via the
    # shared OmicsClaw helper so bulk-ATAC uses the same filename and format
    # as every other domain's skills.
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ATAC-seq preprocessing.\n\n"
            "Step 1 scope: data loading, ENCODE QC criteria, adapter trimming.\n"
            "Use --demo to download and trim GSE66386 FASTQs (S. cerevisiae T0 vs T15)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # ── Required ──────────────────────────────────────────────────────
    req = p.add_argument_group("required")
    req.add_argument("--output", "--wd", dest="wd", required=True,
                     help="Working directory (accepts --output too for "
                          "OmicsClaw runner compatibility).")
    req.add_argument("--input",  dest="samplesheet",
                     help="TSV/CSV sample sheet: sample, condition, replicate, R1 [, R2]. "
                          "Required unless --demo is used.")

    # ── Demo ───────────────────────────────────────────────────────
    demo = p.add_argument_group("demo")
    demo.add_argument("--demo", action="store_true",
                      help="Download GSE66386 FASTQs (T0/T15, 2 reps, sacCer3) and run Step 1.")
    demo.add_argument("--demo-n-reads", type=int, default=0,
                      help="Number of reads to subsample per FASTQ in demo mode. "
                           "0 (default) uses the full FASTQs without subsampling.")

    # ── Optional ───────────────────────────────────────────────────
    opt = p.add_argument_group("optional")
    opt.add_argument("--genome", default=None,
                     help="Reference genome build (e.g. hg38, mm10, sacCer3). "
                          "Metadata for downstream steps (mapping). Demo defaults to sacCer3.")
    opt.add_argument("--tool", default="auto", choices=["auto", "fastp", "trim_galore"],
                     help="Trimming tool. 'auto' picks fastp if available. (default: auto)")
    opt.add_argument("--threads",    type=int, default=16,
                     help="Number of threads (default: 16).")
    opt.add_argument("--adapter",    default=None,
                     help=f"Adapter sequence (default: Nextera {NEXTERA_ADAPTER}).")
    opt.add_argument("--min-length", type=int, default=MIN_READ_LENGTH_AFTER_TRIM,
                     help=f"Min read length after trimming (default: {MIN_READ_LENGTH_AFTER_TRIM}).")
    opt.add_argument("--quality",    type=int, default=BASE_QUALITY_THRESHOLD,
                     help=f"Phred quality threshold (default: {BASE_QUALITY_THRESHOLD}).")
    opt.add_argument("--no-fastqc",  action="store_true",
                     help="Skip FastQC (default: run if fastqc is in PATH).")
    return p


# ── Progress reporting ──────────────────────────────────────────────────
# Written to the controlling terminal (/dev/tty) when one exists, so step
# progress shows live even though the OmicsClaw runner buffers the piped
# stdout; falls back to stdout when there is no terminal. See _emit_progress.
_STEPS = [
    "Load / download sample data (sample sheet + FASTQs)",
    "Adapter trimming + FastQC",
    "Write report, reproducibility, and result.json",
]


def _emit_progress(text: str) -> None:
    """Show progress live on the controlling terminal, bypassing the
    OmicsClaw runner's stdout capture; fall back to stdout when there is
    no terminal (CI / redirected output)."""
    if not tty_write(text):
        print(text, flush=True)


def _print_step_plan() -> None:
    n = len(_STEPS)
    lines = [f"\n[{SKILL_NAME}] pipeline — {n} step(s):"]
    lines += [f"  [{i}/{n}] {desc}" for i, desc in enumerate(_STEPS, 1)]
    lines.append("")
    _emit_progress("\n".join(lines))


def _step(n: int, msg: str) -> None:
    _emit_progress(f"[{SKILL_NAME}] ==> step {n}/{len(_STEPS)}: {msg}")
    logger.info("==> step %d/%d: %s", n, len(_STEPS), msg)


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if not args.demo and not args.samplesheet:
        parser.error("Provide --input <samplesheet> or --demo")

    _print_step_plan()

    # --genome handling:
    # Optional metadata — not used by preprocessing itself (trimming/FastQC).
    # Stored in result.json so downstream steps (mapping) can pick it up.
    if args.demo:
        if args.genome and args.genome != "sacCer3":
            logger.warning(
                "--genome %s ignored in demo mode: "
                "demo data is GSE66386 (sacCer3, S. cerevisiae).",
                args.genome,
            )
        genome = "sacCer3"
    else:
        genome = args.genome  # may be None

    # output_dir — the skill's own output directory (the path passed to
    # --output).  Per the OmicsClaw per-skill output contract every
    # artifact lands directly here — there is NO nested <wd>/preprocessing/
    # subdir.  The caller passes a step-specific dir, e.g.
    # --output <project>/preprocessing, so sibling steps can find each other.
    #
    # Layout:
    #   <output_dir>/../                  ← parent of --output
    #   ├── demo_samplesheet.tsv          ← demo mode only — demo INPUT
    #   ├── fastq/                        ← demo mode only — demo INPUT
    #   │                                   (raw + subsampled FASTQs)
    #   └── <output_dir>/                 ← --output — skill artifacts only
    #       ├── README.md
    #       ├── report.md
    #       ├── result.json
    #       ├── reproducibility/
    #       └── fastq_trimmed/
    #
    # Demo mode places its FASTQ dir + sample sheet BESIDE --output, not
    # inside it: that data stands in for input a real user prepares
    # themselves (a fastq/ dir kept separate from the analysis output), so
    # burying it among the skill's own artifacts would misrepresent the
    # real-run layout. Only skill-generated artifacts land in <output_dir>.
    output_dir = Path(args.wd)
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    # params["tool"] starts as the CLI value ("auto"/"fastp"/"trim_galore").
    # After trimming it is updated to the actual tool used so that
    # commands.sh and result.json never contain "auto".
    params: dict[str, Any] = {
        "genome":     genome,
        "tool":       args.tool,
        "threads":    args.threads,
        "adapter":    args.adapter or NEXTERA_ADAPTER,
        "min_length": args.min_length,
        "quality":    args.quality,
        "run_fastqc": not args.no_fastqc,
        # condition_col removed — belongs to Step 4a (bulkatac-diff)
    }

    # ── Step 1a: load / download sample data ────────────────────────────────
    # In demo mode get_data writes demo_samplesheet.tsv + the raw/subsampled
    # FASTQs into <output_dir>/../fastq/ — beside --output, so the demo
    # input mirrors a real user's separately-prepared fastq/ directory.
    _step(1, "loading sample data"
             + (" — demo mode: downloading GSE66386 FASTQs from SRA "
                "(~1 GB, can take several minutes)" if args.demo else ""))
    sheet = get_data(
        args.samplesheet,
        demo=args.demo,
        demo_n_reads=args.demo_n_reads,
        output_dir=output_dir,
        # Demo FASTQs land beside --output (its parent dir), mirroring a real
        # run where the user prepares the fastq/ dir as separate input.
        subsample_dir=output_dir.parent / "fastq" if args.demo else None,
        default_genome=genome,
    )

    # ── Step 1b: adapter trimming ────────────────────────────────────────────
    _step(2, f"adapter trimming + FastQC on {len(sheet)} sample(s)")
    preprocess_dir     = output_dir / "fastq_trimmed"
    preprocess_results = run_all_preprocessing(
        list(sheet), preprocess_dir,
        tool=args.tool, threads=args.threads, adapter=args.adapter,
        min_length=args.min_length, quality=args.quality,
        run_fastqc=not args.no_fastqc,
    )

    # Resolve "auto" → actual tool ("fastp" or "trim_galore")
    # Must happen before write_report and write_reproducibility
    params["tool"] = preprocess_results[0].tool if preprocess_results else args.tool

    _step(3, "writing report, reproducibility, and result.json")
    write_report(output_dir, sheet, preprocess_results, params)
    write_reproducibility(output_dir, params, demo_mode=args.demo)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`fastq_trimmed/` — trimmed FASTQs and QC reports per sample.\n"
        "`fastq_trimmed/trimmed_summary.csv` — trimming statistics.\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr.\n"
        "\nNext: Step 2a (alignment) requires a BWA or Bowtie2 genome index.\n"
    )

    print(
        f"\n{SKILL_NAME} Step 1 complete:\n"
        f"  {len(sheet)} samples  [{sheet.layout}]\n"
        f"  {len(sheet.conditions)} condition(s): {', '.join(sheet.conditions)}\n"
        f"  Genome:          {genome}\n"
        f"  Tool used:       {params['tool']}\n"
        f"  Output dir:      {output_dir}\n"
        f"  Trimmed FASTQs:  {preprocess_dir}\n"
        f"  Summary:         {preprocess_dir / 'trimmed_summary.csv'}\n"
        f"  Report:          {output_dir / 'report.md'}\n"
        f"\n  Next → bulkatac-mapping → bulkatac-peak-calling → bulkatac-DA\n"
        f"         → bulkatac-motif-enrichment (sequence motifs)  |  "
        f"bulkatac-footprinting (TF occupancy)\n"
    )


if __name__ == "__main__":
    main()