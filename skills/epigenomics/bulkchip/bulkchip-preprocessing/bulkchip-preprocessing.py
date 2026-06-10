#!/usr/bin/env python3
"""
bulkchip-preprocessing.py — Bulk ChIP-seq preprocessing (Step 1).

Scope
-----
  Step 1a  Load sample sheet (with ChIP/input control pairing), validate files
           → skills/epigenomics/bulkchip/_lib/preprocessing.py
  Step 1b  Raw FASTQ QC (FastQC) + adapter trimming (fastp / Trim Galore)
           → skills/epigenomics/bulkchip/_lib/preprocessing.py

Downstream steps (separate skills): bulkchip-mapping, bulkchip-peak-calling,
bulkchip-DA, bulkchip-motif-enrichment, bulkchip-annotation-enrichment.

Use --demo to download + trim the nf-core SPT5 ChIP-seq test set
(S. cerevisiae, T0 vs T15, 2 ChIP reps each + 2 input controls, PE, sacCer3).
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
_SKILL_DIR    = Path(__file__).resolve().parent
_BULKCHIP_DIR = _SKILL_DIR.parent                            # .../bulkchip/
_PROJECT_ROOT = _BULKCHIP_DIR.parent.parent.parent           # OmicsClaw/

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkchip-preprocessing"
SKILL_VERSION = "0.1.0"
try:
    SCRIPT_REL = str(Path(__file__).resolve().relative_to(_PROJECT_ROOT))
except ValueError:
    SCRIPT_REL = "skills/epigenomics/bulkchip/bulkchip-preprocessing/bulkchip-preprocessing.py"

# ---------------------------------------------------------------------------
# _lib imports
# ---------------------------------------------------------------------------
# Relocate into the omicsclaw_bulkchip sub-env before the tool-backed _lib imports.
from skills.epigenomics.bulkchip._lib.subenv_bootstrap import ensure_bulkchip_env  # noqa: E402
from skills.epigenomics.bulkchip._lib.progress import tty_write  # noqa: E402
ensure_bulkchip_env()

from skills.epigenomics.bulkchip._lib.preprocessing import (    # noqa: E402
    get_data,
    sample_sheet_to_dict,
    SampleSheet,
    run_all_preprocessing,
    build_preprocessing_summary,
    PreprocessResult,
    MIN_READ_LENGTH_AFTER_TRIM,
    BASE_QUALITY_THRESHOLD,
)
from skills.epigenomics.bulkchip._lib.encode_qc_criteria import (  # noqa: E402
    ILLUMINA_UNIVERSAL_ADAPTER,
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
        "# ChIP-seq Preprocessing Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Step 1a — Data Loading", "",
        f"- **Samples**: {len(sheet)} "
        f"({len(sheet.chip_samples)} ChIP + {len(sheet.control_samples)} control)",
        f"- **Layout**: {sheet.layout}",
        f"- **Genome**: {sheet.genome}",
        f"- **Conditions**: {', '.join(sheet.conditions)}",
        "- **Replicates per condition**:",
    ]
    for cond, reps in sheet.replicates_per_condition.items():
        lines.append(f"  - {cond}: {len(reps)} replicate(s) {reps}")
    lines += [f"- **Replicated**: {sheet.is_replicated}", ""]

    if sheet.control_map:
        lines += ["### ChIP → input control pairing\n",
                  "| ChIP sample | Antibody | Peak mode | Control |",
                  "|---|---|---|---|"]
        ab = {s.name: (s.antibody or "") for s in sheet.samples}
        pm = {s.name: s.peak_mode for s in sheet.samples}
        for chip, ctrl in sheet.control_map.items():
            lines.append(f"| {chip} | {ab.get(chip,'')} | {pm.get(chip,'')} | {ctrl} |")
        lines.append("")

    lines += [
        "## Step 1b — Adapter Trimming", "",
        f"- **Tool**: {params.get('tool', 'unknown')}",
        f"- **Adapter**: `{params.get('adapter', ILLUMINA_UNIVERSAL_ADAPTER)}` (Illumina universal)",
        f"- **Min length after trim**: {params.get('min_length', MIN_READ_LENGTH_AFTER_TRIM)} bp",
        f"- **Base quality**: Q{params.get('quality', BASE_QUALITY_THRESHOLD)}",
        "",
    ]

    if preprocess_results:
        try:
            df = build_preprocessing_summary(preprocess_results)
            lines.append("### Trimming summary\n")
            lines.append(df.to_markdown(index=False))
            lines.append("")
        except Exception:
            pass

    lines += [
        "## Next Steps", "",
        "- **Step 2**: `bulkchip-mapping` — Bowtie2/BWA alignment, ENCODE BAM "
        "filtering + dedup, NRF/PBC, NSC/RSC cross-correlation + fingerprint QC.",
        "- **Step 3**: `bulkchip-peak-calling` — MACS2 vs input control "
        "(narrow / broad), consensus, featureCounts, FRiP.",
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
            "peak_calling", "differential_binding",
            "motif_enrichment", "peak_annotation", "enrichment",
        ],
        "params":       params,
        "sample_sheet": sample_sheet_to_dict(sheet),
        "preprocessing": [
            {
                "sample":     r.sample_name,
                "tool":       r.tool,
                "is_control": r.is_control,
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
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)

    cmd = (
        f"python {SCRIPT_REL} "
        f"{'--demo' if demo_mode else '--input <samplesheet.tsv>'} "
        f"--wd {shlex.quote(str(output_dir))}"
    )
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

    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ChIP-seq preprocessing.\n\n"
            "Step 1 scope: sample-sheet parsing (ChIP/input pairing), FastQC, "
            "adapter trimming.\nUse --demo to download + trim the nf-core SPT5 "
            "ChIP-seq test set (S. cerevisiae T0 vs T15 + inputs)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--output", "--wd", dest="wd", required=True,
                     help="Working directory (accepts --output too for "
                          "OmicsClaw runner compatibility).")
    req.add_argument("--input", dest="samplesheet",
                     help="TSV/CSV sample sheet: sample, condition, replicate, R1 [, R2], "
                          "control, antibody [, peak_mode]. Required unless --demo.")

    demo = p.add_argument_group("demo")
    demo.add_argument("--no-input", action="store_true", dest="no_input",
                      help="Demo modifier: drop the 2 input/IgG controls so only the "
                           "4 SPT5 ChIP samples are used (blank `control` column) — "
                           "exercises MACS2's no-`-c` peak-calling path and writes "
                           "demo_samplesheet_no_input.tsv. Use together with --demo "
                           "(e.g. `oc run bulkchip-preprocessing --demo --no-input`).")
    demo.add_argument("--demo", action="store_true",
                      help="Download the SPT5 ChIP-seq test set (4 ChIP + 2 input, sacCer3) and run Step 1.")
    demo.add_argument("--demo-n-reads", type=int, default=0, dest="demo_n_reads",
                      help="Reads to subsample per FASTQ in demo mode. "
                           "0 (default) uses the full FASTQs without subsampling.")

    opt = p.add_argument_group("optional")
    opt.add_argument("--genome", default=None,
                     help="Reference genome build (metadata for bulkchip-mapping). Demo: sacCer3.")
    opt.add_argument("--tool", default="auto", choices=["auto", "fastp", "trim_galore"],
                     help="Trimming tool. 'auto' picks fastp if available. (default: auto)")
    opt.add_argument("--threads", type=int, default=16, help="Threads (default: 16).")
    opt.add_argument("--adapter", default=None,
                     help=f"Adapter sequence (default: Illumina universal {ILLUMINA_UNIVERSAL_ADAPTER}).")
    opt.add_argument("--min-length", type=int, default=MIN_READ_LENGTH_AFTER_TRIM, dest="min_length",
                     help=f"Min read length after trimming (default: {MIN_READ_LENGTH_AFTER_TRIM}).")
    opt.add_argument("--quality", type=int, default=BASE_QUALITY_THRESHOLD,
                     help=f"Phred quality threshold (default: {BASE_QUALITY_THRESHOLD}).")
    opt.add_argument("--no-fastqc", action="store_true", dest="no_fastqc",
                     help="Skip FastQC (default: run if fastqc is in PATH).")
    return p


# ── Progress reporting ──────────────────────────────────────────────────
_STEPS = [
    "Load / download sample data (sample sheet + FASTQs)",
    "Adapter trimming + FastQC",
    "Write report, reproducibility, and result.json",
]


def _emit_progress(text: str) -> None:
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

    if args.no_input and not args.demo:
        parser.error("--no-input is a demo modifier; use it together with --demo "
                     "(e.g. --demo --no-input).")

    if not args.demo and not args.samplesheet:
        parser.error("Provide --input <samplesheet> or --demo")

    _print_step_plan()

    # --genome is metadata only (not used during trimming); demo is sacCer3.
    if args.demo:
        if args.genome and args.genome != "sacCer3":
            logger.warning(
                "--genome %s ignored in demo mode: demo data is the SPT5 ChIP-seq "
                "test set (sacCer3, S. cerevisiae).", args.genome,
            )
        genome = "sacCer3"
    else:
        genome = args.genome  # may be None

    output_dir = Path(args.wd)
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    params: dict[str, Any] = {
        "genome":     genome,
        "tool":       args.tool,
        "threads":    args.threads,
        "adapter":    args.adapter or ILLUMINA_UNIVERSAL_ADAPTER,
        "min_length": args.min_length,
        "quality":    args.quality,
        "run_fastqc": not args.no_fastqc,
    }

    # ── Step 1a: load / download sample data ────────────────────────────────
    _step(1, "loading sample data"
             + (" — demo mode: downloading SPT5 ChIP-seq FASTQs "
                "(nf-core test set; first run fetches"
                + (" + subsamples" if args.demo_n_reads > 0 else "") + ")"
                if args.demo else ""))
    sheet = get_data(
        args.samplesheet,
        demo=args.demo,
        demo_n_reads=args.demo_n_reads,
        demo_no_input=args.no_input,
        output_dir=output_dir,
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

    # Resolve "auto" → actual tool ("fastp" or "trim_galore").
    params["tool"] = preprocess_results[0].tool if preprocess_results else args.tool

    _step(3, "writing report, reproducibility, and result.json")
    write_report(output_dir, sheet, preprocess_results, params)
    write_reproducibility(output_dir, params, demo_mode=args.demo)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`fastq_trimmed/` — trimmed FASTQs and QC reports per sample (ChIP + control).\n"
        "`fastq_trimmed/trimmed_summary.csv` — trimming statistics.\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr.\n"
        "\nNext: Step 2 (`bulkchip-mapping`) — needs a BWA or Bowtie2 genome index.\n"
    )

    print(
        f"\n{SKILL_NAME} Step 1 complete:\n"
        f"  {len(sheet)} samples  [{sheet.layout}]  "
        f"({len(sheet.chip_samples)} ChIP + {len(sheet.control_samples)} control)\n"
        f"  {len(sheet.conditions)} condition(s): {', '.join(sheet.conditions)}\n"
        f"  Genome:          {genome}\n"
        f"  Tool used:       {params['tool']}\n"
        f"  Output dir:      {output_dir}\n"
        f"  Trimmed FASTQs:  {preprocess_dir}\n"
        f"  Summary:         {preprocess_dir / 'trimmed_summary.csv'}\n"
        f"  Report:          {output_dir / 'report.md'}\n"
        f"\n  Next → bulkchip-mapping → bulkchip-peak-calling → bulkchip-DA\n"
        f"         → bulkchip-motif-enrichment (sequence motifs)\n"
        f"         → bulkchip-peak-annotation → bulkchip-enrichment (peaks → genes → GO/KEGG)\n"
    )


if __name__ == "__main__":
    main()
