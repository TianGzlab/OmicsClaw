#!/usr/bin/env python3
"""Single-Cell Filter - Filter cells and genes based on QC metrics.

Usage:
    python sc_filter.py --input <data.h5ad> --output <dir>
    python sc_filter.py --input <data.h5ad> --output <dir> --tissue pbmc
    python sc_filter.py --demo --output <dir>
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# Fix for anndata >= 0.11 with StringArray
try:
    import anndata
    anndata.settings.allow_write_nullable_strings = True
except Exception:
    pass

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from omicsclaw.common.report import generate_report_header, generate_report_footer, write_result_json
from omicsclaw.common.checksums import sha256_file
from skills.singlecell._lib.viz_utils import save_figure
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib import qc as sc_qc_utils

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "singlecell-filter"
SKILL_VERSION = "0.2.0"


def filter_cells_and_genes(
    adata,
    min_genes: int = 200,
    max_genes: int | None = None,
    min_counts: int | None = None,
    max_counts: int | None = None,
    max_mt_percent: float | None = None,
    min_cells: int = 3,
    tissue: str | None = None,
) -> tuple:
    """Filter cells and genes based on QC metrics.

    Returns:
        (filtered_adata, filter_summary)
    """
    import scanpy as sc

    n_cells_before = adata.n_obs
    n_genes_before = adata.n_vars

    # Use tissue-specific thresholds if provided
    if tissue:
        thresholds = sc_qc_utils.get_tissue_qc_thresholds(tissue)
        min_genes = thresholds.get("min_genes", min_genes)
        max_genes = thresholds.get("max_genes", max_genes)
        max_mt_percent = thresholds.get("max_mt", max_mt_percent)
        logger.info(f"Using tissue-specific thresholds for {tissue}")

    logger.info(f"Filtering cells...")
    logger.info(f"  Starting with {n_cells_before} cells")

    # Create filter mask
    keep_cells = np.ones(adata.n_obs, dtype=bool)
    filter_stats = {}

    # Filter by n_genes
    if min_genes is not None:
        mask = adata.obs['n_genes_by_counts'] >= min_genes
        n_removed = (~mask).sum()
        keep_cells &= mask
        filter_stats['min_genes_removed'] = int(n_removed)
        logger.info(f"  Removed {n_removed} cells with < {min_genes} genes")

    if max_genes is not None:
        mask = adata.obs['n_genes_by_counts'] <= max_genes
        n_removed = (~mask).sum()
        keep_cells &= mask
        filter_stats['max_genes_removed'] = int(n_removed)
        logger.info(f"  Removed {n_removed} cells with > {max_genes} genes")

    # Filter by total counts
    if min_counts is not None:
        mask = adata.obs['total_counts'] >= min_counts
        n_removed = (~mask).sum()
        keep_cells &= mask
        filter_stats['min_counts_removed'] = int(n_removed)
        logger.info(f"  Removed {n_removed} cells with < {min_counts} counts")

    if max_counts is not None:
        mask = adata.obs['total_counts'] <= max_counts
        n_removed = (~mask).sum()
        keep_cells &= mask
        filter_stats['max_counts_removed'] = int(n_removed)
        logger.info(f"  Removed {n_removed} cells with > {max_counts} counts")

    # Filter by mitochondrial percentage
    if max_mt_percent is not None and 'pct_counts_mt' in adata.obs.columns:
        mask = adata.obs['pct_counts_mt'] <= max_mt_percent
        n_removed = (~mask).sum()
        keep_cells &= mask
        filter_stats['mt_removed'] = int(n_removed)
        logger.info(f"  Removed {n_removed} cells with > {max_mt_percent}% MT")

    # Filter by MAD outliers if available
    if 'outlier' in adata.obs.columns:
        n_outliers = adata.obs['outlier'].sum()
        keep_cells &= ~adata.obs['outlier']
        filter_stats['outliers_removed'] = int(n_outliers)
        logger.info(f"  Removed {n_outliers} MAD outlier cells")

    # Apply cell filter
    adata_filtered = adata[keep_cells, :].copy()
    n_cells_after = adata_filtered.n_obs

    logger.info(f"  Retained {n_cells_after} cells ({100*n_cells_after/n_cells_before:.1f}%)")

    # Filter genes
    logger.info(f"Filtering genes...")
    logger.info(f"  Starting with {n_genes_before} genes")

    sc.pp.filter_genes(adata_filtered, min_cells=min_cells)
    n_genes_after = adata_filtered.n_vars

    logger.info(f"  Retained {n_genes_after} genes ({100*n_genes_after/n_genes_before:.1f}%)")

    # Build summary
    summary = {
        "n_cells_before": n_cells_before,
        "n_cells_after": n_cells_after,
        "cells_retained_pct": round(100 * n_cells_after / n_cells_before, 2),
        "n_genes_before": n_genes_before,
        "n_genes_after": n_genes_after,
        "genes_retained_pct": round(100 * n_genes_after / n_genes_before, 2),
        "filter_stats": filter_stats,
    }

    return adata_filtered, summary


def generate_filter_figures(adata_before, adata_after, output_dir: Path) -> list[str]:
    """Generate before/after filter comparison figures."""
    figures = []
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    # QC comparison violin
    try:
        fig, axes = plt.subplots(1, 3, figsize=(12, 4))

        metrics = ['n_genes_by_counts', 'total_counts', 'pct_counts_mt']
        for i, metric in enumerate(metrics):
            if metric in adata_before.obs.columns:
                data = pd.DataFrame({
                    'Before': adata_before.obs[metric],
                    'After': adata_after.obs[metric]
                })
                data.boxplot(ax=axes[i])
                axes[i].set_title(metric.replace('_', ' ').title())
                axes[i].set_ylabel('Value')

        fig.tight_layout()
        fig_path = figures_dir / "filter_comparison.png"
        fig.savefig(fig_path, dpi=300, bbox_inches='tight')
        figures.append(str(fig_path))
        plt.close()
        logger.info(f"  Saved: filter_comparison.png")
    except Exception as e:
        logger.warning(f"Filter comparison plot failed: {e}")

    # Retention summary
    try:
        fig, ax = plt.subplots(figsize=(6, 4))
        retention_data = {
            'Cells': [adata_before.n_obs, adata_after.n_obs],
            'Genes': [adata_before.n_vars, adata_after.n_vars],
        }
        x = np.arange(2)
        width = 0.35

        bars1 = ax.bar(x - width/2, [adata_before.n_obs, adata_before.n_vars], width, label='Before', color='lightcoral')
        bars2 = ax.bar(x + width/2, [adata_after.n_obs, adata_after.n_vars], width, label='After', color='lightgreen')

        ax.set_ylabel('Count')
        ax.set_xticks(x)
        ax.set_xticklabels(['Cells', 'Genes'])
        ax.legend()
        ax.set_title('Before vs After Filtering')

        fig.tight_layout()
        fig_path = figures_dir / "filter_summary.png"
        fig.savefig(fig_path, dpi=300, bbox_inches='tight')
        figures.append(str(fig_path))
        plt.close()
        logger.info(f"  Saved: filter_summary.png")
    except Exception as e:
        logger.warning(f"Filter summary plot failed: {e}")

    return figures


def write_filter_report(output_dir: Path, summary: dict, params: dict, input_file: str | None) -> None:
    """Write comprehensive filter report."""
    header = generate_report_header(
        title="Single-Cell Filter Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Cells Retained": f"{summary['cells_retained_pct']}%",
            "Genes Retained": f"{summary['genes_retained_pct']}%",
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Cells before**: {summary['n_cells_before']:,}",
        f"- **Cells after**: {summary['n_cells_after']:,}",
        f"- **Retention rate**: {summary['cells_retained_pct']}%",
        "",
        f"- **Genes before**: {summary['n_genes_before']:,}",
        f"- **Genes after**: {summary['n_genes_after']:,}",
        f"- **Retention rate**: {summary['genes_retained_pct']}%",
        "",
        "## Filter Parameters\n",
    ]

    if params.get('tissue'):
        body_lines.append(f"- **Tissue-specific thresholds**: {params['tissue']}")
    body_lines.append(f"- **Min genes per cell**: {params['min_genes']}")
    if params.get('max_genes'):
        body_lines.append(f"- **Max genes per cell**: {params['max_genes']}")
    if params.get('max_mt_percent'):
        body_lines.append(f"- **Max MT%**: {params['max_mt_percent']}%")
    body_lines.append(f"- **Min cells per gene**: {params['min_cells']}")

    # Filter breakdown
    body_lines.extend(["", "## Cells Removed By Filter\n"])
    for key, value in summary.get('filter_stats', {}).items():
        label = key.replace('_removed', '').replace('_', ' ').title()
        body_lines.append(f"- **{label}**: {value:,}")

    # Interpretation
    body_lines.extend([
        "",
        "## Interpretation\n",
    ])

    retention = summary['cells_retained_pct']
    if retention < 50:
        body_lines.append("⚠️ **Warning**: Low retention rate (< 50%). Check QC thresholds and data quality.")
    elif retention < 70:
        body_lines.append("⚡ **Note**: Moderate retention rate (50-70%). Review filtering parameters.")
    else:
        body_lines.append("✅ Good retention rate (> 70%).")

    body_lines.extend([
        "",
        "## Output Files\n",
        "- `filtered.h5ad` — Filtered AnnData object",
        "- `figures/filter_comparison.png` — Before/after QC comparison",
        "- `figures/filter_summary.png` — Cell/gene retention summary",
        "- `tables/filter_stats.csv` — Detailed filtering statistics",
        "",
    ])

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


def generate_demo_data():
    """Generate demo data with QC metrics."""
    import scanpy as sc

    logger.info("Generating demo data...")

    # Try scanpy's built-in dataset
    try:
        adata = sc.datasets.pbmc3k()
        logger.info(f"Loaded pbmc3k: {adata.n_obs} cells x {adata.n_vars} genes")
    except Exception:
        # Synthetic fallback
        np.random.seed(42)
        n_cells, n_genes = 500, 1000
        counts = np.random.negative_binomial(2, 0.02, size=(n_cells, n_genes))
        adata = sc.AnnData(
            X=counts.astype(np.float32),
            obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
            var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
        )

    return adata


def main():
    parser = argparse.ArgumentParser(description="Single-Cell Filter")
    parser.add_argument("--input", dest="input_path", help="Input AnnData file (.h5ad)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument("--min-genes", type=int, default=200, help="Min genes per cell")
    parser.add_argument("--max-genes", type=int, default=None, help="Max genes per cell")
    parser.add_argument("--min-counts", type=int, default=None, help="Min counts per cell")
    parser.add_argument("--max-counts", type=int, default=None, help="Max counts per cell")
    parser.add_argument("--max-mt-percent", type=float, default=20.0, help="Max mitochondrial %%")
    parser.add_argument("--min-cells", type=int, default=3, help="Min cells per gene")
    parser.add_argument("--tissue", type=str, default=None,
                        choices=["pbmc", "brain", "tumor", "heart", "kidney", "liver", "lung"],
                        help="Use tissue-specific thresholds")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if args.demo:
        adata = generate_demo_data()
        input_file = None
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")
        logger.info(f"Loading: {input_path}")
        adata = sc_io.smart_load(input_path)
        input_file = str(input_path)

    # Calculate QC metrics if not present
    if 'n_genes_by_counts' not in adata.obs.columns:
        logger.info("Calculating QC metrics...")
        adata = sc_qc_utils.calculate_qc_metrics(adata, inplace=True)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Store original for comparison
    adata_before = adata.copy()

    # Parameters
    params = {
        "min_genes": args.min_genes,
        "max_genes": args.max_genes,
        "min_counts": args.min_counts,
        "max_counts": args.max_counts,
        "max_mt_percent": args.max_mt_percent,
        "min_cells": args.min_cells,
        "tissue": args.tissue,
    }

    # Apply filtering
    adata_filtered, summary = filter_cells_and_genes(
        adata,
        min_genes=args.min_genes,
        max_genes=args.max_genes,
        min_counts=args.min_counts,
        max_counts=args.max_counts,
        max_mt_percent=args.max_mt_percent,
        min_cells=args.min_cells,
        tissue=args.tissue,
    )

    # Generate figures
    logger.info("Generating figures...")
    figures = generate_filter_figures(adata_before, adata_filtered, output_dir)

    # Save filter stats table
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)

    filter_stats_df = pd.DataFrame([
        {"metric": k, "value": v}
        for k, v in summary["filter_stats"].items()
    ])
    filter_stats_df.to_csv(tables_dir / "filter_stats.csv", index=False)

    # Write report
    logger.info("Writing report...")
    write_filter_report(output_dir, summary, params, input_file)

    # Save filtered data
    output_h5ad = output_dir / "filtered.h5ad"
    adata_filtered.write_h5ad(output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd = f"python sc_filter.py --output {output_dir}"
    if input_file:
        cmd += f" --input {input_file}"
    cmd += f" --min-genes {args.min_genes} --max-mt-percent {args.max_mt_percent} --min-cells {args.min_cells}"
    if args.tissue:
        cmd += f" --tissue {args.tissue}"

    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{cmd}\n")

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Cells: {summary['n_cells_before']:,} → {summary['n_cells_after']:,} ({summary['cells_retained_pct']}%)")
    print(f"  Genes: {summary['n_genes_before']:,} → {summary['n_genes_after']:,} ({summary['genes_retained_pct']}%)")
    print(f"  Output: {output_dir}")


if __name__ == "__main__":
    main()
