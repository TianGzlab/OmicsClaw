#!/usr/bin/env python3
"""Single-Cell Preprocessing - QC, normalization, clustering.

Usage:
    python sc_preprocess.py --input <data.h5ad> --output <dir>
    python sc_preprocess.py --demo --output <dir>
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import scanpy as sc
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from omicsclaw.singlecell.adata_utils import store_analysis_metadata
from omicsclaw.singlecell.viz_utils import save_figure
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "singlecell-preprocessing"
SKILL_VERSION = "0.1.0"


def preprocess_singlecell(
    adata,
    min_genes=200,
    min_cells=3,
    max_mt_pct=20.0,
    n_top_hvg=2000,
    n_pcs=50,
    n_neighbors=15,
    leiden_resolution=1.0,
):
    """Minimal single-cell preprocessing pipeline."""
    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # QC filtering
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_genes(adata, min_cells=min_cells)

    # Calculate QC metrics
    adata.var['mt'] = adata.var_names.str.startswith('MT-')
    sc.pp.calculate_qc_metrics(adata, qc_vars=['mt'], percent_top=None, log1p=False, inplace=True)

    # Filter by MT percentage
    adata = adata[adata.obs.pct_counts_mt < max_mt_pct, :].copy()

    # Normalize and log-transform
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # HVG selection
    sc.pp.highly_variable_genes(adata, n_top_genes=n_top_hvg, flavor='seurat')

    # PCA
    sc.pp.scale(adata, max_value=10)
    sc.tl.pca(adata, n_comps=n_pcs, svd_solver='arpack')

    # Neighbors and UMAP
    sc.pp.neighbors(adata, n_neighbors=n_neighbors, n_pcs=n_pcs)
    sc.tl.umap(adata)

    # Leiden clustering
    sc.tl.leiden(adata, resolution=leiden_resolution)

    logger.info(f"Processed: {adata.n_obs} cells, {len(adata.obs['leiden'].unique())} clusters")
    return adata


def generate_figures(adata, output_dir: Path) -> list[str]:
    """Generate QC and analysis figures."""
    figures = []

    # QC violin plots
    try:
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))
        sc.pl.violin(adata, ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'],
                     multi_panel=True, ax=axes, show=False)
        p = save_figure(fig, output_dir, "qc_violin.png")
        figures.append(str(p))
        plt.close()
    except Exception as e:
        logger.warning(f"QC violin plot failed: {e}")

    # HVG plot
    try:
        sc.pl.highly_variable_genes(adata, show=False)
        p = save_figure(plt.gcf(), output_dir, "hvg_plot.png")
        figures.append(str(p))
        plt.close()
    except Exception as e:
        logger.warning(f"HVG plot failed: {e}")

    # PCA variance ratio
    try:
        sc.pl.pca_variance_ratio(adata, n_pcs=50, show=False)
        p = save_figure(plt.gcf(), output_dir, "pca_variance.png")
        figures.append(str(p))
        plt.close()
    except Exception as e:
        logger.warning(f"PCA variance plot failed: {e}")

    # UMAP
    try:
        sc.pl.umap(adata, color='leiden', show=False)
        p = save_figure(plt.gcf(), output_dir, "umap_clusters.png")
        figures.append(str(p))
        plt.close()
    except Exception as e:
        logger.warning(f"UMAP plot failed: {e}")

    return figures


def write_report(output_dir: Path, summary: dict, input_file: str | None, params: dict) -> None:
    """Write comprehensive report."""
    header = generate_report_header(
        title="Single-Cell Preprocessing Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Cells": str(summary['n_cells']),
            "Genes": str(summary['n_genes']),
            "Clusters": str(summary['n_clusters']),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells after QC**: {summary['n_cells']}",
        f"- **Genes after QC**: {summary['n_genes']}",
        f"- **HVGs selected**: {summary['n_hvg']}",
        f"- **Leiden clusters**: {summary['n_clusters']}",
        "",
        "## Parameters\n",
    ]
    for k, v in params.items():
        body_lines.append(f"- `{k}`: {v}")

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)

    # Tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    cluster_counts = summary.get('cluster_counts', {})
    if cluster_counts:
        df = pd.DataFrame([
            {"cluster": k, "n_cells": v, "proportion": round(v / summary['n_cells'] * 100, 2)}
            for k, v in cluster_counts.items()
        ])
        df.to_csv(tables_dir / "cluster_summary.csv", index=False)

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_preprocess.py --input <input.h5ad> --output {output_dir}"
    for k, v in params.items():
        cmd += f" --{k.replace('_', '-')} {v}"
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    try:
        from importlib.metadata import version as _get_version
        env_lines = [f"{pkg}=={_get_version(pkg)}"
                     for pkg in ["scanpy", "anndata", "numpy", "pandas"]]
    except Exception:
        env_lines = ["scanpy", "anndata", "numpy", "pandas"]
    (repro_dir / "environment.yml").write_text("\n".join(env_lines) + "\n")


def get_demo_data():
    """Generate synthetic single-cell data."""
    logger.info("Generating demo single-cell data")
    demo_path = Path(__file__).parent.parent / "data" / "demo" / "pbmc3k_raw.h5ad"
    if demo_path.exists():
        adata = sc.read_h5ad(demo_path)
    else:
        logger.warning("Local demo data not found, downloading from scanpy")
        adata = sc.datasets.pbmc3k()
    return adata, None


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Preprocessing")
    parser.add_argument("--input", dest="input_path")
    parser.add_argument("--output", dest="output_dir", required=True)
    parser.add_argument("--demo", action="store_true")
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
        adata, _ = get_demo_data()
    else:
        if not args.input_path:
            raise ValueError("--input required when not using --demo")
        adata = sc.read_h5ad(args.input_path)

    input_file = args.input_path if not args.demo else None

    # Preprocess
    adata = preprocess_singlecell(
        adata,
        min_genes=args.min_genes,
        min_cells=args.min_cells,
        max_mt_pct=args.max_mt_pct,
        n_top_hvg=args.n_top_hvg,
        n_pcs=args.n_pcs,
        n_neighbors=args.n_neighbors,
        leiden_resolution=args.leiden_resolution,
    )

    # Summary
    n_hvg = adata.var['highly_variable'].sum() if 'highly_variable' in adata.var else 0
    cluster_counts = adata.obs['leiden'].value_counts().to_dict()
    summary = {
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "n_hvg": int(n_hvg),
        "n_clusters": len(adata.obs['leiden'].unique()),
        "cluster_counts": {str(k): int(v) for k, v in cluster_counts.items()},
    }

    params = {
        "min_genes": args.min_genes,
        "min_cells": args.min_cells,
        "max_mt_pct": args.max_mt_pct,
        "n_top_hvg": args.n_top_hvg,
        "n_pcs": args.n_pcs,
        "n_neighbors": args.n_neighbors,
        "leiden_resolution": args.leiden_resolution,
    }

    # Figures
    generate_figures(adata, output_dir)

    # Report
    write_report(output_dir, summary, input_file, params)

    # Save
    output_h5ad = output_dir / "processed.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved to {output_h5ad}")

    # Result JSON
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    # Metadata
    store_analysis_metadata(adata, SKILL_NAME, "scanpy", params)

    print(f"Success: {SKILL_NAME}")
    print(f"  Output: {output_dir}")
    print(f"Preprocessing complete: {summary['n_cells']} cells, {summary['n_clusters']} clusters")


if __name__ == "__main__":
    main()
