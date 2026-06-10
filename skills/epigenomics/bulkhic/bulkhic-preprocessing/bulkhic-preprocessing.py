#!/usr/bin/env python3
"""
bulkhic-preprocessing.py — Bulk Hi-C Step 1: sample-sheet load + FastQC + trim.

Scope
-----
  Sample sheet (sample, condition, replicate, R1, R2 [, genome])
  → FastQC on raw reads
  → adapter + quality trimming (fastp)
  → trimmed FASTQs + per-sample stats, ready for bulkhic-mapping (Step 2).

  Hi-C has no input/IgG control and no antibody/peak-mode — every sample is a
  Hi-C library grouped by biological condition + replicate.

Output layout
-------------
  <output>/
  ├── README.md, report.md, result.json
  ├── fastq_trimmed/                  (per-sample trimmed FASTQs + trimmed_summary.csv)
  └── reproducibility/

Quick-start
-----------
  python bulkhic-preprocessing.py --demo --output <project>/preprocessing
  python bulkhic-preprocessing.py --input samples.tsv --output <project>/preprocessing
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

_SKILL_DIR    = Path(__file__).resolve().parent
_BULKHIC_DIR  = _SKILL_DIR.parent
_PROJECT_ROOT = _BULKHIC_DIR.parent.parent.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkhic-preprocessing"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkhic/bulkhic-preprocessing/bulkhic-preprocessing.py"

from skills.epigenomics.bulkhic._lib.subenv_bootstrap import ensure_bulkhic_env  # noqa: E402
from skills.epigenomics.bulkhic._lib.progress import tty_write  # noqa: E402
ensure_bulkhic_env()

from skills.epigenomics.bulkhic._lib.preprocessing import (  # noqa: E402
    ILLUMINA_UNIVERSAL_ADAPTER, MIN_READ_LENGTH_AFTER_TRIM, BASE_QUALITY_THRESHOLD,
    get_data, run_all_preprocessing, sample_sheet_to_dict,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load / download sample data (sample sheet + FASTQs)",
    "FastQC (+ optional fastp adapter/quality trim via --trim; default maps raw)",
    "Write report, reproducibility, and result.json",
]


def _emit_progress(text: str) -> None:
    if not tty_write(text):
        print(text, flush=True)


def _print_step_plan() -> None:
    n = len(_STEPS)
    lines = [f"\n[{SKILL_NAME}] pipeline — {n} step(s):"]
    lines += [f"  [{i}/{n}] {d}" for i, d in enumerate(_STEPS, 1)]
    lines.append("")
    _emit_progress("\n".join(lines))


def _step(n: int, msg: str) -> None:
    _emit_progress(f"[{SKILL_NAME}] ==> step {n}/{len(_STEPS)}: {msg}")
    logger.info("==> step %d/%d: %s", n, len(_STEPS), msg)


def write_report(output_dir, sheet, results, params, prev_result_path=None) -> None:
    lines = [
        "# Hi-C Preprocessing Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Samples", "",
        f"- **Samples**: {len(sheet)} Hi-C librar(y/ies)",
        f"- **Layout**: {sheet.layout}",
        f"- **Genome**: {sheet.genome}",
        f"- **Conditions**: {', '.join(sheet.conditions)}",
        f"- **Tool**: {params.get('tool')}",
        "",
        "### Trimming\n",
        "| Sample | Condition | Reads before | Reads after | % kept |",
        "|---|---|---|---|---|",
    ]
    by_cond = {s.name: s.condition for s in sheet.samples}
    for r in results:
        st = r.stats
        before = st.get("total_reads_before")
        after = st.get("total_reads_after")
        pct = f"{after / before * 100:.1f}%" if before else "—"
        lines.append(
            f"| {r.sample_name} | {by_cond.get(r.sample_name, '')} "
            f"| {before:,} | {after:,} | {pct} |" if before and after
            else f"| {r.sample_name} | {by_cond.get(r.sample_name, '')} | — | — | — |"
        )
    lines += [
        "", "## Next Steps", "",
        "- **Step 2**: `bulkhic-mapping` — bwa-mem2 -SP5M + pairtools → `.pairs.gz` + QC.",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill":           SKILL_NAME,
        "version":         SKILL_VERSION,
        "log":             str(output_dir / f"{SKILL_NAME}.log"),
        "steps_completed": ["preprocessing"],
        "steps_pending":   ["mapping", "matrix", "compartments", "insulation", "loops", "pileup"],
        "params":          params,
        "sample_sheet":    sample_sheet_to_dict(sheet),
        "preprocessing": [
            {
                "sample":     r.sample_name,
                "tool":       r.tool,
                "r1_trimmed": str(r.r1_trimmed),
                "r2_trimmed": str(r.r2_trimmed) if r.r2_trimmed else None,
                "stats":      r.stats,
            }
            for r in results
        ],
        "prev_result": str(prev_result_path) if prev_result_path else None,
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(output_dir: Path, params: dict[str, Any], args) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    if args.demo:
        cmd = f"python {SCRIPT_REL} --demo --output {shlex.quote(str(output_dir))}"
        if args.demo_n_reads > 0:
            cmd += f" --demo-n-reads {args.demo_n_reads}"
    else:
        cmd = (f"python {SCRIPT_REL} --input {shlex.quote(str(args.samplesheet))} "
               f"--output {shlex.quote(str(output_dir))}")
    cmd += f" --threads {shlex.quote(str(params.get('threads')))}"
    if params.get("trim"):
        cmd += " --trim"
        for key, flag in [("tool", "--tool"), ("min_length", "--min-length"), ("quality", "--quality")]:
            v = params.get(key)
            if v is not None and not (key == "tool" and v == "none"):
                cmd += f" {flag} {shlex.quote(str(v))}"
    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Bulk Hi-C FastQC + optional adapter trimming (default: map raw).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--output", "--wd", dest="wd", required=True,
                     help="Working directory (accepts --output too).")
    req.add_argument("--input", dest="samplesheet", default=None,
                     help="Sample sheet TSV/CSV: sample, condition, replicate, r1, r2 "
                          "[, genome]. Required unless --demo.")
    demo = p.add_argument_group("demo")
    demo.add_argument("--demo", action="store_true",
                      help="Download a small D. melanogaster S2R+ Hi-C test set (dm6, "
                           "Wang et al. 2018 / GSE101317) and run Step 1.")
    demo.add_argument("--demo-n-reads", type=int, default=3_000_000, dest="demo_n_reads",
                      help="Read pairs to stream per FASTQ in demo mode (default 3,000,000; "
                           "the source libraries are 13–36 GB so the demo streams only this "
                           "prefix). 0 = download the full files.")
    opt = p.add_argument_group("optional")
    opt.add_argument("--genome", default=None, help="Genome build (metadata; demo is dm6).")
    opt.add_argument("--trim", action="store_true",
                     help="Enable fastp adapter/quality trimming. Default OFF: Hi-C is "
                          "mapped raw (4DN/distiller/Juicer standard) — bwa-mem2 -SP5M + "
                          "pairtools handle adapters/ligation junctions.")
    opt.add_argument("--tool", default="auto", choices=["auto", "fastp"],
                     help="Trimming tool when --trim is set (default: auto → fastp).")
    opt.add_argument("--threads", type=int, default=16)
    opt.add_argument("--adapter", default=None, help=f"Adapter (default {ILLUMINA_UNIVERSAL_ADAPTER}).")
    opt.add_argument("--min-length", type=int, default=MIN_READ_LENGTH_AFTER_TRIM, dest="min_length")
    opt.add_argument("--quality", type=int, default=BASE_QUALITY_THRESHOLD)
    opt.add_argument("--no-fastqc", action="store_true", dest="no_fastqc")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if not args.demo and not args.samplesheet:
        parser.error("Provide --input <samplesheet> or --demo")

    _print_step_plan()

    genome = "dm6" if args.demo else args.genome
    output_dir = Path(args.wd)
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    params: dict[str, Any] = {
        "genome":     genome,
        "trim":       args.trim,
        "tool":       (args.tool if args.trim else "none"),
        "threads":    args.threads,
        "adapter":    args.adapter or ILLUMINA_UNIVERSAL_ADAPTER,
        "min_length": args.min_length,
        "quality":    args.quality,
        "run_fastqc": not args.no_fastqc,
    }

    _step(1, "loading sample data"
             + (" — demo mode: streaming D. melanogaster S2R+ Hi-C FASTQs (GSE101317; first run fetches)"
                if args.demo else ""))
    sheet = get_data(
        args.samplesheet, demo=args.demo, demo_n_reads=args.demo_n_reads,
        output_dir=output_dir,
        subsample_dir=output_dir.parent / "fastq" if args.demo else None,
        default_genome=genome or "hg38",
    )

    _step(2, f"FastQC{' + fastp trimming' if args.trim else ' (no trim — mapping raw reads)'} on {len(sheet)} sample(s)")
    fastq_trimmed_dir = output_dir / "fastq_trimmed"
    results = run_all_preprocessing(
        list(sheet), fastq_trimmed_dir,
        do_trim=args.trim,
        tool=args.tool, threads=args.threads, adapter=args.adapter,
        min_length=args.min_length, quality=args.quality, run_fastqc=not args.no_fastqc,
    )

    _step(3, "writing report, reproducibility, and result.json")
    write_report(output_dir, sheet, results, params)
    write_reproducibility(output_dir, params, args)
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`fastq_trimmed/<sample>/fastqc_raw/` — FastQC reports; with --trim, also the "
        "fastp-trimmed FASTQs (+ `trimmed_summary.csv`). Default maps raw reads.\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + every tool's stdout/stderr.\n"
        "\nNext: bulkhic-mapping (Step 2 — reads → .pairs).\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  {len(sheet)} Hi-C sample(s)  [{sheet.layout}]\n"
        f"  {len(sheet.conditions)} condition(s): {', '.join(sheet.conditions)}\n"
        f"  Genome:         {sheet.genome}\n"
        f"  Reads → mapping: {'fastp-trimmed' if args.trim else 'raw (no trim)'}\n"
        f"  Report:         {output_dir / 'report.md'}\n"
        f"\n  Next → bulkhic-mapping → bulkhic-matrix\n"
        f"         → bulkhic-compartments | bulkhic-insulation | bulkhic-loops → bulkhic-pileup\n"
    )


if __name__ == "__main__":
    main()
