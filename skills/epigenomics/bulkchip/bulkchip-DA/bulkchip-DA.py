#!/usr/bin/env python3
"""
bulkchip-DA.py — Bulk ChIP-seq differential binding (Step 4).

Implemented (pyDESeq2-backed). See `_lib/DA.py`.

Scope
-----
  Step 4 — Differential binding via pyDESeq2
    Consensus peak count matrix from Step 3
    → pyDESeq2 two-condition contrast (size factors, Wald test, LFC shrink)
    → volcano plot
    → IGV-ready BED tracks of up / down differentially-bound peaks

Output layout
-------------
  <output>/
  ├── README.md, report.md, result.json
  ├── differential_binding.csv         (peak, baseMean, log2FC, pvalue, padj)
  ├── volcano.png
  ├── up_peaks.bed / down_peaks.bed
  └── reproducibility/

References
----------
  pyDESeq2 : https://github.com/owkin/PyDESeq2
  DESeq2   : https://doi.org/10.1186/s13059-014-0550-8

Quick-start
-----------
  python bulkchip-DA.py --wd <project>/DA --treat <cond_b> --control <cond_a>
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
_BULKCHIP_DIR = _SKILL_DIR.parent
_PROJECT_ROOT = _BULKCHIP_DIR.parent.parent.parent

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

SKILL_NAME    = "bulkchip-DA"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkchip/bulkchip-DA/bulkchip-DA.py"

from skills.epigenomics.bulkchip._lib.subenv_bootstrap import ensure_bulkchip_env  # noqa: E402
from skills.epigenomics.bulkchip._lib.progress import tty_write  # noqa: E402
ensure_bulkchip_env()

from skills.epigenomics.bulkchip._lib.DA import (                       # noqa: E402
    DAResult, run_differential_binding, plot_volcano,
)
from omicsclaw.common.runlog import attach_run_log                     # noqa: E402

_STEPS = [
    "Load Step-3 result + consensus count matrix",
    "pyDESeq2 two-condition contrast (size factors, Wald, LFC shrink)",
    "Volcano plot + up/down peak BED tracks",
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


# ---------------------------------------------------------------------------
# Load Step-3 (peak-calling) result.json
# ---------------------------------------------------------------------------

def load_step3_result(result_json: Path) -> dict[str, Any]:
    """Resolve the consensus count matrix + ChIP sample order/conditions."""
    data = json.loads(result_json.read_text())
    consensus = data.get("consensus", {}) or {}
    counts_file = consensus.get("count_matrix")

    # Count-matrix columns are the ChIP samples, in the order featureCounts saw
    # them — that's the order of the "peak_calling" list written by Step 3.
    chip_samples = [p["sample"] for p in data.get("peak_calling", [])]

    # Condition per ChIP sample from the carried sample sheet.
    ss = data.get("sample_sheet", {}) or {}
    cond_by_name = {s["name"]: s.get("condition", "") for s in ss.get("samples", [])}
    conditions = [cond_by_name.get(n, "") for n in chip_samples]

    return {
        "data": data,
        "counts_file": Path(counts_file) if counts_file else None,
        "sample_names": chip_samples,
        "conditions": conditions,
    }


# ---------------------------------------------------------------------------
# Report + result.json + reproducibility
# ---------------------------------------------------------------------------

def write_report(output_dir: Path, da: DAResult, params: dict[str, Any],
                 step3_data: dict[str, Any], prev_result_path: Path) -> None:
    lines = [
        "# ChIP-seq Differential Binding Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        "## Step 4 — Differential binding (pyDESeq2)", "",
        f"- **Contrast**: {da.contrast}",
        f"- **Thresholds**: padj < {da.padj_threshold}, |log2FC| ≥ {da.lfc_threshold}",
        "",
        "| Gained (up) | Lost (down) | Tested |",
        "|---|---|---|",
        f"| {da.n_up:,} | {da.n_down:,} | {da.n_tested:,} |",
        "",
        f"- Full table: `{da.results_tsv.name}`",
        f"- Volcano: `{da.volcano_png.name if da.volcano_png else 'n/a'}`",
        f"- BED tracks: `{da.up_bed.name if da.up_bed else 'n/a'}`, "
        f"`{da.down_bed.name if da.down_bed else 'n/a'}`",
        "",
        "> log2FC > 0 = stronger binding in the treatment condition; "
        "< 0 = stronger in the reference. DESeq2 size-factor normalization "
        "handles library-depth differences across ChIP samples.",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill":           SKILL_NAME,
        "version":         SKILL_VERSION,
        "log":             str(output_dir / f"{SKILL_NAME}.log"),
        "steps_completed": step3_data.get("steps_completed", []) + ["differential_binding"],
        "steps_pending":   [s for s in step3_data.get("steps_pending", [])
                            if s not in ("differential_binding",)],
        "params":          params,
        "differential_binding": {
            "contrast":       da.contrast,
            "results_tsv":    str(da.results_tsv),
            "volcano_png":    str(da.volcano_png) if da.volcano_png else None,
            "up_bed":         str(da.up_bed) if da.up_bed else None,
            "down_bed":       str(da.down_bed) if da.down_bed else None,
            "all_bed":        str(da.all_bed) if da.all_bed else None,
            "n_up":           da.n_up,
            "n_down":         da.n_down,
            "n_tested":       da.n_tested,
            "padj_threshold": da.padj_threshold,
            "lfc_threshold":  da.lfc_threshold,
        },
        "prev_result": str(prev_result_path),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(output_dir: Path, params: dict[str, Any], prev_result_path: Path) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    cmd = (
        f"python {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))} "
        f"--padj {params.get('padj')} --lfc {params.get('lfc')} --threads {params.get('threads')}"
    )
    if params.get("treat"):
        cmd += f" --treat {shlex.quote(params['treat'])}"
    if params.get("control"):
        cmd += f" --control {shlex.quote(params['control'])}"
    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["pandas", "numpy", "pydeseq2", "matplotlib"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Bulk ChIP-seq differential binding (pyDESeq2).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkchip-peak-calling (Step 3). "
                          "Auto-detected from --wd's sibling peak_calling/result.json if omitted.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too).")

    opt = p.add_argument_group("optional")
    opt.add_argument("--treat", default=None, help="Treatment condition (numerator of the contrast).")
    opt.add_argument("--control", default=None, help="Reference condition (denominator).")
    opt.add_argument("--padj", type=float, default=0.05, help="Adjusted p-value cutoff (default 0.05).")
    opt.add_argument("--lfc", type=float, default=1.0, help="|log2FC| cutoff for up/down calls (default 1.0).")
    opt.add_argument("--threads", type=int, default=8)
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "peak_calling" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd so the Step-3 result.json can be located.")
    if not prev_result_path.exists():
        parser.error(f"Step-3 peak-calling result not found: {prev_result_path}")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir  = Path(args.wd) if args.wd else project_dir / "DA"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    _print_step_plan()

    # ── Step 1: load Step-3 result ──────────────────────────────────────────
    _step(1, "loading Step-3 peak-calling result + consensus count matrix")
    s3 = load_step3_result(prev_result_path)
    counts_file  = s3["counts_file"]
    sample_names = s3["sample_names"]
    conditions   = s3["conditions"]
    if not counts_file or not counts_file.exists():
        parser.error("Consensus count matrix not found in Step-3 result.json "
                     "(run bulkchip-peak-calling first).")
    unique = sorted(set(c for c in conditions if c))
    if len(unique) < 2:
        parser.error(f"DA needs ≥2 ChIP conditions with replicates; found: {unique or 'none'}.")
    logger.info("Loaded Step 3: %d ChIP samples, conditions=%s, matrix=%s",
                len(sample_names), unique, counts_file)

    params: dict[str, Any] = {
        "treat":   args.treat,
        "control": args.control,
        "padj":    args.padj,
        "lfc":     args.lfc,
        "threads": args.threads,
    }

    # ── Step 2: pyDESeq2 contrast ───────────────────────────────────────────
    treat   = args.treat or unique[-1]    # default: alphabetically-last vs first
    control = args.control or unique[0]
    _step(2, f"differential binding (pyDESeq2) — contrast {treat} vs {control}")
    da = run_differential_binding(
        counts_file, sample_names, conditions, output_dir / "differential_binding",
        contrast_treat=treat, contrast_control=control,
        padj_threshold=args.padj, lfc_threshold=args.lfc,
    )

    # ── Step 3: volcano ─────────────────────────────────────────────────────
    _step(3, "volcano plot + up/down peak BED tracks")
    plot_volcano(da, output_dir / "plots")

    # ── Step 4: outputs ─────────────────────────────────────────────────────
    _step(4, "writing report, reproducibility, and result.json")
    write_report(output_dir, da, params, s3["data"], prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)

    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`differential_binding/` — pyDESeq2 results TSV, summary, up/down/all BED tracks.\n"
        "`plots/` — volcano plot (PDF/PNG) + underlying TSV.\n"
        f"`{SKILL_NAME}.log` — full run log: narrative + tool/library output.\n"
        "\nDifferential binding is the end of the core ChIP pipeline; "
        "see bulkchip-motif-enrichment / bulkchip-annotation-enrichment for downstream.\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  Contrast:  {da.contrast}\n"
        f"  Gained/Lost: {da.n_up:,} up / {da.n_down:,} down  ({da.n_tested:,} tested)\n"
        f"  Results:   {da.results_tsv}\n"
        f"  Volcano:   {da.volcano_png}\n"
        f"  Report:    {output_dir / 'report.md'}\n"
        f"\n  Next → downstream analyses (run any/all):\n"
        f"         • bulkchip-motif-enrichment — sequence-level TF motifs\n"
        f"         • bulkchip-peak-annotation → bulkchip-enrichment — peaks → genes → GO/KEGG\n"
        f"           (peak-annotation auto-adds the DA up/down peaks alongside the consensus)\n"
    )


if __name__ == "__main__":
    main()
