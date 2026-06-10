#!/usr/bin/env python3
"""
bulkatac-differential_accessibility.py — Differential accessibility analysis.

Reads Step 3 result.json → runs pyDESeq2 on peak count matrix → generates
DA results, genome browser tracks, volcano plot.

Usage
-----
  python bulkatac-differential_accessibility.py \\
      --prev-result output/peak_calling/result.json \\
      --wd output \\
      --treat T15 --control T0

Output layout
-------------
  <output>/
  ├── report.md, result.json, reproducibility/
  ├── DA/{contrast}/
  │   ├── da_results_{contrast}.tsv
  │   ├── da_summary_{contrast}.csv
  │   ├── da_peaks_up_{contrast}.bed
  │   ├── da_peaks_down_{contrast}.bed
  │   └── da_peaks_all_{contrast}.bed
  └── plots/{contrast}/
      └── volcano_{contrast}.{pdf,png,tsv}
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
_BULKATAC_DIR = _SKILL_DIR.parent                            # .../bulkatac/
_PROJECT_ROOT = _BULKATAC_DIR.parent.parent.parent           # OmicsClaw/

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkatac-DA"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkatac/bulkatac-DA/bulkatac-DA.py"

# ---------------------------------------------------------------------------
# _lib imports
# ---------------------------------------------------------------------------
# Relocate into the omicsclaw_bulkatac sub-env before the tool-backed _lib imports.
from skills.epigenomics.bulkatac._lib.subenv_bootstrap import ensure_bulkatac_env  # noqa: E402
from skills.epigenomics.bulkatac._lib.progress import tty_write  # noqa: E402
ensure_bulkatac_env()

from skills.epigenomics.bulkatac._lib.DA import (          # noqa: E402
    DAResult,
    run_differential_accessibility,
    plot_volcano,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402


# ---------------------------------------------------------------------------
# Load Step 3 result.json
# ---------------------------------------------------------------------------

def load_step3_result(result_json: Path) -> dict[str, Any]:
    """Load Step 3 result.json."""
    data = json.loads(result_json.read_text())

    # Count matrix
    consensus = data.get("consensus", {})
    counts_file = consensus.get("count_matrix")
    if counts_file:
        counts_file = Path(counts_file)

    # Sample info
    ss = data.get("sample_sheet", {})
    samples = ss.get("samples", [])
    sample_names = [s["name"] for s in samples]
    conditions   = [s.get("condition", "") for s in samples]

    # Genome files (for annotation) — may be None in older result.json
    gf = data.get("genome_files") or {}
    gtf = Path(gf["gtf"]) if gf.get("gtf") and Path(gf["gtf"]).exists() else None

    # Step 3 params (peak calling q-value)
    step3_params = data.get("params", {})
    peak_qvalue  = step3_params.get("qvalue", 0.05)

    # Step 3 annotation file
    step3_dir = result_json.parent
    annotation_tsv = step3_dir / "annotation" / f"qvalue{peak_qvalue}" / "annotated_peaks.tsv"
    if not annotation_tsv.exists():
        # Try searching for any annotated_peaks.tsv under annotation/
        ann_dir = step3_dir / "annotation"
        if ann_dir.exists():
            candidates = list(ann_dir.glob("*/annotated_peaks.tsv"))
            if candidates:
                annotation_tsv = candidates[0]
                logger.info("Found annotation file: %s", annotation_tsv)
            else:
                logger.warning("No annotated_peaks.tsv found under %s", ann_dir)
                annotation_tsv = None
        else:
            logger.warning("Annotation directory not found: %s", ann_dir)
            annotation_tsv = None

    return {
        "data":           data,
        "counts_file":    counts_file,
        "sample_names":   sample_names,
        "conditions":     conditions,
        "gtf":            gtf,
        "annotation_tsv": annotation_tsv,
        "peak_qvalue":    peak_qvalue,
    }


# ---------------------------------------------------------------------------
# Report + result.json
# ---------------------------------------------------------------------------

def write_report(
    output_dir: Path,
    da_result: DAResult,
    params: dict[str, Any],
    step3_data: dict[str, Any],
    *,
    param_tag: str = "",
    plots_dir: Path | None = None,
    prev_result_path: Path | None = None,
    annotation_tsv: Path | None = None,
) -> None:
    lines: list[str] = [
        "# Differential Accessibility Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        f"## Contrast: {da_result.contrast}", "",
        "| Metric | Value |",
        "|---|---|",
        f"| Peaks tested | {da_result.n_tested:,} |",
        f"| Up (increased accessibility) | {da_result.n_up:,} |",
        f"| Down (decreased accessibility) | {da_result.n_down:,} |",
        f"| padj threshold | {da_result.padj_threshold} |",
        f"| log2FC threshold | {da_result.lfc_threshold} |",
        "",
        "## Output files", "",
        f"- Full results: `DA/{da_result.contrast}/{param_tag}/da_results_{da_result.contrast}.tsv`",
        f"- Up peaks (browser): `DA/{da_result.contrast}/{param_tag}/da_peaks_up_{da_result.contrast}.bed`",
        f"- Down peaks (browser): `DA/{da_result.contrast}/{param_tag}/da_peaks_down_{da_result.contrast}.bed`",
        f"- All DA (color-coded): `DA/{da_result.contrast}/{param_tag}/da_peaks_all_{da_result.contrast}.bed`",
        "",
        "## Genome browser tracks", "",
        "BED files include track headers and RGB colors for direct loading in",
        "IGV, WashU Epigenome Browser, or UCSC Genome Browser.",
        "- Up peaks: red (255,0,0)",
        "- Down peaks: blue (0,0,255)",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. "
        "Results require expert interpretation.",
    ]

    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill":   SKILL_NAME,
        "version": SKILL_VERSION,
        "log":     str(output_dir / f"{SKILL_NAME}.log"),
        "params":  params,
        "param_tag": param_tag,
        "da": {
            "contrast":       da_result.contrast,
            "n_tested":       da_result.n_tested,
            "n_up":           da_result.n_up,
            "n_down":         da_result.n_down,
            "padj_threshold": da_result.padj_threshold,
            "lfc_threshold":  da_result.lfc_threshold,
            "results_tsv":    str(da_result.results_tsv),
            "up_bed":         str(da_result.up_bed) if da_result.up_bed else None,
            "down_bed":       str(da_result.down_bed) if da_result.down_bed else None,
            "all_bed":        str(da_result.all_bed) if da_result.all_bed else None,
            "volcano_pdf":    str(plots_dir / f"volcano_{da_result.contrast}.pdf"),
            "annotation_source": str(annotation_tsv) if annotation_tsv else None,
        },
        "prev_result":  str(prev_result_path),
        "sample_sheet": step3_data.get("sample_sheet"),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(
    output_dir: Path,
    params: dict[str, Any],
    prev_result_path: Path,
) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)

    cmd = (
        f"python {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))}"
    )
    for key, flag in [
        ("treat",   "--treat"),
        ("control", "--control"),
        ("padj",    "--padj"),
        ("lfc",     "--lfc"),
    ]:
        v = params.get(key)
        if v is not None:
            cmd += f" {flag} {shlex.quote(str(v))}"

    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Pinned package versions → reproducibility/requirements.txt, via the
    # shared OmicsClaw helper so bulk-ATAC uses the same filename and format
    # as every other domain's skills.
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pydeseq2", "pandas", "numpy", "matplotlib"])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            f"{SKILL_NAME} v{SKILL_VERSION}\n\n"
            "Differential accessibility analysis using pyDESeq2 on the\n"
            "peak count matrix from Step 3 (peak calling)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    req = p.add_argument_group("required (at least one)")
    req.add_argument("--prev-result", "--input", required=False, dest="prev_result",
                     default=None,
                     help="result.json from bulkatac-peak-calling (Step 3); accepts "
                          "--input too for OmicsClaw runner compatibility. "
                          "If omitted, auto-detected as <wd>/peak_calling/result.json.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too for "
                          "OmicsClaw runner compatibility). Default: sibling "
                          "of prev-result's parent dir (e.g. .../DA/).")

    contrast = p.add_argument_group("contrast")
    contrast.add_argument("--treat", default=None,
                          help="Treatment condition name (auto-detected if omitted).")
    contrast.add_argument("--control", default=None,
                          help="Control condition name (auto-detected if omitted).")

    thresh = p.add_argument_group("thresholds")
    thresh.add_argument("--padj", type=float, default=0.05,
                        help="Adjusted p-value threshold (default: 0.05).")
    thresh.add_argument("--lfc", type=float, default=1.0,
                        help="log2 fold change threshold (default: 1.0).")

    opt = p.add_argument_group("optional")
    opt.add_argument("--threads", type=int, default=16,
                     help="Number of threads (default: 16).")
    opt.add_argument("--skip-annotation", action="store_true", dest="skip_annotation",
                     help="Skip merging Step 3 peak annotation.")

    return p


# ── Progress reporting ──────────────────────────────────────────────────
# Written to the controlling terminal (/dev/tty) when one exists, so step
# progress shows live even though the OmicsClaw runner buffers the piped
# stdout; falls back to stdout when there is no terminal. See _emit_progress.
_STEPS = [
    "Load Step-3 peak-calling result",
    "Differential accessibility testing (pyDESeq2)",
    "Volcano plot",
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

    # ── Resolve prev-result: explicit > inferred from --wd ────────────────
    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "peak_calling" / "result.json"
    else:
        parser.error("Either --prev-result or --wd must be provided.")

    if not prev_result_path.exists():
        parser.error(f"--prev-result not found: {prev_result_path}")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "DA"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    _print_step_plan()

    # ── Load Step 3 ──────────────────────────────────────────────────────
    _step(1, "loading Step-3 peak-calling result")
    step3 = load_step3_result(prev_result_path)
    step3_data     = step3["data"]
    counts_file    = step3["counts_file"]
    sample_names   = step3["sample_names"]
    conditions     = step3["conditions"]
    annotation_tsv = step3["annotation_tsv"]

    if counts_file is None or not counts_file.exists():
        parser.error(f"Count matrix not found. Check Step 3 result.json.")

    logger.info("Loaded Step 3: %d samples, count matrix: %s",
                len(sample_names), counts_file)

    # Determine contrast
    treat   = args.treat
    control = args.control
    peak_qvalue = step3["peak_qvalue"]

    unique_conds = sorted(set(conditions))
    if len(unique_conds) < 2:
        parser.error(
            f"DA requires >= 2 conditions, got: {unique_conds}. "
            "Check sample_sheet conditions in Step 3 result.json."
        )
    if treat is None or control is None:
        control = unique_conds[0]
        treat   = unique_conds[1]

    contrast_name = f"{treat}_vs_{control}"
    param_tag = f"q{peak_qvalue}_padj{args.padj}_lfc{args.lfc}"

    params: dict[str, Any] = {
        "treat":       treat,
        "control":     control,
        "padj":        args.padj,
        "lfc":         args.lfc,
        "peak_qvalue": peak_qvalue,
    }

    # ── DA ────────────────────────────────────────────────────────────────
    _step(2, f"differential accessibility (pyDESeq2) — contrast {contrast_name}")
    da_dir = output_dir / "DA" / contrast_name / param_tag
    da_result = run_differential_accessibility(
        counts_file, sample_names, conditions, da_dir,
        contrast_treat=treat, contrast_control=control,
        annotation_tsv=annotation_tsv if not args.skip_annotation else None,
        padj_threshold=args.padj, lfc_threshold=args.lfc,
    )

    # ── Plots ─────────────────────────────────────────────────────────────
    _step(3, "volcano plot")
    plots_dir = output_dir / "plots" / contrast_name / param_tag
    plot_volcano(da_result, plots_dir)

    # ── Outputs ───────────────────────────────────────────────────────────
    _step(4, "writing report, reproducibility, and result.json")
    write_report(output_dir, da_result, params, step3_data,
                 param_tag=param_tag, plots_dir=plots_dir,
                 prev_result_path=prev_result_path,
                 annotation_tsv=annotation_tsv)
    write_reproducibility(output_dir, params, prev_result_path)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        f"`DA/{contrast_name}/{param_tag}/` — DA results, BED tracks for genome browsers.\n"
        f"`plots/{contrast_name}/{param_tag}/` — Volcano plot.\n"
        f"{SKILL_NAME}.log — full run log: narrative + every tool's stdout/stderr.\n"
        "\nDirectory naming: q=peak calling qvalue, padj=DA significance, lfc=fold change.\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  Contrast:  {da_result.contrast}\n"
        f"  Up peaks:  {da_result.n_up:,}\n"
        f"  Down peaks: {da_result.n_down:,}\n"
        f"  Results:   {da_result.results_tsv}\n"
        f"  Volcano:   {plots_dir / f'volcano_{da_result.contrast}.pdf'}\n"
        f"  Report:    {output_dir / 'report.md'}\n"
        f"\n  Next → downstream analyses (run any/all):\n"
        f"         • bulkatac-motif-enrichment — sequence-level TF motifs\n"
        f"         • bulkatac-footprinting — TOBIAS TF occupancy at motif sites\n"
    )


if __name__ == "__main__":
    main()
