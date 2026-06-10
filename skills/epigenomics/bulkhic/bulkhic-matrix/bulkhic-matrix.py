#!/usr/bin/env python3
"""
bulkhic-matrix.py — Bulk Hi-C Step 3: .pairs → balanced .cool / .mcool.

cooler cload pairs → cooler balance (ICE) → cooler zoomify → .mcool, plus the
foundational P(s) contact-decay QC (cooltools expected-cis) and, when a
juicer_tools jar is available, a best-effort .hic export for Juicebox.

Quick-start
-----------
  python bulkhic-matrix.py --prev-result <project>/mapping/result.json --wd <project>/matrix
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

SKILL_NAME    = "bulkhic-matrix"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkhic/bulkhic-matrix/bulkhic-matrix.py"

from skills.epigenomics.bulkhic._lib.subenv_bootstrap import ensure_bulkhic_env  # noqa: E402
from skills.epigenomics.bulkhic._lib.progress import tty_write  # noqa: E402
ensure_bulkhic_env()

from skills.epigenomics.bulkhic._lib.matrix import (  # noqa: E402
    DEFAULT_BASE_BINSIZE, DEFAULT_RESOLUTIONS, DEFAULT_PS_RESOLUTION,
    run_all_matrix, run_all_combined, write_matrix_summary, MatrixResult, plot_pofs_all,
    run_scc_reproducibility, compute_expected_ps, run_pca_reproducibility,
    run_all_contact_maps,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load Step-2 result + resolve pairs + genome/chrom.sizes",
    "cooler cload + balance + zoomify → .mcool (+ optional .hic)",
    "P(s) contact-decay QC (cooltools expected-cis)",
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


def _parse_resolutions(spec: str | None) -> list[int]:
    if not spec:
        return list(DEFAULT_RESOLUTIONS)
    return sorted({int(x) for x in spec.replace(" ", "").split(",") if x})


def write_report(output_dir, results: list[MatrixResult], params, step2_data, prev_result_path) -> None:
    lines = [
        "# Hi-C Matrix Report (pairs → balanced .mcool)\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        "", "---", "",
        f"- **Samples**: {len(results)}   **Base binsize**: {params.get('base_binsize'):,} bp",
        f"- **Resolutions**: {', '.join(f'{r:,}' for r in params.get('resolutions', []))}",
        "",
        "### Outputs\n",
        "| Sample | Kind | .mcool | .hic | P(s) |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        kind = f"pooled ({', '.join(r.members)})" if r.is_combined else "replicate"
        lines.append(
            f"| {r.sample_name} | {kind} | `{Path(r.mcool).name}` "
            f"| {'`' + Path(r.hic).name + '`' if r.hic else '—'} "
            f"| {'✓' if r.ps_png else '—'} |"
        )
    n_combined = sum(1 for r in results if r.is_combined)
    if n_combined:
        lines += [
            "",
            f"> **Per-condition pooling**: {n_combined} combined matrix(es) built by "
            "summing each condition's replicate contacts (`cooler merge`) for deeper "
            "coverage. Downstream skills run on both replicate and pooled `.mcool`s.",
        ]
    lines += [
        "", "## Next Steps", "",
        "- **bulkhic-compartments** — A/B compartments (eigs-cis + saddle).",
        "- **bulkhic-insulation** — TADs / insulation boundaries.",
        "- **bulkhic-loops** — loops / dots.",
        "- **bulkhic-pileup** — aggregate feature strength.",
        "", "---", "",
        "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation.",
    ]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill":           SKILL_NAME,
        "version":         SKILL_VERSION,
        "log":             str(output_dir / f"{SKILL_NAME}.log"),
        "steps_completed": step2_data.get("steps_completed", []) + ["matrix"],
        "steps_pending":   [s for s in step2_data.get("steps_pending", []) if s != "matrix"],
        "params":          params,
        "matrix": [
            {
                "sample":       r.sample_name,
                "mcool":        str(r.mcool),
                "cool":         str(r.cool),
                "base_binsize": r.base_binsize,
                "resolutions":  r.resolutions,
                "balanced":     r.balanced,
                "hic":          str(r.hic) if r.hic else None,
                "expected_tsv": str(r.expected_tsv) if r.expected_tsv else None,
                "ps_png":       str(r.ps_png) if r.ps_png else None,
                "combined":     r.is_combined,
                "condition":    r.condition,
                "members":      r.members,
            }
            for r in results
        ],
        # Carry the reference forward — bulkhic-compartments needs the FASTA to
        # build a GC phasing track; all downstream need chrom_sizes + genome.
        "genome_files": step2_data.get("genome_files"),
        "sample_sheet": step2_data.get("sample_sheet"),
        "prev_result":  str(prev_result_path),
    }
    (output_dir / "result.json").write_text(json.dumps(result, indent=2, default=str))


def write_reproducibility(output_dir: Path, params: dict[str, Any], prev_result_path: Path) -> None:
    repro = output_dir / "reproducibility"
    repro.mkdir(parents=True, exist_ok=True)
    cmd = (f"python {SCRIPT_REL} --prev-result {shlex.quote(str(prev_result_path))} "
           f"--wd {shlex.quote(str(output_dir))} "
           f"--base-binsize {params.get('base_binsize')} "
           f"--resolutions {','.join(str(r) for r in params.get('resolutions', []))} "
           f"--threads {params.get('threads')}")
    cmd += f" --format {params.get('format', 'mcool')}"
    if params.get("p_curve_resolutions"):
        cmd += " --p-curve-resolutions " + ",".join(str(r) for r in params["p_curve_resolutions"])
    if params.get("scc_resolutions"):
        cmd += " --scc-resolutions " + ",".join(str(r) for r in params["scc_resolutions"])
    if not params.get("combine", True):
        cmd += " --no-combine"
    (repro / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["cooler", "cooltools", "numpy", "pandas", "matplotlib"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Bulk Hi-C pairs → balanced .cool/.mcool.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkhic-mapping (Step 2). "
                          "Auto-detected from --wd's sibling mapping/result.json if omitted.")
    req.add_argument("--output", "--wd", dest="wd", default=None,
                     help="Working directory (accepts --output too).")
    opt = p.add_argument_group("optional")
    opt.add_argument("--base-binsize", type=int, default=DEFAULT_BASE_BINSIZE, dest="base_binsize",
                     help=f"Finest bin size for the base .cool (default {DEFAULT_BASE_BINSIZE}).")
    opt.add_argument("--resolutions", default=None,
                     help="Comma-separated .mcool resolutions (multiples of base). "
                          f"Default: {','.join(str(r) for r in DEFAULT_RESOLUTIONS)}.")
    opt.add_argument("--p-curve-resolutions", default="5000,10000,50000,100000", dest="p_curve_resolutions",
                     help="Comma-separated resolutions for the P(s) contact-decay QC (default 5000,10000,50000,100000).")
    opt.add_argument("--scc-resolutions", default="5000,10000,50000,100000", dest="scc_resolutions",
                     help="Comma-separated resolutions for HiCRep SCC reproducibility QC (default 5000,10000,50000,100000).")
    opt.add_argument("--viz-resolution", type=int, default=500000, dest="viz_resolution",
                     help="Resolution (bp) for the whole-genome contact-map figures (default 500000).")
    opt.add_argument("--threads", type=int, default=16)
    opt.add_argument("--format", default="mcool", choices=["mcool", "both"], dest="fmt",
                     help="Output format: 'mcool' (default; cooler — the analysis format "
                          "every downstream skill reads) or 'both' (also export a Juicebox "
                          ".hic via the bundled tools/juicer_tools.jar, installed by "
                          "0_setup_env_for_bulkhic.sh). No hic-only mode: .mcool is always required.")
    opt.add_argument("--no-combine", action="store_true", dest="no_combine",
                     help="Skip building a pooled per-condition matrix (cooler merge of "
                          "each condition's replicates). By default a combined .mcool is "
                          "built for every condition with ≥2 replicates.")
    return p


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.prev_result:
        prev_result_path = Path(args.prev_result)
    elif args.wd:
        prev_result_path = Path(args.wd).parent / "mapping" / "result.json"
    else:
        parser.error("Provide --prev-result or --wd so the Step-2 result.json can be located.")
    if not prev_result_path.exists():
        parser.error(f"Mapping result not found: {prev_result_path}")

    _print_step_plan()

    _step(1, "loading Step-2 mapping result + resolving pairs/genome")
    step2_data = json.loads(prev_result_path.read_text())
    gf = step2_data.get("genome_files", {}) or {}
    genome = gf.get("genome") or (step2_data.get("sample_sheet", {}) or {}).get("genome")
    chrom_sizes = gf.get("chrom_sizes")
    if not genome or not chrom_sizes:
        parser.error("Step-2 result is missing genome/chrom_sizes (genome_files). Re-run bulkhic-mapping.")
    pairs_inputs = [(m["sample"], Path(m["pairs"])) for m in step2_data.get("mapping", [])]
    if not pairs_inputs:
        parser.error("Step-2 result has no mapping[] pairs.")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "matrix"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    resolutions = _parse_resolutions(args.resolutions)
    p_curve_res = [int(x) for x in str(args.p_curve_resolutions).split(',') if x.strip()]
    scc_res = [int(x) for x in str(args.scc_resolutions).split(',') if x.strip()]
    viz_res = int(args.viz_resolution)
    make_hic = (args.fmt == "both")
    combine = not args.no_combine
    _default_jar = _PROJECT_ROOT / "tools" / "juicer_tools.jar"
    juicer_jar = _default_jar if _default_jar.exists() else None
    if make_hic and juicer_jar is None:
        logger.warning("--format both requested but tools/juicer_tools.jar is missing — "
                       "run 0_setup_env_for_bulkhic.sh to install it; producing .mcool only.")
    if not make_hic:
        logger.info("Output format: .mcool only. Tip: use --format both to also "
                    "export a Juicebox .hic file.")

    params: dict[str, Any] = {
        "base_binsize": args.base_binsize,
        "resolutions":  sorted(set(resolutions) | {args.base_binsize}),
        "p_curve_resolutions": p_curve_res,
        "scc_resolutions": scc_res,
        "viz_resolution": viz_res,
        "threads":      args.threads,
        "format":       args.fmt,
        "make_hic":     make_hic,
        "combine":      combine,
        "juicer_jar":   str(juicer_jar) if juicer_jar else None,
    }

    _step(2, f"cooler cload + balance + zoomify on {len(pairs_inputs)} sample(s)"
             + (" (+ .hic export)" if make_hic and juicer_jar else ""))
    matrix_kwargs = dict(
        base_binsize=args.base_binsize, resolutions=resolutions,
        nproc=args.threads, juicer_jar=juicer_jar, make_hic=make_hic,
    )
    matrices_dir = output_dir / "matrix"
    results = run_all_matrix(pairs_inputs, genome, Path(chrom_sizes), matrices_dir, **matrix_kwargs)

    # Per-condition replicate pools: sum each condition's replicate contacts into
    # one deeper matrix so downstream loop/TAD/compartment calls have the coverage
    # the shallow per-replicate matrices lack. Added to results[] → flows downstream.
    if combine:
        sample_to_condition = {
            s["name"]: s["condition"]
            for s in (step2_data.get("sample_sheet", {}) or {}).get("samples", [])
        }
        combined = run_all_combined(
            results, sample_to_condition, Path(chrom_sizes), matrices_dir,
            pairs_by_sample=dict(pairs_inputs), **matrix_kwargs,
        )
        if combined:
            _emit_progress(f"[{SKILL_NAME}] pooled {len(combined)} condition(s): "
                           + ", ".join(r.condition for r in combined))
        results += combined

    # ---- base .cool cleanup: keep only the .mcool in each matrix dir ----
    for r in results:
        if getattr(r, "cool", None) and Path(r.cool).exists():
            Path(r.cool).unlink()
            r.cool = None

    # ---- multi-resolution QC under matrix_QC/{p_curve,scc}/<res> ----
    from types import SimpleNamespace
    avail = set(results[0].resolutions) if results else set()
    qc_dir = output_dir / "matrix_QC"

    pofs_figs = {}
    for res in [x for x in p_curve_res if x in avail]:
        d = qc_dir / "p_curve" / str(res)
        d.mkdir(parents=True, exist_ok=True)
        pres = []
        for r in results:
            tsv, png = compute_expected_ps(
                r.mcool, res, d / f"{r.sample_name}.expected_cis.{res}.tsv",
                d / f"{r.sample_name}.P_curve.{res}.png", nproc=args.threads)
            pres.append(SimpleNamespace(sample_name=r.sample_name, expected_tsv=tsv))
        if sum(1 for p in pres if p.expected_tsv) >= 2:
            fig = plot_pofs_all(pres, d, res)
            if fig:
                pofs_figs[res] = str(fig)
    params["p_curve_figs"] = pofs_figs

    reps = [(r.sample_name, r.mcool) for r in results if not r.is_combined]
    scc_summary = {}
    pca_summary = {}
    if len(reps) >= 2:
        for res in [x for x in scc_res if x in avail]:
            _scc = run_scc_reproducibility(reps, qc_dir / "scc" / str(res), resolution=res)
            if _scc:
                scc_summary[res] = {"min": _scc.get("min_scc"), "mean": _scc.get("mean_scc"),
                                    "png": str(_scc.get("png")) if _scc.get("png") else None}
                if _scc.get("min_scc") is not None:
                    logger.info("SCC @%d bp: min=%.3f mean=%.3f", res, _scc["min_scc"], _scc["mean_scc"])
            _pca = run_pca_reproducibility(reps, qc_dir / "pca" / str(res), resolution=res,
                                           sample_sheet=step2_data.get("sample_sheet"))
            if _pca:
                pca_summary[res] = _pca
    params["scc"] = scc_summary
    params["pca"] = pca_summary

    # ---- whole-genome contact maps (GenAsmClaw/HapHiC style) ----
    maps = run_all_contact_maps(
        results, output_dir / "matrix_visualization" / str(viz_res),
        resolution=viz_res, sample_sheet=step2_data.get("sample_sheet"))
    params["contact_maps"] = maps
    if maps:
        logger.info("contact maps (%d bp): %d sample(s)", viz_res, len(maps))

    write_matrix_summary(results, output_dir)
    _step(3, "matrix_QC: multi-resolution P(s) + SCC reproducibility")

    _step(4, "writing report, reproducibility, and result.json")
    write_report(output_dir, results, params, step2_data, prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\n"
        "Start with `report.md`.\n"
        "`matrix/<sample>/<sample>.mcool` — multi-resolution, ICE-balanced contact matrix.\n"
        "`matrix/<condition>_combined/...mcool` — per-condition pool (replicate contacts summed; "
        "deeper coverage for downstream calls). Skip with `--no-combine`.\n"
        "`matrix_QC/p_curve/<res>/` — P(s) decay+slope per sample + `P_curve_of_all` overlay, per resolution.\n"
        "`matrix_QC/scc/<res>/` — HiCRep SCC reproducibility heatmap + scc_values.tsv, per resolution.\n"
        "`matrix_QC/pca/<res>/` — sample PCA on contact matrices (sample_pca + pca_coords.tsv), per resolution.\n"
        "`matrix_visualization/<res>/` — whole-genome contact map per sample (default 500 kb).\n"
        "`matrix/<sample>/<sample>.hic` — optional Juicebox export (--format both).\n"
        f"`{SKILL_NAME}.log` — full run log.\n"
        "\nNext: bulkhic-compartments / bulkhic-insulation / bulkhic-loops → bulkhic-pileup.\n"
    )

    n_hic = sum(1 for r in results if r.hic)
    n_combined = sum(1 for r in results if r.is_combined)
    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  {len(results)} matrix(es)   base {args.base_binsize:,} bp   "
        f"{len(params['resolutions'])} resolutions"
        + (f"   ({n_combined} pooled per-condition)" if n_combined else "") + "\n"
        + "".join(f"  [{r.sample_name}]{' (pooled)' if r.is_combined else ''} .mcool ✓"
                  f"{'  .hic ✓' if r.hic else ''}"
                  f"{'  P(s) ✓' if r.ps_png else ''}\n" for r in results)
        + (f"  Format: mcool + .hic  ({n_hic}/{len(results)} exported)\n" if make_hic
           else "  Format: mcool only  (tip: --format both also writes a Juicebox .hic)\n")
        + f"  Matrices: {output_dir}\n"
        f"  Report:   {output_dir / 'report.md'}\n"
        f"\n  Next → downstream analyses (run any/all):\n"
        f"         • bulkhic-compartments — A/B compartments (eigs + saddle)\n"
        f"         • bulkhic-insulation — TADs / insulation boundaries\n"
        f"         • bulkhic-loops — loops / dots  → then bulkhic-pileup\n"
    )


if __name__ == "__main__":
    main()
