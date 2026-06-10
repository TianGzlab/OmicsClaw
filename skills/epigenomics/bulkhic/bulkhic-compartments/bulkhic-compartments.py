#!/usr/bin/env python3
"""
bulkhic-compartments.py — Bulk Hi-C Step 4a: A/B compartments (cooltools).

cooltools expected-cis → eigs-cis (GC-phased E1) → saddle, per sample, on the
balanced .mcool from bulkhic-matrix. Default resolution 100 kb.

Quick-start
-----------
  python bulkhic-compartments.py --prev-result <project>/matrix/result.json --wd <project>/compartments
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

SKILL_NAME    = "bulkhic-compartments"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkhic/bulkhic-compartments/bulkhic-compartments.py"

from skills.epigenomics.bulkhic._lib.subenv_bootstrap import ensure_bulkhic_env  # noqa: E402
from skills.epigenomics.bulkhic._lib.progress import tty_write  # noqa: E402
ensure_bulkhic_env()

from skills.epigenomics.bulkhic._lib.compartments import (  # noqa: E402
    DEFAULT_RESOLUTIONS, run_compartments, CompartmentResult, plot_saddle_strength_all,
    run_compartment_pca,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load Step-3 matrix result + resolve .mcool + FASTA",
    "expected-cis + eigs-cis (GC-phased E1) + saddle per sample",
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


def write_report(output_dir, results: list[CompartmentResult], params, step3_data, prev_result_path) -> None:
    lines = [
        "# Hi-C A/B Compartment Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        f"**Resolutions**: {', '.join(f'{r:,}' for r in params.get('resolutions', []))} bp", "", "---", "",
        "| Sample | Resolution | E1 track | A/B BED | Saddle | Strength |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        _s = f"{r.strength:.3f}" if r.strength is not None else "—"
        lines.append(
            f"| {r.sample_name} | {r.resolution:,} | {'✓' if r.eigs_vecs else '—'} "
            f"| {'✓' if r.ab_bed else '—'} | {'✓' if r.saddle_png else '—'} | {_s} |"
        )
    lines += ["", "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation."]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill": SKILL_NAME, "version": SKILL_VERSION,
        "log": str(output_dir / f"{SKILL_NAME}.log"), "params": params,
        "compartments": [
            {
                "sample":       r.sample_name,
                "resolution":   r.resolution,
                "is_combined":  r.is_combined,
                "eigs_vecs":    str(r.eigs_vecs) if r.eigs_vecs else None,
                "eigs_lam":     str(r.eigs_lam) if r.eigs_lam else None,
                "ab_bed":       str(r.ab_bed) if r.ab_bed else None,
                "saddle_npz":   str(r.saddle_npz) if r.saddle_npz else None,
                "saddle_png":   str(r.saddle_png) if r.saddle_png else None,
                "gc_track":     str(r.gc_track) if r.gc_track else None,
                "view_bed":     str(r.view_bed) if r.view_bed else None,
                "expected_tsv": str(r.expected_tsv) if r.expected_tsv else None,
                "strength_tsv": str(r.strength_tsv) if r.strength_tsv else None,
                "strength":     r.strength,
                "AA":           r.aa,
                "BB":           r.bb,
                "AB":           r.ab,
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
        f"--threads {params.get('threads')}\n"
    )
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["cooler", "cooltools", "bioframe", "numpy", "pandas", "matplotlib"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Hi-C A/B compartments (eigs-cis + saddle).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkhic-matrix. Auto-detected from --wd's sibling matrix/result.json.")
    req.add_argument("--output", "--wd", dest="wd", default=None)
    opt = p.add_argument_group("optional")
    opt.add_argument("--resolutions", default=",".join(str(r) for r in DEFAULT_RESOLUTIONS),
                     help="Comma-separated bin sizes for compartments "
                          f"(default {','.join(str(r) for r in DEFAULT_RESOLUTIONS)}).")
    opt.add_argument("--n-eigs", type=int, default=1, dest="n_eigs")
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
    _step(1, "loading Step-3 matrix result + resolving .mcool + FASTA")
    step3_data = json.loads(prev_result_path.read_text())
    gf = step3_data.get("genome_files", {}) or {}
    fasta = gf.get("fasta")
    if not fasta:
        parser.error("Matrix result has no genome_files.fasta — needed for the GC phasing track.")
    matrices = [(m["sample"], Path(m["mcool"]), bool(m.get("combined")))
                for m in step3_data.get("matrix", [])]
    if not matrices:
        parser.error("Matrix result has no matrix[] entries.")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "compartments"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    resolutions = [int(x) for x in str(args.resolutions).replace(" ", "").split(",") if x]
    params = {"resolutions": resolutions, "n_eigs": args.n_eigs, "threads": args.threads}

    _step(2, f"expected-cis + eigs-cis + saddle on {len(matrices)} sample(s) "
             f"@ {len(resolutions)} resolution(s): {', '.join(f'{r:,}' for r in resolutions)} bp")
    results: list[CompartmentResult] = []
    comparison_figs: dict[int, str] = {}
    compartment_pca_figs: dict[int, dict] = {}
    for res in resolutions:
        comp_dir = output_dir / "compartments" / str(res)
        saddle_dir = output_dir / "saddle_plots" / str(res)
        res_results = [
            run_compartments(name, mcool, res, Path(fasta), comp_dir, saddle_dir,
                             n_eigs=args.n_eigs, nproc=args.threads, is_combined=comb)
            for name, mcool, comb in matrices
        ]
        # comparison figure shows CONDITIONS (combined) only; fall back to all if <2 combined.
        conds = [r for r in res_results if r.is_combined]
        panel = conds if len(conds) >= 2 else res_results
        if len(panel) >= 2:
            fig = plot_saddle_strength_all(panel, saddle_dir, step3_data.get("sample_sheet"))
            if fig:
                comparison_figs[res] = str(fig)
                logger.info("comparison (saddle_strength_all) @ %d bp: %s", res, fig)
        # compartment-profile PCA (dcHiC-style) on the individual replicates
        reps = [r for r in res_results if not r.is_combined]
        _pca = run_compartment_pca(reps, output_dir / "compartment_pca" / str(res),
                                   resolution=res, sample_sheet=step3_data.get("sample_sheet"))
        if _pca:
            compartment_pca_figs[res] = _pca
            logger.info("compartment PCA @ %d bp: PC1=%.0f%% PC2=%.0f%%", res,
                        100 * _pca["var"][0], 100 * _pca["var"][1] if len(_pca["var"]) > 1 else 0.0)
        results += res_results
    params["comparison_figs"] = comparison_figs
    params["compartment_pca"] = compartment_pca_figs

    _step(3, "writing report, reproducibility, and result.json")
    write_report(output_dir, results, params, step3_data, prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\nStart with `report.md`.\n"
        "`compartments/<res>/<sample>.eigs.<res>.cis.vecs.tsv` — E1 eigenvector (GC-phased: + = A, − = B);\n"
        "  per sample also `.AB.<res>.bed` (compartment calls) + `.expected_cis.<res>.tsv`.\n"
        "  `gc.<res>.tsv` + `view.<res>.bed` are shared per resolution (genome-level, sample-independent).\n"
        "`saddle_plots/<res>/<sample>.saddle.<res>.png` — saddle O/E heatmap; `.strength.<res>.tsv` +\n"
        "  `saddle_strength_all.{png,pdf}` (conditions only) — compartment strength.\n"
        "`compartment_pca/<res>/compartment_pca.{png,pdf}` — dcHiC-style sample PCA on quantile-normalized\n"
        "  GC-phased E1 compartment scores (+ `compartment_pca_coords.tsv`), per resolution.\n"
        f"`{SKILL_NAME}.log` — full run log.\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  Resolutions: {', '.join(f'{r:,}' for r in resolutions)} bp\n"
        + "".join(f"  [{r.sample_name}] "
                  f"{'E1 ✓' if r.eigs_vecs else 'E1 —'}"
                  f"{'  A/B ✓' if r.ab_bed else ''}"
                  f"{'  saddle ✓' if r.saddle_png else ''}"
                  f"{('  strength %.3f' % r.strength) if r.strength is not None else ''}\n" for r in results)
        + f"  Report: {output_dir / 'report.md'}\n"
        f"\n  Next → bulkhic-pileup (aggregate strength) — sibling: bulkhic-insulation, bulkhic-loops\n"
    )


if __name__ == "__main__":
    main()
