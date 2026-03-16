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
from omicsclaw.spatial.adata_utils import get_spatial_key, store_analysis_metadata
from omicsclaw.spatial.loader import load_spatial_data
from omicsclaw.spatial.viz_utils import save_figure

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "spatial-preprocess"
SKILL_VERSION = "0.1.0"


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------


def preprocess(
    adata,
    *,
    min_genes: int = 200,
    min_cells: int = 3,
    max_mt_pct: float = 20.0,
    n_top_hvg: int = 2000,
    n_pcs: int = 50,
    n_neighbors: int = 15,
    leiden_resolution: float = 1.0,
    species: str = "human",
) -> dict:
    """Run the full preprocessing pipeline. Returns a summary dict."""

    n_cells_raw = adata.n_obs
    n_genes_raw = adata.n_vars
    logger.info("Input: %d cells x %d genes", n_cells_raw, n_genes_raw)

    # QC metrics
    mt_prefix = "MT-" if species == "human" else "mt-"
    adata.var["mt"] = adata.var_names.str.startswith(mt_prefix)
    sc.pp.calculate_qc_metrics(
        adata, qc_vars=["mt"], percent_top=None, log1p=False, inplace=True,
    )

    # Filter
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)
    if max_mt_pct < 100:
        adata = adata[adata.obs["pct_counts_mt"] < max_mt_pct].copy()

    n_cells_filtered = adata.n_obs
    n_genes_filtered = adata.n_vars
    logger.info(
        "After QC: %d cells x %d genes (removed %d cells, %d genes)",
        n_cells_filtered,
        n_genes_filtered,
        n_cells_raw - n_cells_filtered,
        n_genes_raw - n_genes_filtered,
    )

    # Preserve raw counts
    adata.raw = adata.copy()

    # Normalize
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # HVG
    n_hvg = min(n_top_hvg, adata.n_vars - 1)
    sc.pp.highly_variable_genes(adata, n_top_genes=n_hvg, flavor="seurat")
    logger.info("Selected %d highly variable genes", adata.var["highly_variable"].sum())

    # Scale + PCA on HVG
    adata_hvg = adata[:, adata.var["highly_variable"]].copy()
    sc.pp.scale(adata_hvg, max_value=10)
    n_comps = min(n_pcs, adata_hvg.n_vars - 1, adata_hvg.n_obs - 1)
    sc.tl.pca(adata_hvg, n_comps=n_comps)

    # Copy embeddings back
    adata.obsm["X_pca"] = adata_hvg.obsm["X_pca"]
    adata.uns["pca"] = adata_hvg.uns.get("pca", {})
    if "PCs" in adata_hvg.varm:
        adata.varm["PCs"] = np.zeros((adata.n_vars, n_comps))
        hvg_mask = adata.var["highly_variable"].values
        adata.varm["PCs"][hvg_mask] = adata_hvg.varm["PCs"]

    # Neighbors + UMAP + Leiden
    n_pcs_use = min(n_comps, 30)
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs_use)
    sc.tl.umap(adata)
    sc.tl.leiden(adata, resolution=leiden_resolution, flavor="igraph")

    n_clusters = adata.obs["leiden"].nunique()
    logger.info("Leiden clustering: %d clusters (resolution=%.2f)", n_clusters, leiden_resolution)

    store_analysis_metadata(
        adata,
        SKILL_NAME,
        "scanpy_standard",
        params={
            "min_genes": min_genes,
            "min_cells": min_cells,
            "max_mt_pct": max_mt_pct,
            "n_top_hvg": n_hvg,
            "n_pcs": n_comps,
            "n_neighbors": n_neighbors,
            "leiden_resolution": leiden_resolution,
            "species": species,
        },
    )

    summary = {
        "n_cells_raw": n_cells_raw,
        "n_genes_raw": n_genes_raw,
        "n_cells_filtered": n_cells_filtered,
        "n_genes_filtered": n_genes_filtered,
        "n_hvg": int(adata.var["highly_variable"].sum()),
        "n_clusters": n_clusters,
        "has_spatial": get_spatial_key(adata) is not None,
        "cluster_sizes": adata.obs["leiden"].value_counts().to_dict(),
    }
    return adata, summary


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
            fig = plt.gcf()
            p = save_figure(fig, output_dir, "qc_violin.png")
            figures.append(str(p))
    except Exception as e:
        logger.warning("Could not generate QC violin: %s", e)

    # UMAP coloured by leiden
    try:
        if "leiden" in adata.obs.columns and "X_umap" in adata.obsm.keys():
            sc.pl.umap(adata, color="leiden", show=False)
            fig = plt.gcf()
            p = save_figure(fig, output_dir, "umap_leiden.png")
            figures.append(str(p))
    except Exception as e:
        logger.warning("Could not generate UMAP figure: %s", e)

    # Spatial plot coloured by leiden
    try:
        spatial_key = get_spatial_key(adata)
        if spatial_key and "leiden" in adata.obs.columns:
            if "spatial" in adata.uns and len(adata.uns["spatial"]) > 0:
                sc.pl.spatial(adata, color="leiden", show=False)
            else:
                # sc.pl.embedding mandates an "X_" prefix for keys in obsm
                if "X_spatial" not in adata.obsm and spatial_key == "spatial":
                    adata.obsm["X_spatial"] = adata.obsm["spatial"]
                sc.pl.embedding(adata, basis="spatial", color="leiden", show=False)
            fig = plt.gcf()
            p = save_figure(fig, output_dir, "spatial_leiden.png")
            figures.append(str(p))
    except Exception as e:
        logger.warning("Could not generate Spatial figure: %s", e)

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

    # report.md
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
        "",
        "### Cluster sizes\n",
        "| Cluster | Cells |",
        "|---------|-------|",
    ]
    for cluster, size in sorted(summary["cluster_sizes"].items(), key=lambda x: int(x[0])):
        body_lines.append(f"| {cluster} | {size} |")

    body_lines.append("")
    body_lines.append("## Parameters\n")
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    report_path = output_dir / "report.md"
    report_path.write_text(report)
    logger.info("Wrote %s", report_path)

    # result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(
        output_dir,
        skill=SKILL_NAME,
        version=SKILL_VERSION,
        summary=summary,
        data={"params": params, **summary},
        input_checksum=checksum,
    )

    # tables/cluster_summary.csv
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    df = pd.DataFrame(
        list(summary["cluster_sizes"].items()),
        columns=["cluster", "n_cells"],
    )
    df.to_csv(tables_dir / "cluster_summary.csv", index=False)

    # reproducibility
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
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


