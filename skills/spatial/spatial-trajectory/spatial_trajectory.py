#!/usr/bin/env python3
"""Spatial Trajectory — pseudotime and trajectory inference.

Usage:
    python spatial_trajectory.py --input <preprocessed.h5ad> --output <dir>
    python spatial_trajectory.py --input <data.h5ad> --output <dir> --method dpt
    python spatial_trajectory.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=FutureWarning)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import scanpy as sc

from omicsclaw.common.checksums import sha256_file
from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_result_json,
)
from omicsclaw.spatial.adata_utils import (
    ensure_neighbors,
    ensure_pca,
    store_analysis_metadata,
)
from omicsclaw.spatial.viz_utils import save_figure
from omicsclaw.spatial.viz import VizParams, plot_trajectory, plot_features

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-trajectory"
SKILL_VERSION = "0.1.0"




# ---------------------------------------------------------------------------
# Core: DPT (built-in, always available)
# ---------------------------------------------------------------------------


def _run_dpt(
    adata,
    *,
    root_cell: str | None = None,
    n_dcs: int = 10,
) -> dict:
    """Run diffusion pseudotime using scanpy."""

    ensure_pca(adata)
    ensure_neighbors(adata)

    n_comps = min(n_dcs, adata.obsm["X_pca"].shape[1], adata.n_obs - 2)
    sc.tl.diffmap(adata, n_comps=max(n_comps, 2))

    if root_cell and root_cell in adata.obs_names:
        adata.uns["iroot"] = list(adata.obs_names).index(root_cell)
        logger.info("Using provided root cell: %s", root_cell)
    else:
        dc1 = adata.obsm["X_diffmap"][:, 0]
        adata.uns["iroot"] = int(np.argmax(dc1))
        root_cell = adata.obs_names[adata.uns["iroot"]]
        logger.info("Auto-selected root cell: %s (max DC1)", root_cell)

    sc.tl.dpt(adata)

    dpt_vals = adata.obs["dpt_pseudotime"].values
    finite_mask = np.isfinite(dpt_vals)

    cluster_key = "leiden" if "leiden" in adata.obs.columns else None
    per_cluster = {}
    if cluster_key:
        for cl in sorted(adata.obs[cluster_key].unique().tolist(), key=str):
            mask = (adata.obs[cluster_key] == cl) & finite_mask
            if np.sum(mask) > 0:
                per_cluster[str(cl)] = {
                    "mean_pseudotime": float(dpt_vals[mask].mean()),
                    "median_pseudotime": float(np.median(dpt_vals[mask])),
                    "n_cells": int(np.sum(mask)),
                }

    return {
        "method": "dpt",
        "root_cell": root_cell,
        "mean_pseudotime": float(dpt_vals[finite_mask].mean()) if np.any(finite_mask) else 0.0,
        "max_pseudotime": float(dpt_vals[finite_mask].max()) if np.any(finite_mask) else 0.0,
        "n_finite": int(np.sum(finite_mask)),
        "per_cluster": per_cluster,
    }


# ---------------------------------------------------------------------------
# Optional: CellRank
# ---------------------------------------------------------------------------


def _run_cellrank(adata, *, n_states: int = 3) -> dict:
    """Run CellRank for directed trajectory analysis."""
    from omicsclaw.spatial.dependency_manager import require
    require("cellrank", feature="CellRank trajectory inference")
    import cellrank as cr

    kernel = cr.kernels.ConnectivityKernel(adata).compute_transition_matrix()
    estimator = cr.estimators.GPCCA(kernel)
    estimator.compute_schur(n_components=20)
    estimator.compute_macrostates(n_states=n_states)

    macrostates = adata.obs.get("macrostates", None)
    n_macro = macrostates.nunique() if macrostates is not None else 0

    return {
        "method": "cellrank",
        "n_macrostates": n_macro,
        "root_cell": None,
    }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------


def run_trajectory(
    adata,
    *,
    method: str = "dpt",
    root_cell: str | None = None,
    n_states: int = 3,
) -> dict:
    """Run trajectory inference. Returns summary dict."""

    n_cells = adata.n_obs
    n_genes = adata.n_vars
    logger.info("Input: %d cells x %d genes", n_cells, n_genes)

    if method == "cellrank":
        try:
            result = _run_cellrank(adata, n_states=n_states)
        except Exception as exc:
            logger.warning("CellRank failed (%s), falling back to DPT", exc)
            result = _run_dpt(adata, root_cell=root_cell)
    else:
        result = _run_dpt(adata, root_cell=root_cell)

    return {"n_cells": n_cells, "n_genes": n_genes, **result}


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate trajectory figures using the SpatialClaw viz library."""
    figures: list[str] = []

    # Detect available pseudotime column
    pseudotime_key = next(
        (c for c in ("dpt_pseudotime", "velocity_pseudotime", "latent_time")
         if c in adata.obs.columns),
        None,
    )

    # 1. Pseudotime on UMAP ± velocity stream (via plot_trajectory)
    if pseudotime_key:
        try:
            # Explicitly request umap basis so spatial coords are never used here.
            _umap_basis = "umap" if "X_umap" in adata.obsm else None
            fig = plot_trajectory(
                adata,
                VizParams(
                    feature=pseudotime_key,
                    colormap="viridis",
                    title=f"Pseudotime ({pseudotime_key})",
                    basis=_umap_basis,
                ),
                subtype="pseudotime",
            )
            p = save_figure(fig, output_dir, "pseudotime_umap.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate pseudotime UMAP: %s", exc)

    # 2. Pseudotime on spatial
    if pseudotime_key and "spatial" in adata.obsm:
        try:
            fig = plot_features(
                adata,
                VizParams(feature=pseudotime_key, basis="spatial",
                          colormap="viridis", title=f"Pseudotime (spatial)"),
            )
            p = save_figure(fig, output_dir, "pseudotime_spatial.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate pseudotime spatial: %s", exc)

    # 3. Diffusion map embedding
    if "X_diffmap" in adata.obsm:
        try:
            fig = plot_features(
                adata,
                VizParams(
                    feature=pseudotime_key or "leiden",
                    basis="diffmap",
                    colormap="viridis",
                    title="Diffusion Map",
                ),
            )
            p = save_figure(fig, output_dir, "diffmap.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate diffmap: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    """Write report.md, result.json, tables, reproducibility."""

    header = generate_report_header(
        title="Spatial Trajectory Inference Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", "dpt"),
            "Root cell": summary.get("root_cell", "auto"),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Root cell**: {summary.get('root_cell', 'auto')}",
    ]

    if summary["method"] == "dpt":
        body_lines.extend([
            f"- **Mean pseudotime**: {summary.get('mean_pseudotime', 0):.4f}",
            f"- **Max pseudotime**: {summary.get('max_pseudotime', 0):.4f}",
            f"- **Cells with finite DPT**: {summary.get('n_finite', 0)}",
        ])

        per_cluster = summary.get("per_cluster", {})
        if per_cluster:
            body_lines.extend([
                "", "### Pseudotime per Cluster\n",
                "| Cluster | Mean PT | Median PT | Cells |",
                "|---------|---------|-----------|-------|",
            ])
            for cl, info in sorted(per_cluster.items()):
                body_lines.append(
                    f"| {cl} | {info['mean_pseudotime']:.3f} "
                    f"| {info['median_pseudotime']:.3f} | {info['n_cells']} |"
                )

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer
    (output_dir / "report.md").write_text(report)
    logger.info("Wrote %s", output_dir / "report.md")

    summary_for_json = {k: v for k, v in summary.items() if k != "per_cluster"}
    if "per_cluster" in summary:
        summary_for_json["per_cluster"] = summary["per_cluster"]
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary=summary_for_json,
        data={"params": params, **summary_for_json},
        input_checksum=checksum,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    per_cluster = summary.get("per_cluster", {})
    if per_cluster:
        rows = [{"cluster": k, **v} for k, v in per_cluster.items()]
        pd.DataFrame(rows).to_csv(tables_dir / "trajectory_summary.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_trajectory.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        if v is not None:
            cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _ver
    except ImportError:
        pass
    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Run spatial-preprocess --demo and load the resulting processed.h5ad."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_traj_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Running spatial-preprocess --demo into %s", tmp_path)
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed (exit {result.returncode}):\n"
                f"{result.stderr}"
            )
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)
        logger.info("Loaded demo: %d cells x %d genes", adata.n_obs, adata.n_vars)
        return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Trajectory — pseudotime and trajectory inference",
    )
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method", default="dpt", choices=["dpt", "cellrank", "palantir"],
    )
    parser.add_argument("--root-cell", default=None)
    parser.add_argument("--n-states", type=int, default=3)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        input_path = Path(args.input_path)
        if not input_path.exists():
            print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    if "X_pca" not in adata.obsm:
        raise ValueError(
            "PCA not found. Run spatial-preprocess before trajectory analysis:\n"
            "  python omicsclaw.py run preprocess --input data.h5ad --output results/preprocess/"
        )

    params = {
        "method": args.method,
        "root_cell": args.root_cell,
        "n_states": args.n_states,
    }

    summary = run_trajectory(
        adata,
        method=args.method,
        root_cell=args.root_cell,
        n_states=args.n_states,
    )

    generate_figures(adata, output_dir, summary)
    write_report(output_dir, summary, input_file, params)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    if summary["method"] == "dpt":
        print(
            f"Trajectory complete (DPT): root={summary['root_cell']}, "
            f"mean pseudotime={summary.get('mean_pseudotime', 0):.4f}"
        )
    else:
        print(f"Trajectory complete ({summary['method']})")


if __name__ == "__main__":
    main()
