#!/usr/bin/env python3
"""Single-Cell QC - Quality control metrics and visualization.

Usage:
    python sc_qc.py --input <data.h5ad> --output <dir>
    python sc_qc.py --demo --output <dir>
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

SKILL_NAME = "singlecell-qc"
SKILL_VERSION = "0.2.0"


def generate_qc_figures(adata, output_dir: Path) -> list[str]:
    """Generate QC visualization figures.

    Creates violin plots, scatter plots, and histograms for QC metrics.
    """
    figures = []

    # QC violin plots
    try:
        sc_qc_utils.plot_qc_violin(adata, output_dir)
        fig_path = output_dir / "figures" / "qc_violin.png"
        if fig_path.exists():
            figures.append(str(fig_path))
            logger.info("  Saved: qc_violin.png")
    except Exception as e:
        logger.warning(f"QC violin plot failed: {e}")

    # QC scatter plots
    try:
        sc_qc_utils.plot_qc_scatter(adata, output_dir)
        fig_path = output_dir / "figures" / "qc_scatter.png"
        if fig_path.exists():
            figures.append(str(fig_path))
            logger.info("  Saved: qc_scatter.png")
    except Exception as e:
        logger.warning(f"QC scatter plot failed: {e}")

    # QC histograms
    try:
        sc_qc_utils.plot_qc_histograms(adata, output_dir)
        fig_path = output_dir / "figures" / "qc_histograms.png"
        if fig_path.exists():
            figures.append(str(fig_path))
            logger.info("  Saved: qc_histograms.png")
    except Exception as e:
        logger.warning(f"QC histogram plot failed: {e}")

    # Highest expressed genes
    try:
        sc_qc_utils.plot_highest_expr_genes(adata, output_dir, n_top=20)
        fig_path = output_dir / "figures" / "highest_expr_genes.png"
        if fig_path.exists():
            figures.append(str(fig_path))
            logger.info("  Saved: highest_expr_genes.png")
    except Exception as e:
        logger.warning(f"Highest expression plot failed: {e}")

    return figures


def generate_qc_summary_table(adata, output_dir: Path) -> dict:
    """Generate QC metrics summary table.

    Returns summary statistics for all QC metrics.
    """
    metrics = ["n_genes_by_counts", "total_counts", "pct_counts_mt"]
    if "pct_counts_ribo" in adata.obs.columns:
        metrics.append("pct_counts_ribo")

    summary_data = []
    summary_stats = {}

    for metric in metrics:
        if metric not in adata.obs.columns:
            continue

        values = adata.obs[metric]
        stats = {
            "metric": metric,
            "min": float(values.min()),
            "max": float(values.max()),
            "mean": float(values.mean()),
            "median": float(values.median()),
            "std": float(values.std()),
            "q25": float(values.quantile(0.25)),
            "q75": float(values.quantile(0.75)),
        }
        summary_data.append(stats)
        summary_stats[metric] = {
            "median": stats["median"],
            "mean": stats["mean"],
            "min": stats["min"],
            "max": stats["max"],
        }

    # Save to tables directory
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(summary_data)
    df.to_csv(tables_dir / "qc_metrics_summary.csv", index=False)
    logger.info(f"  Saved: tables/qc_metrics_summary.csv")

    # Also save per-cell QC metrics (optional, may be large)
    qc_obs = adata.obs[metrics].copy()
    qc_obs.to_csv(tables_dir / "qc_metrics_per_cell.csv")
    logger.info(f"  Saved: tables/qc_metrics_per_cell.csv")

    return summary_stats


def write_qc_report(output_dir: Path, summary: dict, params: dict, input_file: str | None) -> None:
    """Write comprehensive QC report."""
    header = generate_report_header(
        title="Single-Cell QC Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Cells": str(summary["n_cells"]),
            "Genes": str(summary["n_genes"]),
            "Species": params["species"],
        },
    )

    # Build body
    body_lines = [
        "## Summary\n",
        f"- **Total cells**: {summary['n_cells']:,}",
        f"- **Total genes**: {summary['n_genes']:,}",
        f"- **Species**: {params['species']}",
        "",
        "## QC Metrics Overview\n",
    ]

    # Add metric summaries
    for metric, stats in summary.get("qc_metrics", {}).items():
        metric_name = metric.replace("_", " ").title()
        body_lines.append(f"### {metric_name}\n")
        body_lines.append(f"- **Median**: {stats['median']:.2f}")
        body_lines.append(f"- **Mean**: {stats['mean']:.2f}")
        body_lines.append(f"- **Range**: [{stats['min']:.2f}, {stats['max']:.2f}]")
        body_lines.append("")

    # Gene detection info
    body_lines.extend([
        "## Gene Detection\n",
        f"- **Median genes per cell**: {summary.get('median_genes', 'N/A')}",
        f"- **Median UMIs per cell**: {summary.get('median_counts', 'N/A')}",
        "",
    ])

    # Mitochondrial content
    if "pct_counts_mt" in summary.get("qc_metrics", {}):
        mt_stats = summary["qc_metrics"]["pct_counts_mt"]
        body_lines.extend([
            "## Mitochondrial Content\n",
            f"- **Median MT%**: {mt_stats['median']:.2f}%",
            f"- **Mean MT%**: {mt_stats['mean']:.2f}%",
            f"- **Range**: [{mt_stats['min']:.2f}%, {mt_stats['max']:.2f}%]",
            "",
        ])

    # Ribosomal content (if calculated)
    if "pct_counts_ribo" in summary.get("qc_metrics", {}):
        ribo_stats = summary["qc_metrics"]["pct_counts_ribo"]
        body_lines.extend([
            "## Ribosomal Content\n",
            f"- **Median Ribosomal%**: {ribo_stats['median']:.2f}%",
            f"- **Mean Ribosomal%**: {ribo_stats['mean']:.2f}%",
            "",
        ])

    # Parameters section
    body_lines.extend([
        "## Parameters\n",
        f"- `species`: {params['species']}",
        f"- `calculate_ribo`: {params.get('calculate_ribo', True)}",
        "",
    ])

    # Output files section
    body_lines.extend([
        "## Output Files\n",
        "### Figures\n",
        "- `figures/qc_violin.png` — Violin plots of QC metrics",
        "- `figures/qc_scatter.png` — Scatter plots showing relationships between metrics",
        "- `figures/qc_histograms.png` — Distribution histograms of QC metrics",
        "- `figures/highest_expr_genes.png` — Top 20 highest expressed genes",
        "",
        "### Tables\n",
        "- `tables/qc_metrics_summary.csv` — Summary statistics for all QC metrics",
        "- `tables/qc_metrics_per_cell.csv` — Per-cell QC metric values",
        "",
        "### Data\n",
        "- `qc_checked.h5ad` — AnnData object with QC metrics added to `.obs`",
        "",
    ])

    # Interpretation guidance
    body_lines.extend([
        "## Interpretation Guidance\n",
        "### N Genes by Counts",
        "- Low values (< 200) may indicate empty droplets or low-quality cells",
        "- High values (> 5000-6000) may indicate doublets",
        "",
        "### Total Counts (UMIs)",
        "- Low counts may indicate poor capture efficiency",
        "- Very high counts may indicate doublets",
        "",
        "### Mitochondrial Percentage",
        "- High MT% (> 10-20%) indicates stressed or dying cells",
        "- Thresholds vary by tissue type:",
        "  - PBMC: < 5%",
        "  - Tumor: < 20%",
        "  - Heart/Kidney/Liver: < 15%",
        "",
        "**Note**: This skill only calculates and visualizes QC metrics. Use `sc-preprocessing` skill to apply filtering.\n",
    ])

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)
    logger.info(f"  Saved: report.md")


def generate_demo_data(species: str = "human"):
    """Generate synthetic single-cell data for demo.

    Creates a realistic AnnData object with varied QC metrics.
    """
    import scanpy as sc

    logger.info("Generating synthetic demo data...")

    # Try to load from local demo data first
    demo_path = _PROJECT_ROOT / "examples" / "pbmc3k.h5ad"
    if demo_path.exists():
        logger.info(f"Loading local demo data: {demo_path}")
        return sc.read_h5ad(demo_path), None

    # Fall back to scanpy's built-in dataset
    logger.info("Downloading pbmc3k from scanpy datasets...")
    try:
        adata = sc.datasets.pbmc3k()
        logger.info(f"Loaded pbmc3k: {adata.n_obs} cells x {adata.n_vars} genes")
        return adata, None
    except Exception as e:
        logger.warning(f"Failed to load pbmc3k: {e}")
        # Generate synthetic data as last resort
        logger.info("Generating synthetic data...")

        np.random.seed(42)
        n_cells = 500
        n_genes = 1000

        # Create count matrix with realistic distribution
        counts = np.random.negative_binomial(2, 0.02, size=(n_cells, n_genes))

        # Create AnnData
        adata = sc.AnnData(
            X=counts.astype(np.float32),
            obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
            var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
        )

        # Add some MT- genes for human species
        mt_genes = ["MT-1", "MT-2", "MT-3", "MT-4", "MT-5"]
        gene_names = list(adata.var_names)
        for i, mt_gene in enumerate(mt_genes):
            if i < len(gene_names):
                gene_names[i] = mt_gene
        adata.var_names = gene_names

        logger.info(f"Generated synthetic data: {adata.n_obs} cells x {adata.n_vars} genes")
        return adata, None


def main():
    parser = argparse.ArgumentParser(
        description="Single-Cell QC — Quality control metrics and visualization"
    )
    parser.add_argument("--input", dest="input_path", help="Input AnnData file (.h5ad)")
    parser.add_argument("--output", dest="output_dir", required=True, help="Output directory")
    parser.add_argument("--demo", action="store_true", help="Run with demo data")
    parser.add_argument(
        "--species",
        default="human",
        choices=["human", "mouse"],
        help="Species for mitochondrial gene detection (default: human)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    if args.demo:
        adata, _ = generate_demo_data(species=args.species)
        input_file = None
    else:
        if not args.input_path:
            parser.error("--input required when not using --demo")
        input_path = Path(args.input_path)
        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        logger.info(f"Loading data from: {input_path}")
        adata = sc_io.smart_load(input_path)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Store parameters
    params = {
        "species": args.species,
        "calculate_ribo": True,
    }

    # Calculate QC metrics
    logger.info("Calculating QC metrics...")
    adata = sc_qc_utils.calculate_qc_metrics(
        adata,
        species=args.species,
        calculate_ribo=True,
        inplace=True,
    )

    # Generate QC summary table
    logger.info("Generating QC summary table...")
    qc_metrics_summary = generate_qc_summary_table(adata, output_dir)

    # Generate figures
    logger.info("Generating QC figures...")
    figures = generate_qc_figures(adata, output_dir)

    # Build summary dict
    summary = {
        "n_cells": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "median_genes": float(adata.obs["n_genes_by_counts"].median()),
        "median_counts": float(adata.obs["total_counts"].median()),
        "qc_metrics": qc_metrics_summary,
    }

    # Write report
    logger.info("Writing report...")
    write_qc_report(output_dir, summary, params, input_file)

    # Save AnnData with QC metrics
    output_h5ad = output_dir / "qc_checked.h5ad"
    adata.write_h5ad(output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Write reproducibility info
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    cmd_parts = [f"python sc_qc.py --output {output_dir}"]
    if input_file:
        cmd_parts.append(f"--input {input_file}")
    cmd_parts.append(f"--species {args.species}")
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{' '.join(cmd_parts)}\n")

    try:
        from importlib.metadata import version as _get_version
        env_lines = [
            f"scanpy=={_get_version('scanpy')}",
            f"anndata=={_get_version('anndata')}",
            f"numpy=={_get_version('numpy')}",
            f"pandas=={_get_version('pandas')}",
        ]
    except Exception:
        env_lines = ["scanpy", "anndata", "numpy", "pandas"]
    (repro_dir / "requirements.txt").write_text("\n".join(env_lines) + "\n")

    # Write result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, {"params": params}, checksum)

    # Final summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Cells analyzed: {summary['n_cells']:,}")
    print(f"  Genes: {summary['n_genes']:,}")
    print(f"  Median genes/cell: {summary['median_genes']:.0f}")
    print(f"  Median UMIs/cell: {summary['median_counts']:.0f}")
    if "pct_counts_mt" in qc_metrics_summary:
        print(f"  Median MT%: {qc_metrics_summary['pct_counts_mt']['median']:.2f}%")
    print(f"\nFiles generated:")
    print(f"  - report.md")
    print(f"  - qc_checked.h5ad")
    print(f"  - figures/qc_violin.png")
    print(f"  - figures/qc_scatter.png")
    print(f"  - figures/qc_histograms.png")
    print(f"  - tables/qc_metrics_summary.csv")
    print(f"\nNote: No cells were filtered. Use sc-preprocessing skill for filtering.")


if __name__ == "__main__":
    main()
