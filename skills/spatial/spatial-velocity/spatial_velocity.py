#!/usr/bin/env python3
"""Spatial Velocity — RNA velocity and cellular dynamics.

Supported methods:
  stochastic  scVelo stochastic model (default)
  deterministic scVelo deterministic steady-state model
  dynamical   scVelo full kinetic model (slowest, most accurate)
  velovi      VELOVI — variational inference RNA velocity (requires scvi-tools)

Requires: pip install scvelo
          pip install -e ".[full]"   (for velovi)

Usage:
    python spatial_velocity.py --input <data.h5ad> --output <dir>
    python spatial_velocity.py --input <data.h5ad> --output <dir> --method dynamical
    python spatial_velocity.py --demo --output <dir>
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
from skills.spatial._lib.dependency_manager import require
from skills.spatial._lib.velocity import (
    run_velocity, SUPPORTED_METHODS,
    validate_velocity_layers, add_demo_velocity_layers,
)
from skills.spatial._lib.viz_utils import save_figure
from skills.spatial._lib.viz import VizParams, plot_features, plot_velocity

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-velocity"
SKILL_VERSION = "0.2.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path, summary: dict) -> list[str]:
    """Generate RNA velocity figures using the SpatialClaw viz library."""
    figures: list[str] = []
    method = summary.get("method", "stochastic")

    # 1. Velocity stream plot (UMAP or spatial)
    if "velocity_graph" in adata.uns:
        for basis_pref, fname in [("umap", "velocity_stream_umap.png"),
                                   ("spatial", "velocity_stream_spatial.png")]:
            key = "X_umap" if basis_pref == "umap" else "spatial"
            if key not in adata.obsm:
                continue
            try:
                fig = plot_velocity(
                    adata,
                    VizParams(basis=basis_pref, colormap="magma",
                              title=f"RNA Velocity Stream ({basis_pref})"),
                    subtype="stream",
                )
                p = save_figure(fig, output_dir, fname)
                figures.append(str(p))
            except Exception as exc:
                logger.warning("Could not generate velocity stream (%s): %s", basis_pref, exc)

    # 2. Phase portrait for top velocity genes
    if "Ms" in adata.layers and "Mu" in adata.layers:
        try:
            fig = plot_velocity(adata, VizParams(), subtype="phase")
            p = save_figure(fig, output_dir, "velocity_phase.png")
            figures.append(str(p))
        except Exception as exc:
            logger.warning("Could not generate velocity phase plot: %s", exc)

    # 3. Velocity speed spatial/UMAP map (fallback feature plot)
    color_key = "velocity_speed" if "velocity_speed" in adata.obs.columns else None
    if color_key:
        for basis_pref, fname in [("umap", "velocity_speed_umap.png"),
                                   ("spatial", "velocity_speed_spatial.png")]:
            key = "X_umap" if basis_pref == "umap" else "spatial"
            if key not in adata.obsm:
                continue
            try:
                fig = plot_features(
                    adata,
                    VizParams(feature=color_key, basis=basis_pref, colormap="magma",
                              title=f"Velocity Speed ({basis_pref})"),
                )
                p = save_figure(fig, output_dir, fname)
                figures.append(str(p))
            except Exception as exc:
                logger.warning("Could not generate velocity speed (%s): %s", basis_pref, exc)

    # 4. PAGA plot
    try:
        fig = plot_velocity(adata, VizParams(), subtype="paga")
        p = save_figure(fig, output_dir, "velocity_paga.png")
        figures.append(str(p))
    except Exception as exc:
        logger.warning("Could not generate PAGA plot: %s", exc)

    return figures


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_report(
    adata,
    output_dir: Path,
    summary: dict,
    input_file: str | None,
    params: dict,
) -> None:
    header = generate_report_header(
        title="Spatial RNA Velocity Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={"Method": summary.get("method", "")},
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells**: {summary['n_cells']}",
        f"- **Genes**: {summary['n_genes']}",
        f"- **Method**: {summary['method']}",
        f"- **Mean velocity speed**: {summary.get('mean_speed', 0):.4f}",
        f"- **Median velocity speed**: {summary.get('median_speed', 0):.4f}",
    ]
    if summary.get("n_velocity_genes") is not None:
        body_lines.append(f"- **Velocity genes**: {summary['n_velocity_genes']}")
    if summary.get("mean_confidence") is not None:
        body_lines.append(f"- **Mean velocity confidence**: {summary['mean_confidence']:.4f}")

    body_lines.extend(["", "## Parameters\n"])
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)
    logger.info("Wrote %s", output_dir / "report.md")

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
        summary={k: v for k, v in summary.items() if isinstance(v, (str, int, float, bool, type(None)))},
        data={"params": params},
        input_checksum=checksum,
    )

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    if "velocity_speed" in adata.obs.columns:
        df = adata.obs[["velocity_speed"]].copy()
        df.index.name = "Cell"
        df.to_csv(tables_dir / "velocity_speed.csv")
    if "velocity_confidence" in adata.obs.columns:
        df = adata.obs[["velocity_confidence"]].copy()
        df.index.name = "Cell"
        df.to_csv(tables_dir / "velocity_confidence.csv")
    if "velocity_pseudotime" in adata.obs.columns:
        df = adata.obs[["velocity_pseudotime"]].copy()
        df.index.name = "Cell"
        df.to_csv(tables_dir / "velocity_pseudotime.csv")

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_velocity.py --input <input.h5ad> --method {params.get('method', 'stochastic')} --output {output_dir}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    from importlib.metadata import version as _ver, PackageNotFoundError
    env_lines: list[str] = []
    for pkg in ["scanpy", "anndata", "numpy", "pandas", "scvelo", "scvi-tools", "velovi", "torch"]:
        try:
            env_lines.append(f"{pkg}=={_ver(pkg)}")
        except PackageNotFoundError:
            pass
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data() -> tuple:
    """Generate demo AnnData with synthetic spliced/unspliced layers."""
    preprocess_script = (
        _PROJECT_ROOT / "skills" / "spatial" / "spatial-preprocess" / "spatial_preprocess.py"
    )
    if not preprocess_script.exists():
        raise FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")

    with tempfile.TemporaryDirectory(prefix="spatial_velo_demo_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        logger.info("Generating demo data via spatial-preprocess ...")
        result = subprocess.run(
            [sys.executable, str(preprocess_script), "--demo", "--output", str(tmp_path)],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"spatial-preprocess --demo failed:\n{result.stderr}"
            )
        processed = tmp_path / "processed.h5ad"
        if not processed.exists():
            raise FileNotFoundError(f"Expected {processed}")
        adata = sc.read_h5ad(processed)
        add_demo_velocity_layers(adata)
        logger.info("Demo: %d cells × %d genes", adata.n_obs, adata.n_vars)
        return adata, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Spatial Velocity — RNA velocity and cellular dynamics\n"
                    "Requires: pip install scvelo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", dest="input_path",
                        help="Input .h5ad file with 'spliced' and 'unspliced' layers")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true",
                        help="Run with synthetic demo data (requires scvelo)")
    parser.add_argument(
        "--method", default="stochastic",
        choices=list(SUPPORTED_METHODS),
        help="Velocity method (default: stochastic)",
    )
    args = parser.parse_args()

    require("scvelo", feature="RNA velocity")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
    elif args.input_path:
        input_path = Path(args.input_path)
        if not input_path.exists():
            print(f"ERROR: Input not found: {input_path}", file=sys.stderr)
            sys.exit(1)
        adata = sc.read_h5ad(args.input_path)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input <file.h5ad> or --demo", file=sys.stderr)
        sys.exit(1)

    params = {"method": args.method}
    summary = run_velocity(adata, method=args.method)

    generate_figures(adata, output_dir, summary)
    write_report(adata, output_dir, summary, input_file, params)

    store_analysis_metadata(
        adata, SKILL_NAME, summary["method"],
        params=params,
    )

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved: %s", h5ad_path)

    print(
        f"Velocity complete ({summary['method']}): "
        f"mean speed = {summary.get('mean_speed', 0):.4f}, "
        f"median speed = {summary.get('median_speed', 0):.4f}"
    )


if __name__ == "__main__":
    main()
