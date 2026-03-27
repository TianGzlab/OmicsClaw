#!/usr/bin/env python3
"""Spatial Preprocess — load, QC, normalize, embed, and cluster spatial data.

Usage:
    python spatial_preprocess.py --input <data.h5ad> --output <dir>
    python spatial_preprocess.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

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
from skills.spatial._lib.adata_utils import get_spatial_key
from skills.spatial._lib.loader import load_spatial_data
from skills.spatial._lib.preprocessing import preprocess
from skills.spatial._lib.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-preprocess"
SKILL_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate QC, UMAP, and Spatial figures."""
    import matplotlib.pyplot as plt

    figures = []

    # QC violin
    try:
        keys_to_plot = [k for k in ["n_genes_by_counts", "total_counts", "pct_counts_mt"] if k in adata.obs.columns]
        if keys_to_plot:
            sc.pl.violin(adata, keys_to_plot, jitter=0.4, multi_panel=True, show=False)
            p = save_figure(plt.gcf(), output_dir, "qc_violin.png")
            figures.append(str(p))
            plt.close("all")
    except Exception as e:
        logger.warning("Could not generate QC violin: %s", e)

    # UMAP coloured by leiden
    try:
        if "leiden" in adata.obs.columns and "X_umap" in adata.obsm.keys():
            sc.pl.umap(adata, color="leiden", show=False)
            p = save_figure(plt.gcf(), output_dir, "umap_leiden.png")
            figures.append(str(p))
            plt.close("all")
    except Exception as e:
        logger.warning("Could not generate UMAP figure: %s", e)

    # Spatial plot coloured by leiden
    try:
        spatial_key = get_spatial_key(adata)
        if spatial_key and "leiden" in adata.obs.columns:
            if "spatial" in adata.uns and len(adata.uns["spatial"]) > 0:
                sc.pl.spatial(adata, color="leiden", show=False)
            else:
                if "X_spatial" not in adata.obsm and spatial_key == "spatial":
                    adata.obsm["X_spatial"] = adata.obsm["spatial"]
                sc.pl.embedding(adata, basis="spatial", color="leiden", show=False)
            p = save_figure(plt.gcf(), output_dir, "spatial_leiden.png")
            figures.append(str(p))
            plt.close("all")
    except Exception as e:
        logger.warning("Could not generate Spatial figure: %s", e)

    return figures


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write report.md, result.json, tables, reproducibility."""
    header = generate_report_header(
        title="Spatial Preprocessing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Species": params.get("species", "human"),
            "Data type": params.get("data_type", "generic"),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Raw**: {summary['n_cells_raw']} cells x {summary['n_genes_raw']} genes",
        f"- **After QC**: {summary['n_cells_filtered']} cells x {summary['n_genes_filtered']} genes",
        f"- **HVG selected**: {summary['n_hvg']}",
        f"- **Leiden clusters**: {summary['n_clusters']}",
        f"- **Spatial coordinates**: {'Yes' if summary['has_spatial'] else 'No'}",
        f"- **Suggested PCs**: {summary.get('n_pcs_suggested', 'N/A')}",
    ]
    if summary.get("tissue_preset"):
        body_lines.append(f"- **Tissue preset**: {summary['tissue_preset']}")
    if summary.get("multi_resolution"):
        body_lines.append("")
        body_lines.append("### Multi-resolution clustering\n")
        body_lines.append("| Resolution | Clusters |")
        body_lines.append("|------------|----------|")
        for res, n_cl in summary["multi_resolution"].items():
            body_lines.append(f"| {res} | {n_cl} |")
    body_lines.append("")
    body_lines.append("### Cluster sizes\n")
    body_lines.append("| Cluster | Cells |")
    body_lines.append("|---------|-------|")
    for cluster, size in sorted(summary["cluster_sizes"].items(), key=lambda x: int(x[0])):
        body_lines.append(f"| {cluster} | {size} |")

    body_lines.append("")
    body_lines.append("## Parameters\n")
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer)

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, skill=SKILL_NAME, version=SKILL_VERSION,
                      summary=summary, data={"params": params, **summary}, input_checksum=checksum)

    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    pd.DataFrame(
        list(summary["cluster_sizes"].items()), columns=["cluster", "n_cells"],
    ).to_csv(tables_dir / "cluster_summary.csv", index=False)

    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)
    cmd = f"python spatial_preprocess.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
    except ImportError:
        from importlib_metadata import version as _get_version  # type: ignore
    env_lines = []
    for pkg in ["scanpy", "anndata", "squidpy", "numpy", "pandas", "matplotlib"]:
        try:
            env_lines.append(f"{pkg}=={_get_version(pkg)}")
        except Exception:
            env_lines.append(f"{pkg}=?")
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data():
    """Load the built-in demo dataset."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_visium.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path), str(demo_path)

    logger.info("Demo file not found, generating synthetic data")
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
    from generate_demo_data import generate_demo_visium
    return generate_demo_visium(), None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Spatial Preprocess")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--data-type", default="generic")
    parser.add_argument("--species", default="human")
    parser.add_argument("--min-genes", type=int, default=0)
    parser.add_argument("--min-cells", type=int, default=0)
    parser.add_argument("--max-mt-pct", type=float, default=20.0)
    parser.add_argument("--max-genes", type=int, default=0,
                        help="Max genes per cell (0=no limit, auto-set by --tissue)")
    parser.add_argument("--tissue", default=None,
                        help="Tissue type for QC presets: pbmc, brain, heart, tumor, "
                             "liver, kidney, lung, gut, skin, muscle")
    parser.add_argument("--n-top-hvg", type=int, default=2000)
    parser.add_argument("--n-pcs", type=int, default=30)
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--leiden-resolution", type=float, default=0.5)
    parser.add_argument("--resolutions", default=None,
                        help="Comma-separated resolutions to explore (e.g., 0.4,0.6,0.8,1.0)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.demo:
        adata, input_file = get_demo_data()
        if args.min_genes == 200:
            args.min_genes = 5
        if args.n_top_hvg == 2000:
            args.n_top_hvg = 50
        if args.n_pcs == 50:
            args.n_pcs = 15
    elif args.input_path:
        adata = load_spatial_data(args.input_path, data_type=args.data_type)
        input_file = args.input_path
    else:
        print("ERROR: Provide --input or --demo", file=sys.stderr)
        sys.exit(1)

    # Parse resolutions
    resolutions = None
    if args.resolutions:
        resolutions = [float(r.strip()) for r in args.resolutions.split(",")]

    params = {
        "data_type": args.data_type, "species": args.species,
        "min_genes": args.min_genes, "min_cells": args.min_cells,
        "max_mt_pct": args.max_mt_pct, "max_genes": args.max_genes,
        "tissue": args.tissue,
        "n_top_hvg": args.n_top_hvg, "n_pcs": args.n_pcs,
        "n_neighbors": args.n_neighbors,
        "leiden_resolution": args.leiden_resolution,
    }

    # Run pipeline via _lib
    adata, summary = preprocess(
        adata,
        resolutions=resolutions,
        **{k: v for k, v in params.items() if k not in ("data_type",)},
    )

    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params)

    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(f"Preprocessing complete: {summary['n_cells_filtered']} cells, {summary['n_clusters']} clusters")


if __name__ == "__main__":
    main()
