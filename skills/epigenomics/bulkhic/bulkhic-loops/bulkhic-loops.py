#!/usr/bin/env python3
"""
bulkhic-loops.py — Bulk Hi-C Step 4c: loops via Mustache (multi-resolution).

Mustache (scale-space loop detection — the production caller) is run per sample
on the balanced .mcool from bulkhic-matrix, independently at each requested
resolution (default 5 kb + 10 kb). Each resolution's loops are written as their
own BEDPE — no cross-resolution merge.

Quick-start
-----------
  python bulkhic-loops.py --prev-result <project>/matrix/result.json --wd <project>/loops
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

SKILL_NAME    = "bulkhic-loops"
SKILL_VERSION = "0.2.0"
SCRIPT_REL    = "skills/epigenomics/bulkhic/bulkhic-loops/bulkhic-loops.py"

from skills.epigenomics.bulkhic._lib.subenv_bootstrap import ensure_bulkhic_env  # noqa: E402
from skills.epigenomics.bulkhic._lib.progress import tty_write  # noqa: E402
ensure_bulkhic_env()

from skills.epigenomics.bulkhic._lib.loops import (  # noqa: E402
    DEFAULT_RESOLUTIONS, DEFAULT_FDR, DEFAULT_MAX_DIST, run_loops, LoopResult,
    plot_loop_size_distribution, run_loop_pca,
)
from skills.epigenomics.bulkhic._lib.pileup import run_pileup, plot_pileup_all  # noqa: E402
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load Step-3 matrix result + resolve .mcool",
    "Mustache loop calling per sample (each resolution, no merge)",
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


def _res_cells(r: LoopResult, resolutions) -> str:
    return "  ".join(f"{res//1000}kb={r.n_by_res.get(res, '—')}" for res in resolutions)


def write_report(output_dir, results: list[LoopResult], params, step3_data, prev_result_path) -> None:
    resolutions = params.get("resolutions", [])
    lines = [
        "# Hi-C Loops Report (Mustache)\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        f"**Caller**: Mustache   **Resolutions**: {', '.join(f'{r:,}' for r in resolutions)} bp   "
        f"**p-threshold**: {params.get('fdr')}   **Max distance**: {params.get('max_dist'):,} bp", "", "---", "",
        "| Sample | " + " | ".join(f"{r//1000} kb" for r in resolutions) + " | Total |",
        "|---|" + "---|" * (len(resolutions) + 1),
    ]
    for r in results:
        cells = " | ".join(str(r.n_by_res.get(res, "—")) for res in resolutions)
        lines.append(f"| {r.sample_name} | {cells} | {r.n_loops:,} |")
    lines += ["", "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation."]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill": SKILL_NAME, "version": SKILL_VERSION,
        "log": str(output_dir / f"{SKILL_NAME}.log"), "params": params,
        "loops": [
            {
                "sample":         r.sample_name,
                "resolutions":    r.resolutions,
                "n_loops":        r.n_loops,
                "loops_bedpe":    str(r.primary_bedpe) if r.primary_bedpe else None,
                "per_resolution": [
                    {"resolution": res,
                     "bedpe":      str(r.bedpe_by_res[res]),
                     "n_loops":    r.n_by_res.get(res, 0)}
                    for res in r.resolutions if res in r.bedpe_by_res
                ],
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
    res_str = ",".join(str(r) for r in params.get("resolutions", []))
    (repro / "commands.sh").write_text(
        f"#!/bin/bash\npython {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))} --resolutions {res_str} "
        f"--fdr {params.get('fdr')} --max-dist {params.get('max_dist')}\n"
    )
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["mustache-hic", "cooler", "numpy", "pandas"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Hi-C loops (Mustache, multi-resolution).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkhic-matrix. Auto-detected from --wd's sibling matrix/result.json.")
    req.add_argument("--output", "--wd", dest="wd", default=None)
    opt = p.add_argument_group("optional")
    opt.add_argument("--resolutions", default=",".join(str(r) for r in DEFAULT_RESOLUTIONS),
                     help=f"Comma-separated bin sizes for Mustache (default {','.join(str(r) for r in DEFAULT_RESOLUTIONS)}).")
    # Back-compat: --resolution adds a single resolution.
    opt.add_argument("--resolution", type=int, default=None, help="Single resolution (alias; appended to --resolutions).")
    opt.add_argument("--fdr", type=float, default=DEFAULT_FDR,
                     help=f"Mustache p-value threshold -pt (default {DEFAULT_FDR}).")
    opt.add_argument("--max-dist", type=int, default=DEFAULT_MAX_DIST, dest="max_dist",
                     help=f"Max loop-locus separation bp -d (default {DEFAULT_MAX_DIST}).")
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

    resolutions = [int(x) for x in str(args.resolutions).split(",") if x.strip()]
    if args.resolution and args.resolution not in resolutions:
        resolutions.append(args.resolution)
    resolutions = sorted(set(resolutions))

    _print_step_plan()
    _step(1, "loading Step-3 matrix result + resolving .mcool")
    step3_data = json.loads(prev_result_path.read_text())
    matrices = [(m["sample"], Path(m["mcool"]), bool(m.get("combined")))
                for m in step3_data.get("matrix", [])]
    if not matrices:
        parser.error("Matrix result has no matrix[] entries.")
    mcool_of = {name: mcool for name, mcool, _ in matrices}

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "loops"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    params = {"resolutions": resolutions, "fdr": args.fdr,
              "max_dist": args.max_dist, "threads": args.threads}

    _step(2, f"Mustache on {len(matrices)} sample(s) @ {resolutions} bp (-pt {args.fdr})")
    results = [
        run_loops(name, mcool, resolutions, output_dir / "loops",
                  fdr=args.fdr, max_dist=args.max_dist, nproc=args.threads, is_combined=comb)
        for name, mcool, comb in matrices
    ]

    # per-resolution: loop size distribution (conditions only) + union-loop PCA (replicates)
    size_figs: dict[int, str] = {}
    loop_pca_figs: dict[int, dict] = {}
    loop_pileup_figs: dict[int, str] = {}
    for res in resolutions:
        loops_res_dir = output_dir / "loops" / str(res)
        conds = [r for r in results if r.is_combined]
        _sz = plot_loop_size_distribution(conds if conds else results, loops_res_dir,
                                          resolution=res, sample_sheet=step3_data.get("sample_sheet"))
        if _sz:
            size_figs[res] = str(_sz)
        reps = [r for r in results if not r.is_combined]
        loop_inputs = [(r.sample_name, r.bedpe_by_res.get(res), mcool_of.get(r.sample_name)) for r in reps]
        _pca = run_loop_pca(loop_inputs, output_dir / "loop_pca" / str(res),
                            resolution=res, sample_sheet=step3_data.get("sample_sheet"))
        if _pca:
            loop_pca_figs[res] = _pca
            logger.info("loop PCA @ %d bp: PC1=%.0f%% (%d union loops)", res,
                        100 * _pca["var"][0], _pca["n_union_loops"])
        # loop APA pileup (coolpup.py off-diagonal) — moved in from bulkhic-pileup
        pres = []
        for r in results:
            bp = r.bedpe_by_res.get(res)
            if bp and r.n_by_res.get(res, 0) > 0 and mcool_of.get(r.sample_name):
                pr = run_pileup(r.sample_name, mcool_of[r.sample_name], res, bp,
                                output_dir / "loop_pileup" / str(res),
                                features_format="bedpe", kind="loops", nproc=args.threads)
                pres.append(pr)
        if len(pres) >= 2:
            _pfig = plot_pileup_all(pres, output_dir / "loop_pileup" / str(res), "loops")
            if _pfig:
                loop_pileup_figs[res] = str(_pfig)
                logger.info("loop APA pileup @ %d bp: %s", res, _pfig)
    params["loop_size_figs"] = size_figs
    params["loop_pca"] = loop_pca_figs
    params["loop_pileup"] = loop_pileup_figs

    _step(3, "writing report, reproducibility, and result.json")
    write_report(output_dir, results, params, step3_data, prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\nStart with `report.md`.\n"
        "`loops/<res>/<sample>.loops.<res>.bedpe` — Mustache loops, one BEDPE per resolution (no merge);\n"
        "  raw `<sample>.mustache.<res>.tsv` alongside.\n"
        "`loops/<res>/loop_size_distribution.{png,pdf}` — loop size (anchor separation), conditions only.\n"
        "`loop_pca/<res>/loop_pca.{png,pdf}` — sample PCA on union-loop contact strength (+ coords).\n"
        "`loop_pileup/<res>/` — coolpup.py loop APA (aggregate peak analysis) per sample + comparison.\n"
        f"`{SKILL_NAME}.log` — full run log.\n"
        "\nNext: bulkhic-pileup — aggregate (APA) the loops to quantify strength.\n"
    )

    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete (Mustache):\n"
        f"  Resolutions: {', '.join(f'{r:,}' for r in resolutions)} bp   p-threshold: {args.fdr}\n"
        + "".join(f"  [{r.sample_name}] {_res_cells(r, resolutions)}  (total {r.n_loops})\n" for r in results)
        + f"  Report: {output_dir / 'report.md'}\n"
        f"\n  Next → bulkhic-pileup (APA on these loops) — sibling: bulkhic-compartments, bulkhic-insulation\n"
    )


if __name__ == "__main__":
    main()
