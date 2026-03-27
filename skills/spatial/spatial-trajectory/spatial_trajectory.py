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
from skills.spatial._lib.adata_utils import store_analysis_metadata
from skills.spatial._lib.trajectory import run_trajectory, SUPPORTED_METHODS
from skills.spatial._lib.viz_utils import save_figure
from skills.spatial._lib.viz import VizParams, plot_trajectory, plot_features

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-trajectory"
SKILL_VERSION = "0.1.0"


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
        from importlib_metadata import version as _ver  # type: ignore
    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_ver(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


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
            "  python omicsclaw.py run spatial-preprocess --input data.h5ad --output results/"
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
