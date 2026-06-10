#!/usr/bin/env python3
"""
bulkhic-pileup.py — Bulk Hi-C Step 4d: aggregate / pileup analysis (cooltools).

Stacks observed/expected snippets around features (loops BEDPE → off-diagonal
APA; boundaries BED → on-diagonal) from the balanced .mcool, producing an
aggregate heatmap + central-enrichment score per sample.

Features default to the loops from a sibling bulkhic-loops run; override with
--features (a BEDPE or BED) and --features-format.

Quick-start
-----------
  python bulkhic-pileup.py --prev-result <project>/matrix/result.json --wd <project>/pileup
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

SKILL_NAME    = "bulkhic-pileup"
SKILL_VERSION = "0.1.0"
SCRIPT_REL    = "skills/epigenomics/bulkhic/bulkhic-pileup/bulkhic-pileup.py"

from skills.epigenomics.bulkhic._lib.subenv_bootstrap import ensure_bulkhic_env  # noqa: E402
from skills.epigenomics.bulkhic._lib.progress import tty_write  # noqa: E402
ensure_bulkhic_env()

from skills.epigenomics.bulkhic._lib.pileup import (  # noqa: E402
    DEFAULT_FLANK, run_pileup, PileupResult, plot_pileup_all,
)
from omicsclaw.common.runlog import attach_run_log  # noqa: E402

_STEPS = [
    "Load Step-3 matrix result + resolve .mcool + features",
    "cooltools pileup (aggregate O/E around features) per sample",
    "Write report, reproducibility, and result.json",
]

# Printed by this terminal skill to announce the whole suite is finished.
_SUITE_DONE_BANNER = (
    "\n  ✓ All bulkhic steps complete: "
    "preprocessing → mapping → matrix → compartments / insulation / loops → pileup.\n"
    "  This is the final step of the bulk Hi-C suite.\n"
)


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


def _discover_from_sibling(
    result_path: Path, entries_key: str, file_key: str, count_key: str,
) -> tuple[dict[str, Path], int | None]:
    """Read a sibling result.json → ({sample: feature_file}, common_resolution).

    Only keeps entries whose feature file exists and whose count (n_loops /
    n_boundaries) is > 0, so empty calls don't spawn empty pileups.
    """
    if not result_path.exists():
        return {}, None
    data = json.loads(result_path.read_text())
    valid = [e for e in data.get(entries_key, [])
             if e.get(file_key) and e.get(count_key, 0) and Path(e[file_key]).exists()]
    if not valid:
        return {}, None
    # Multi-resolution siblings (e.g. tads) list one entry per (sample, resolution).
    # Pick a SINGLE resolution so the feature BED and the pileup resolution stay
    # consistent: the finest resolution that covers the most samples.
    from collections import defaultdict
    if any(e.get("resolution") for e in valid):
        per_res = defaultdict(dict)
        for e in valid:
            r = e.get("resolution")
            if r is not None:
                per_res[r][e["sample"]] = Path(e[file_key])
        best = max(per_res, key=lambda r: (len(per_res[r]), -r))   # most samples, then finest
        return dict(per_res[best]), best
    per_sample = {}
    for e in valid:
        per_sample[e["sample"]] = Path(e[file_key])
    return per_sample, None


def _find_sibling_result(project_dir: Path, name: str) -> Path:
    """Locate a sibling skill's result.json, tolerating a numbered-dir prefix.

    Matches an exact dir (``loops/``) first, then any dir ending in the name
    (e.g. ``03_loops/``) so the tiered output-dir numbering doesn't break
    auto-discovery. Falls back to the plain path if nothing is found.
    """
    exact = project_dir / name / "result.json"
    if exact.exists():
        return exact
    matches = sorted(p for p in project_dir.glob(f"*{name}/result.json"))
    return matches[0] if matches else exact


def _discover_feature_sets(args, project_dir: Path) -> list[dict[str, Any]]:
    """Build the feature sets to pile up.

    Explicit ``--features`` wins (single set applied to all samples). Otherwise
    auto-discover BOTH sibling sources, each piled up in its own geometry:
      - ``loops`` from ``../loops/result.json`` → BEDPE, off-diagonal APA
      - ``boundaries`` from ``../tads/result.json`` → BED, on-diagonal
    A set whose resolution is missing falls back to ``--resolution``.
    """
    # GENERAL-PURPOSE tool: pile up whatever --features you pass, in the --kind
    # geometry. Loop APA and TAD pileups now run automatically inside
    # bulkhic-loops / bulkhic-tads, so they are no longer auto-discovered here.
    if not args.features:
        return []
    kind = args.kind or ("tads" if args.features_format == "bed" else "loops")
    return [{
        "kind": kind, "format": args.features_format,
        "resolution": args.resolution, "shared": Path(args.features), "per_sample": {},
    }]


def write_report(output_dir, results: list[PileupResult], params, step3_data, prev_result_path) -> None:
    kinds = params.get("feature_kinds") or []
    lines = [
        "# Hi-C Pileup / Aggregate Report\n",
        f"**Skill**: {SKILL_NAME}  |  **Version**: {SKILL_VERSION}",
        f"**Flank**: {params.get('flank'):,} bp   "
        f"**Feature sets**: {', '.join(kinds) if kinds else '—'}", "", "---", "",
        "| Sample | Feature | Format | Res (bp) | Pileup | Center enrichment |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        enr = f"{r.center_enrichment:.2f}" if r.center_enrichment else "—"
        lines.append(
            f"| {r.sample_name} | {r.kind} | {r.features_format} | {r.resolution:,} "
            f"| {'✓' if r.pileup_npz else '—'} | {enr} |")
    lines += ["", "> **Disclaimer**: OmicsClaw is a research tool. Results require expert interpretation."]
    (output_dir / "report.md").write_text("\n".join(lines) + "\n")

    result: dict[str, Any] = {
        "skill": SKILL_NAME, "version": SKILL_VERSION,
        "log": str(output_dir / f"{SKILL_NAME}.log"), "params": params,
        "pileup": [
            {
                "sample":            r.sample_name,
                "kind":              r.kind,
                "resolution":        r.resolution,
                "features":          str(r.features),
                "features_format":   r.features_format,
                "pileup_npz":        str(r.pileup_npz) if r.pileup_npz else None,
                "pileup_png":        str(r.pileup_png) if r.pileup_png else None,
                "center_enrichment": r.center_enrichment,
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
    # Feature sets (loops/boundaries) are auto-discovered from sibling results, so
    # the repro command just re-runs the auto-discovery; --resolution is only
    # emitted when the user pinned one (else each sibling's resolution is used).
    res = params.get("resolution")
    res_flag = f" --resolution {res}" if res else ""
    (repro / "commands.sh").write_text(
        f"#!/bin/bash\npython {SCRIPT_REL} "
        f"--prev-result {shlex.quote(str(prev_result_path))} "
        f"--wd {shlex.quote(str(output_dir))}{res_flag} "
        f"--flank {params.get('flank')}\n"
    )
    from omicsclaw.common.report import write_repro_requirements
    write_repro_requirements(output_dir, ["cooler", "cooltools", "numpy", "pandas", "matplotlib"])


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=f"{SKILL_NAME} v{SKILL_VERSION} — Hi-C aggregate / pileup (cooltools).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    req = p.add_argument_group("required")
    req.add_argument("--prev-result", "--input", dest="prev_result", default=None,
                     help="result.json from bulkhic-matrix (for the .mcool). "
                          "Auto-detected from --wd's sibling matrix/result.json.")
    req.add_argument("--output", "--wd", dest="wd", default=None)
    opt = p.add_argument_group("optional")
    opt.add_argument("--features", default=None,
                     help="REQUIRED: BEDPE or BED of features to aggregate (e.g. CTCF sites, "
                          "enhancers, custom loops/domains). Loop/TAD pileups run inside "
                          "bulkhic-loops / bulkhic-tads — use this skill for arbitrary features.")
    opt.add_argument("--features-format", default="bedpe", dest="features_format",
                     choices=["bedpe", "bed"], help="Geometry for --features (default bedpe = off-diagonal APA).")
    opt.add_argument("--kind", default=None, choices=["loops", "tads", "boundaries"],
                     help="Pileup geometry (default: bed->tads on-diagonal, bedpe->loops off-diagonal APA).")
    opt.add_argument("--resolution", type=int, default=None,
                     help="Bin size for the pileup. Default: the resolution each sibling "
                          "(loops/insulation) called features at; falls back to 10000.")
    opt.add_argument("--flank", type=int, default=DEFAULT_FLANK,
                     help=f"Flank (bp) around each feature (default {DEFAULT_FLANK}).")
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
    _step(1, "loading Step-3 matrix result + resolving .mcool + features")
    step3_data = json.loads(prev_result_path.read_text())
    matrices = [(m["sample"], Path(m["mcool"])) for m in step3_data.get("matrix", [])]
    if not matrices:
        parser.error("Matrix result has no matrix[] entries.")

    project_dir = prev_result_path.resolve().parent.parent
    output_dir = Path(args.wd) if args.wd else project_dir / "pileup"
    output_dir.mkdir(parents=True, exist_ok=True)
    attach_run_log(output_dir, SKILL_NAME, SKILL_VERSION)

    feature_sets = _discover_feature_sets(args, project_dir)
    params = {"resolution": args.resolution, "flank": args.flank,
              "threads": args.threads,
              "feature_kinds": [fs["kind"] for fs in feature_sets]}

    # No features (no --features, and no sibling loops/insulation calls) → nothing
    # to aggregate. Degrade gracefully (like the other downstream skills) rather
    # than hard-failing: write an empty result so the run completes with a reason.
    if not feature_sets:
        logger.warning(
            "No --features given. bulkhic-pileup is now a general-purpose tool for "
            "ARBITRARY features (pass --features <bedpe/bed> --kind <loops|tads|boundaries>). "
            "Loop APA and TAD pileups are produced automatically by bulkhic-loops / "
            "bulkhic-tads. Writing an empty pileup result.")
        _step(2, "no features available — skipping pileup")
        _step(3, "writing report, reproducibility, and result.json")
        write_report(output_dir, [], params, step3_data, prev_result_path)
        write_reproducibility(output_dir, params, prev_result_path)
        (output_dir / "README.md").write_text(
            f"# {SKILL_NAME} output\n\nStart with `report.md`.\n"
            "No features were available to aggregate (no loops/boundaries). "
            "Re-run with `--features <bedpe/bed>` once loops/insulation produce calls.\n"
            f"`{SKILL_NAME}.log` — full run log.\n"
        )
        print(
            f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
            f"  No features to aggregate (no loops/boundaries available) — nothing piled up.\n"
            f"  Provide --features <bedpe/bed>, or run on deeper data so bulkhic-loops calls loops.\n"
            f"  Report: {output_dir / 'report.md'}\n"
            f"{_SUITE_DONE_BANNER}"
        )
        return

    kinds_desc = ", ".join(f"{fs['kind']} ({fs['format']})" for fs in feature_sets)
    _step(2, f"pileup on {len(matrices)} sample(s) — feature sets: {kinds_desc}")
    results: list[PileupResult] = []
    for fs in feature_sets:
        # Each feature kind goes in its own subdir so loop-APA and boundary
        # pileups never clash on the per-sample <sample>.pileup.<res>.npz name.
        kind, fmt, shared = fs["kind"], fs["format"], fs["shared"]
        res_bp = fs["resolution"] or 10_000
        for name, mcool in matrices:
            feats = fs["per_sample"].get(name) or shared
            if feats is None:
                continue
            results.append(run_pileup(
                name, mcool, res_bp, feats, output_dir / kind / name,
                features_format=fmt, flank=args.flank, nproc=args.threads, kind=kind,
            ))

    if len(matrices) >= 2:
        comp = {}
        for _kind in sorted({r.kind for r in results if r.pileup_npz}):
            _fig = plot_pileup_all(results, output_dir / _kind, _kind)
            if _fig:
                comp[_kind] = str(_fig)
        params["comparison_figs"] = comp
        if comp:
            logger.info("comparison pileup panels: %s", comp)

    _step(3, "writing report, reproducibility, and result.json")
    write_report(output_dir, results, params, step3_data, prev_result_path)
    write_reproducibility(output_dir, params, prev_result_path)
    (output_dir / "README.md").write_text(
        f"# {SKILL_NAME} output\n\nStart with `report.md`.\n"
        "`<kind>/<sample>/*.pileup.*.npz` — aggregate O/E snippet stack "
        "(`<kind>` = loops / boundaries / custom).\n"
        "`<kind>/<sample>/*.pileup.*.png` — APA-style aggregate heatmap.\n"
        f"`{SKILL_NAME}.log` — full run log.\n"
    )

    n_ok = sum(1 for r in results if r.pileup_npz)
    print(
        f"\n{SKILL_NAME} v{SKILL_VERSION} complete:\n"
        f"  Feature sets: {kinds_desc}   ({n_ok}/{len(results)} piled up)\n"
        + "".join(f"  [{r.sample_name}] {r.kind} @ {r.resolution:,} bp — "
                  f"{'pileup ✓' if r.pileup_npz else 'pileup —'}"
                  f"{f'  center-enrichment {r.center_enrichment:.2f}' if r.center_enrichment else ''}\n"
                  for r in results)
        + f"  Report: {output_dir / 'report.md'}\n"
        + _SUITE_DONE_BANNER
    )


if __name__ == "__main__":
    main()