# ---------------------------------------------------------------------------
# Demo data
# ---------------------------------------------------------------------------


def get_demo_data():
    """Load the built-in demo dataset."""
    demo_path = _PROJECT_ROOT / "examples" / "demo_visium.h5ad"
    if demo_path.exists():
        return sc.read_h5ad(demo_path), str(demo_path)

    # Fallback: generate in-memory
    logger.info("Demo file not found, generating synthetic data")
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))
    from generate_demo_data import generate_demo_visium
    adata = generate_demo_visium()
    return adata, None


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
    parser.add_argument("--min-genes", type=int, default=200)
    parser.add_argument("--min-cells", type=int, default=3)
    parser.add_argument("--max-mt-pct", type=float, default=20.0)
    parser.add_argument("--n-top-hvg", type=int, default=2000)
    parser.add_argument("--n-pcs", type=int, default=50)
    parser.add_argument("--n-neighbors", type=int, default=15)
    parser.add_argument("--leiden-resolution", type=float, default=1.0)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if args.demo:
        adata, input_file = get_demo_data()
        # Override defaults for small demo dataset
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

    params = {
        "data_type": args.data_type,
        "species": args.species,
        "min_genes": args.min_genes,
        "min_cells": args.min_cells,
        "max_mt_pct": args.max_mt_pct,
        "n_top_hvg": args.n_top_hvg,
        "n_pcs": args.n_pcs,
        "n_neighbors": args.n_neighbors,
        "leiden_resolution": args.leiden_resolution,
    }

    # Run pipeline — returns (adata, summary) since internal .copy() may rebind
    adata, summary = preprocess(adata, **{k: v for k, v in params.items() if k not in ("data_type",)})

    # Generate outputs
    generate_figures(adata, output_dir)
    write_report(output_dir, summary, input_file, params)

    # Save processed h5ad
    h5ad_path = output_dir / "processed.h5ad"
    adata.write_h5ad(h5ad_path)
    logger.info("Saved processed data: %s", h5ad_path)

    print(f"Preprocessing complete: {summary['n_cells_filtered']} cells, {summary['n_clusters']} clusters")


if __name__ == "__main__":
    main()
