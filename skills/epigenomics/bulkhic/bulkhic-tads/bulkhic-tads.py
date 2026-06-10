#!/usr/bin/env python3
"""
bulkhic-insulation.py — Bulk Hi-C Step 4b: TADs / insulation (cooltools).

cooltools insulation (diamond-window score + boundary calling) per sample on the
balanced .mcool from bulkhic-matrix. Default resolution 25 kb, window ~10× bin.

Quick-start
-----------
  python bulkhic-insulation.py --prev-result <project>/matrix/result.json --wd <project>/insulation
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

SKILL_NAME    = "bulkhic-tads"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkhic/bulkhic-tads/bulkhic-tads.py"

from skills.epigenomics.bulkhic._lib.subenv_bootstrap import ensure_bulkhic_env  # noqa: E402
from skills.epigenomics.bulkhic._lib.progress import tty_write  # noqa: E402
ensure_bulkhic_env()

from skills.epigenomics.bulkhic._lib.insulation import (  # noqa: E402
    DEFAULT_RESOLUTION, DEFAULT_RESOLUTIONS, DEFAULT_WINDOW_MULTIPLES, run_insulation,
    InsulationResult, run_tad_pca, plot_tad_size_distribution,
)
from skills.epigenomics.bulkhic._lib.pileup import run_pileup, plot_pileup_all  # noqa: E402
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load Step-3 matrix result + resolve .mcool",
    "cooltools insulation + boundary calling per sample",
    "Write report, reproducibility, and result.json",
]


def _emit_progress(text: str) -> None:
    if not tty_write(text):
        print(text, flush=True)


def _print_step_plan() -> None:
    n = len(_STEPS)
    _emit_progress("\n".join([f"\n[{SKILL_NAME}] pipeline — {n} step(s):"]
                             + [f"  [{i}/{n}] {d}" for i, d in enumerate(_STEPS, 1)] + [""]))


def _step(n: int, msg: str) -> None:
    _emit_progress(f"[{SKILL_NAME}] ==> step {n}/{len(_STEPS)}: {msg}")
    logger.info("==> step %d/%d: %s", n, len(_STEPS), msg)


def write_report(output_dir, results: list[InsulationResult], params, step3_data, prev_result_path) -> None:
    lines = [
        "# Hi-C Insulation / TAD Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        f"**Resolutions**: {', '.join(f'{r:,}' for r in params.get('resolutions', []))} bp   "
        f"**Window**: {params.get('window_multiple')}× resolution", "", "---", "",
        "| Sample | Resolution | Boundaries | TADs | Insulation track |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r.sample_name} | {r.resolution:,} | {r.n_boundaries:,} | {r.n_tads:,} "
                     f"| {'✓' if r.insulation_tsv else '—'} |")
    lines += ["", "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation."]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill": SKILL_NAME, "version": SKILL_VERSION,
        "log": str(output_dir / f"{SKILL_NAME}.log"), "params": params,
        "insulation": [
            {
                "sample":         r.sample_name,
                "resolution":     r.resolution,
                "is_combined":    r.is_combined,
                "windows":        r.windows,
                "insulation_tsv": str(r.insulation_tsv) if r.insulation_tsv else None,
                "primary_window": r.primary_window,
                "boundaries_bed": str(r.boundaries_bed) if r.boundaries_bed else None,
                "n_boundaries":   r.n_boundaries,
                "tads_bed":       str(r.tads_bed) if r.tads_bed else None,
                "n_tads":         r.n_tads,
            }
            for r in results
        ],
        "genome_files": step3_data.get("genome_files"),
        "sample_sheet": step3_data.get("sample_sheet"),
        "prev_result":  str(prev_result_path),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(output_dir, params, prev_result_path) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    (repro / "commands.sh").write_text(
        f"#!/bin/bash\npython {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))} "
        f"--resolutions {','.join(str(r) for r in params.get('resolutions', []))} "
        f"--window-multiple {params.get('window_multiple')} "
        f"--threshold {params.get('threshold')}\n"
    )
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["cooler", "cooltools", "numpy", "pandas"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Hi-C insulation / TAD boundaries (cooltools).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkhic-matrix. Auto-detected from --wd's sibling matrix/result.json.")
    req.add_argument("--output", "--wd", dest="wd", default=None)
    opt = p.add_argument_group("optional")
    opt.add_argument("--resolutions", default=",".join(str(r) for r in DEFAULT_RESOLUTIONS),
                     help="Comma-separated bin sizes for TAD/insulation "
                          f"(default {','.join(str(r) for r in DEFAULT_RESOLUTIONS)}; MS set).")
    opt.add_argument("--window-multiple", type=int, default=8, dest="window_multiple",
                     help="Diamond window = N × resolution (MS uses 8).")
    opt.add_argument("--windows", default=None,
                     help="Explicit comma-separated diamond windows (bp); overrides --window-multiple.")
    opt.add_argument("--threshold", default="Li", help="Boundary threshold: Li | Otsu | <float>.")
    opt.add_argument("--threads", type=int, default=8)
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "matrix" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd.")
    if not prev_result_path.exists():
        parser.error(f"Matrix result not found: {prev_result_path}")

    _print_step_plan()
    _step(1, "loading Step-3 matrix result + resolving .mcool")
    step3_data = json.loads(prev_result_path.read_text())
    matrices = [(m["sample"], Path(m["mcool"]), bool(m.get("combined")))
                for m in step3_data.get("matrix", [])]
    mcool_of = {m["sample"]: Path(m["mcool"]) for m in step3_data.get("matrix", [])}
    if not matrices:
        parser.error("Matrix result has no matrix[] entries.")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "tads"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    resolutions = [int(x) for x in str(args.resolutions).replace(" ", "").split(",") if x]
    win_override = ([int(x) for x in args.windows.replace(" ", "").split(",") if x]
                    if args.windows else None)
    params = {"resolutions": resolutions, "window_multiple": args.window_multiple,
              "windows_override": win_override, "threshold": args.threshold, "threads": args.threads}

    _step(2, f"insulation + TAD calling on {len(matrices)} sample(s) @ {len(resolutions)} "
             f"resolution(s): {', '.join(f'{r:,}' for r in resolutions)} bp (window {args.window_multiple}x)")
    results: list[InsulationResult] = []
    size_figs: dict[int, str] = {}
    tad_pca_figs: dict[int, dict] = {}
    tad_pileup_figs: dict[int, str] = {}
    for res in resolutions:
        windows = win_override or [args.window_multiple * res]
        tads_dir = output_dir / "tads" / str(res)
        res_results = [
            run_insulation(name, mcool, res, tads_dir, windows=windows,
                           threshold=args.threshold, nproc=args.threads, is_combined=comb)
            for name, mcool, comb in matrices
        ]
        # TAD size distribution — conditions (combined) only
        conds = [r for r in res_results if r.is_combined]
        _szfig = plot_tad_size_distribution(conds if conds else res_results, tads_dir,
                                            resolution=res, sample_sheet=step3_data.get("sample_sheet"))
        if _szfig:
            size_figs[res] = str(_szfig)
        # TAD-profile PCA (HiC-bench style) on the individual replicates
        reps = [r for r in res_results if not r.is_combined]
        primary = reps[0].primary_window if reps else windows[len(windows) // 2]
        _pca = run_tad_pca(reps, output_dir / "tad_pca" / str(res),
                           resolution=res, window=primary,
                           sample_sheet=step3_data.get("sample_sheet"))
        if _pca:
            tad_pca_figs[res] = _pca
            logger.info("TAD PCA @ %d bp: PC1=%.0f%% PC2=%.0f%%", res,
                        100 * _pca["var"][0], 100 * _pca["var"][1] if len(_pca["var"]) > 1 else 0.0)
        # TAD pileup (coolpup.py rescaled on-diagonal) — moved in from bulkhic-pileup
        tpres = []
        for r in res_results:
            tb = getattr(r, "tads_bed", None)
            if tb and r.n_tads > 0 and mcool_of.get(r.sample_name):
                pr = run_pileup(r.sample_name, mcool_of[r.sample_name], res, tb,
                                output_dir / "tad_pileup" / str(res),
                                features_format="bed", kind="tads", nproc=args.threads)
                tpres.append(pr)
        if len(tpres) >= 2:
            _pfig = plot_pileup_all(tpres, output_dir / "tad_pileup" / str(res), "tads")
            if _pfig:
                tad_pileup_figs[res] = str(_pfig)
                logger.info("TAD pileup @ %d bp: %s", res, _pfig)
        results += res_results
    params["tad_size_figs"] = size_figs
    params["tad_pca"] = tad_pca_figs
    params["tad_pileup"] = tad_pileup_figs

    _step(3, "writing report, reproducibility, and result.json")
    write_report(output_dir, results, params, step3_data, prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\nStart with `report.md`.\n"
        "`tads/<res>/<sample>.TADs.<res>.bed` — TAD domains (small TADs merged across weaker boundary);\n"
        "  per sample also `.boundaries.<res>.bed` + `.insulation.<res>.tsv` (per-bin insulation score).\n"
        "  `view.<res>.bed` shared per resolution. Diamond window = window-multiple x resolution (MS: 8x).\n"
        "`tads/<res>/tad_size_distribution.{png,pdf}` — TAD size distribution, conditions only.\n"
        "`tad_pileup/<res>/` — coolpup.py rescaled on-diagonal TAD pileup per sample + comparison.\n"
        "`tad_pca/<res>/tad_pca.{png,pdf}` — sample PCA on quantile-normalized log2 insulation scores\n"
        "  (HiC-bench-style; + `tad_pca_coords.tsv`), per resolution.\n"
        f"`{SKILL_NAME}.log` — full run log.\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  Resolutions: {', '.join(f'{r:,}' for r in resolutions)} bp\n"
        + "".join(f"  [{r.sample_name}] {r.n_boundaries:,} boundaries, {r.n_tads:,} TADs"
                  f"{'' if r.insulation_tsv else '  (insulation track missing)'}\n" for r in results)
        + f"  Report: {output_dir / 'report.md'}\n"
        f"\n  Next → bulkhic-pileup (boundary strength) — sibling: bulkhic-compartments, bulkhic-loops\n"
    )


if __name__ == "__main__":
    main()
