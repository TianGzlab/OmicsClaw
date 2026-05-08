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
import shlex
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
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

from omicsclaw.common.report import (
    generate_report_header,
    generate_report_footer,
    load_result_json,
    write_result_json,
    write_replot_hint,
)
from omicsclaw.common.checksums import sha256_file
from skills.singlecell._lib.adata_utils import canonicalize_singlecell_adata, ensure_input_contract, store_analysis_metadata
from skills.singlecell._lib.export import save_h5ad
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_qc
from skills.singlecell._lib import qc as sc_qc_utils

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-qc"
SKILL_VERSION = "0.2.0"
SCRIPT_REL_PATH = "skills/singlecell/scrna/sc-qc/sc_qc.py"

R_ENHANCED_PLOTS: dict[str, str] = {
    # sc-qc runs before clustering — no embeddings or cell-type compositions yet.
    # plot_feature_violin reads qc_metrics_per_cell.csv written by _export_figure_data.
    "plot_feature_violin": "r_qc_violin.png",
}
QC_METHOD = "qc_metrics"
METHOD_PARAM_DEFAULTS = {
    QC_METHOD: {
        "species": "human",
        "calculate_ribo": True,
    }
}
PUBLIC_PARAM_KEYS = ("species",)


def generate_qc_summary_table(adata) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    """Build QC metric summaries for report, tables, and figure_data."""
    metrics = ["n_genes_by_counts", "total_counts", "pct_counts_mt"]
    if "pct_counts_ribo" in adata.obs.columns:
        metrics.append("pct_counts_ribo")
    metrics = [metric for metric in metrics if metric in adata.obs.columns]

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
    summary_df = pd.DataFrame(summary_data)
    qc_obs = adata.obs.loc[:, metrics].copy()
    qc_obs.insert(0, "cell_id", adata.obs_names.astype(str))
    return summary_stats, summary_df, qc_obs.reset_index(drop=True)


def _build_highest_expr_genes_table(adata, n_top: int = 20) -> pd.DataFrame:
    matrix = adata.X
    mean_expression = np.asarray(matrix.mean(axis=0)).ravel()
    df = pd.DataFrame({"gene": adata.var_names.astype(str), "mean_expression": mean_expression})
    return df.sort_values("mean_expression", ascending=False).head(n_top).reset_index(drop=True)


def _build_barcode_rank_table(adata) -> pd.DataFrame:
    counts = np.sort(np.asarray(adata.obs["total_counts"], dtype=float))[::-1]
    return pd.DataFrame({
        "rank": np.arange(1, len(counts) + 1),
        "total_counts": counts,
        "log10_rank": np.log10(np.arange(1, len(counts) + 1)),
        "log10_total_counts": np.log10(counts + 1),
    })


def _build_qc_correlation_table(adata, metrics: list[str]) -> pd.DataFrame:
    corr = adata.obs.loc[:, metrics].corr(numeric_only=True)
    corr.index.name = "metric"
    return corr.reset_index()


def _prepare_qc_gallery_context(adata, summary: dict, effective_params: dict, output_dir: Path) -> dict:
    summary_stats, summary_df, qc_metrics_df = generate_qc_summary_table(adata)
    summary["qc_metrics"] = summary_stats
    qc_metric_columns = [column for column in qc_metrics_df.columns if column != "cell_id"]
    return {
        "output_dir": Path(output_dir),
        "qc_metric_columns": qc_metric_columns,
        "qc_summary_df": summary_df,
        "qc_metrics_df": qc_metrics_df,
        "highest_expr_df": _build_highest_expr_genes_table(adata),
        "barcode_rank_df": _build_barcode_rank_table(adata),
        "qc_correlation_df": _build_qc_correlation_table(adata, qc_metric_columns),
        "qc_run_summary_df": pd.DataFrame(
            [
                {"metric": "method", "value": "qc_metrics"},
                {"metric": "n_cells", "value": int(summary.get("n_cells", 0))},
                {"metric": "n_genes", "value": int(summary.get("n_genes", 0))},
                {"metric": "species", "value": effective_params.get("species", "human")},
                {"metric": "calculate_ribo", "value": effective_params.get("calculate_ribo", True)},
                {"metric": "expression_source", "value": summary.get("expression_source", "adata.X")},
                {"metric": "gene_name_source", "value": summary.get("gene_name_source", "var_names")},
            ]
        ),
    }


def _build_qc_visualization_recipe(_adata, _summary: dict, _context: dict) -> VisualizationRecipe:
    qc_metric_columns = _context.get("qc_metric_columns", [])
    return VisualizationRecipe(
        recipe_id="standard-sc-qc-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell QC gallery",
        description="Default OmicsClaw QC diagnostic gallery for scRNA-seq quality assessment.",
        plots=[
            PlotSpec(
                plot_id="qc_violin",
                role="overview",
                renderer="qc_violin",
                filename="qc_violin.png",
                title="QC violin plots",
                description="Distribution of core QC metrics across cells.",
                required_obs=["n_genes_by_counts", "total_counts"],
                params={"metrics": qc_metric_columns},
            ),
            PlotSpec(
                plot_id="qc_scatter",
                role="diagnostic",
                renderer="qc_scatter",
                filename="qc_scatter.png",
                title="QC scatter plots",
                description="Pairwise relationships among counts, detected genes, and mitochondrial content.",
                required_obs=["n_genes_by_counts", "total_counts"],
            ),
            PlotSpec(
                plot_id="qc_histograms",
                role="diagnostic",
                renderer="qc_histograms",
                filename="qc_histograms.png",
                title="QC histograms",
                description="Metric distributions with median indicators.",
                required_obs=["n_genes_by_counts", "total_counts"],
                params={"metrics": qc_metric_columns},
            ),
            PlotSpec(
                plot_id="highest_expr_genes",
                role="supporting",
                renderer="highest_expr_genes",
                filename="highest_expr_genes.png",
                title="Highest expressed genes",
                description="Top genes by mean expression to reveal dominant features or contaminants.",
            ),
            PlotSpec(
                plot_id="barcode_rank",
                role="diagnostic",
                renderer="barcode_rank",
                filename="barcode_rank.png",
                title="Barcode-rank curve",
                description="Ranked library-size curve to inspect capture complexity and tail behavior.",
                required_obs=["total_counts"],
            ),
            PlotSpec(
                plot_id="qc_correlation_heatmap",
                role="supporting",
                renderer="qc_correlation_heatmap",
                filename="qc_correlation_heatmap.png",
                title="QC correlation heatmap",
                description="Pairwise Pearson correlations among QC metrics.",
                required_obs=["n_genes_by_counts", "total_counts"],
            ),
        ],
    )


def _gallery_figure_path(output_dir: Path, filename: str) -> Path:
    return Path(output_dir) / "figures" / filename


def _render_qc_violin(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_qc_utils.plot_qc_violin(adata, output_dir, metrics=spec.params.get("metrics"))
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_qc_scatter(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_qc_utils.plot_qc_scatter(adata, output_dir)
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_qc_histograms(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_qc_utils.plot_qc_histograms(adata, output_dir, metrics=spec.params.get("metrics"))
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_highest_expr_genes(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_qc_utils.plot_highest_expr_genes(adata, output_dir, n_top=20)
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_barcode_rank(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_qc_utils.plot_barcode_rank(adata, output_dir)
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


def _render_qc_correlation_heatmap(adata, spec: PlotSpec, context: dict) -> object:
    output_dir = Path(context["output_dir"])
    sc_qc_utils.plot_qc_correlation_heatmap(adata, output_dir, metrics=context.get("qc_metric_columns"))
    path = _gallery_figure_path(output_dir, spec.filename)
    return path if path.exists() else None


QC_GALLERY_RENDERERS = {
    "qc_violin": _render_qc_violin,
    "qc_scatter": _render_qc_scatter,
    "qc_histograms": _render_qc_histograms,
    "highest_expr_genes": _render_highest_expr_genes,
    "barcode_rank": _render_barcode_rank,
    "qc_correlation_heatmap": _render_qc_correlation_heatmap,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")


def _export_figure_data(output_dir: Path, summary: dict, recipe: VisualizationRecipe, artifacts, context: dict) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    available_files: dict[str, str] = {}
    for key, filename, df in (
        ("qc_run_summary", "qc_run_summary.csv", context.get("qc_run_summary_df")),
        ("qc_metrics_summary", "qc_metrics_summary.csv", context.get("qc_summary_df")),
        ("qc_metrics_per_cell", "qc_metrics_per_cell.csv", context.get("qc_metrics_df")),
        ("highest_expr_genes", "highest_expr_genes.csv", context.get("highest_expr_df")),
        ("barcode_rank_curve", "barcode_rank_curve.csv", context.get("barcode_rank_df")),
        ("qc_metric_correlations", "qc_metric_correlations.csv", context.get("qc_correlation_df")),
    ):
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.to_csv(figure_data_dir / filename, index=False)
            available_files[key] = filename

    # Write gene_expression.csv in long format for plot_feature_violin R renderer.
    # Pivots qc_metrics_per_cell wide -> long so metrics appear as "genes" (features).
    qc_df = context.get("qc_metrics_df")
    if isinstance(qc_df, pd.DataFrame) and not qc_df.empty and "cell_id" in qc_df.columns:
        metric_cols = [c for c in qc_df.columns if c != "cell_id"]
        if metric_cols:
            long_rows = []
            for col in metric_cols:
                for _, row in qc_df[["cell_id", col]].iterrows():
                    long_rows.append({"cell_id": row["cell_id"], "gene": col, "expression": row[col]})
            long_df = pd.DataFrame(long_rows)
            long_df.to_csv(figure_data_dir / "gene_expression.csv", index=False)
            available_files["gene_expression"] = "gene_expression.csv"

    manifest = {
        "skill": SKILL_NAME,
        "recipe_id": recipe.recipe_id,
        "method": summary.get("method", "qc_metrics"),
        "available_files": available_files,
        "qc_metric_columns": context.get("qc_metric_columns", []),
        "plots": [
            {
                "plot_id": artifact.plot_id,
                "filename": artifact.filename,
                "status": artifact.status,
                "role": artifact.role,
            }
            for artifact in artifacts
        ],
    }
    _write_figure_data_manifest(output_dir, manifest)
    context["figure_data_files"] = available_files
    context["figure_data_manifest"] = manifest


def generate_qc_figures(adata, output_dir: Path, summary: dict | None = None, *, gallery_context: dict | None = None) -> list[str]:
    context = gallery_context or {}
    if "output_dir" not in context:
        context["output_dir"] = Path(output_dir)
    recipe = _build_qc_visualization_recipe(adata, summary or {}, context)
    artifacts = render_plot_specs(adata, output_dir, recipe, QC_GALLERY_RENDERERS, context=context)
    _export_figure_data(output_dir, summary or {}, recipe, artifacts, context)
    context["recipe"] = recipe
    context["artifacts"] = artifacts
    return [artifact.path for artifact in artifacts if artifact.status == "rendered" and artifact.path]


def export_tables(output_dir: Path, *, gallery_context: dict | None = None) -> list[str]:
    context = gallery_context or {}
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    exported: list[str] = []
    for filename, key in (
        ("qc_metrics_summary.csv", "qc_summary_df"),
        ("qc_metrics_per_cell.csv", "qc_metrics_df"),
        ("highest_expr_genes.csv", "highest_expr_df"),
        ("barcode_rank_curve.csv", "barcode_rank_df"),
        ("qc_metric_correlations.csv", "qc_correlation_df"),
    ):
        df = context.get(key)
        if isinstance(df, pd.DataFrame) and not df.empty:
            path = tables_dir / filename
            df.to_csv(path, index=False)
            exported.append(str(path))
    return exported


def write_qc_report(output_dir: Path, summary: dict, effective_params: dict, input_file: str | None, *, gallery_context: dict | None = None) -> None:
    """Write comprehensive QC report."""
    context = gallery_context or {}
    header = generate_report_header(
        title="Single-Cell QC Report",
        skill_name=SKILL_NAME,
        input_files=[Path(input_file)] if input_file else None,
        extra_metadata={
            "Method": summary.get("method", "qc_metrics"),
            "Cells": str(summary["n_cells"]),
            "Genes": str(summary["n_genes"]),
            "Species": effective_params["species"],
            "Expression source": summary.get("expression_source", "adata.X"),
        },
    )

    # Build body
    body_lines = [
        "## Summary\n",
        f"- **Method**: {summary.get('method', 'qc_metrics')}",
        f"- **Total cells**: {summary['n_cells']:,}",
        f"- **Total genes**: {summary['n_genes']:,}",
        f"- **Species**: {effective_params['species']}",
        f"- **Expression source used for QC**: {summary.get('expression_source', 'adata.X')}",
        f"- **Gene identifiers used for QC**: {summary.get('gene_name_source', 'var_names')}",
        "- **Output object standardization**: Yes; `processed.h5ad` is saved in the OmicsClaw scRNA contract for downstream reuse.",
        "- **Filtering performed**: No; this skill is diagnostic only.",
        "",
        "## Input Validation\n",
    ]

    for warning in summary.get("input_warnings", []):
        body_lines.append(f"- {warning}")

    if not summary.get("input_warnings"):
        body_lines.append("- Input matrix and gene identifiers passed QC preparation checks.")

    body_lines.extend([
        "",
        "## QC Metrics Overview\n",
    ])

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
        "## Effective Parameters\n",
        f"- `species`: {effective_params['species']}",
        f"- `calculate_ribo`: {effective_params.get('calculate_ribo', True)} (fixed current wrapper behavior)",
        "",
    ])

    # Output files section
    body_lines.extend([
        "## Output Files\n",
        "- `figures/manifest.json` — Standard Python gallery manifest",
        "- `figure_data/` — Figure-ready CSV exports for downstream customization",
        "- `tables/qc_metrics_summary.csv` — Summary statistics for all QC metrics",
        "- `tables/qc_metrics_per_cell.csv` — Per-cell QC metric values",
        "- `tables/highest_expr_genes.csv` — Top genes by mean expression",
        "- `processed.h5ad` — AnnData object with QC metrics added to `.obs`, feature tags added to `.var`, and OmicsClaw analysis metadata added to `.uns`",
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
        "  PBMC: < 5%",
        "  Tumor: < 20%",
        "  Heart/Kidney/Liver: < 15%",
        "",
        "**Note**: This skill only calculates and visualizes QC metrics. Use `sc-preprocessing` skill to apply filtering.\n",
    ])

    footer = generate_report_footer()
    report = header + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report, encoding="utf-8")
    logger.info(f"  Saved: report.md")


def build_public_params(effective_params: dict) -> dict:
    """Return the CLI-exposed parameter subset for replay commands."""
    return {key: effective_params[key] for key in PUBLIC_PARAM_KEYS if key in effective_params}


def write_reproducibility(output_dir: Path, public_params: dict, input_file: str | None, *, demo_mode: bool = False) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    command_parts = ["python", SCRIPT_REL_PATH]
    if demo_mode:
        command_parts.append("--demo")
    elif input_file:
        command_parts.extend(["--input", input_file])
    else:
        command_parts.extend(["--input", "<input.h5ad>"])
    command_parts.extend(["--output", str(output_dir)])
    for key, value in public_params.items():
        if value is None or value == "":
            continue
        if key == "species" and value == METHOD_PARAM_DEFAULTS[QC_METHOD]["species"]:
            continue
        if isinstance(value, bool):
            if value:
                command_parts.append(f"--{key.replace('_', '-')}")
            continue
        command_parts.extend([f"--{key.replace('_', '-')}", str(value)])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")

    try:
        from importlib.metadata import version as _get_version
        requirement_lines = [
            f"scanpy=={_get_version('scanpy')}",
            f"anndata=={_get_version('anndata')}",
            f"numpy=={_get_version('numpy')}",
            f"pandas=={_get_version('pandas')}",
        ]
    except Exception:
        requirement_lines = ["scanpy", "anndata", "numpy", "pandas"]
    requirements_text = "\n".join(requirement_lines) + "\n"
    (repro_dir / "requirements.txt").write_text(requirements_text, encoding="utf-8")




def generate_demo_data(species: str = "human"):
    """Generate synthetic single-cell data for demo.

    Creates a realistic AnnData object with varied QC metrics.
    """
    import scanpy as sc

    logger.info("Generating synthetic demo data...")

    try:
        adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
        ensure_input_contract(adata, source_path=str(demo_path) if demo_path else None, standardized=True)
        logger.info(f"Loaded demo data: {demo_path or 'scanpy-pbmc3k'}")
        return adata, demo_path
    except Exception as e:
        logger.warning(f"Failed to load local/scanpy pbmc3k: {e}")
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

        ensure_input_contract(adata, standardized=True)
        logger.info(f"Generated synthetic data: {adata.n_obs} cells x {adata.n_vars} genes")
        return adata, None




def _render_r_enhanced(output_dir, figure_data_dir, r_enhanced):
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


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
    parser.add_argument("--r-enhanced", action="store_true", default=False, help="Generate R-enhanced figures via ggplot2 renderers")
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
        adata = sc_io.smart_load(input_path, skill_name=SKILL_NAME)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")

    # Store parameters
    effective_params = {
        **METHOD_PARAM_DEFAULTS[QC_METHOD],
        "species": args.species,
    }
    public_params = build_public_params(effective_params)
    apply_preflight(
        preflight_sc_qc(
            adata,
            species=effective_params["species"],
            source_path=input_file,
        ),
        logger,
    )

    logger.info("Canonicalizing input into the OmicsClaw scRNA contract...")
    processed_adata, prepared_input, input_contract = canonicalize_singlecell_adata(
        adata,
        species=effective_params["species"],
        standardizer_skill=SKILL_NAME,
    )
    matrix_contract = {
        "X": "raw_counts",
        "raw": "raw_counts_snapshot",
        "layers": {"counts": "raw_counts"},
        "producer_skill": SKILL_NAME,
    }
    processed_adata.uns["omicsclaw_matrix_contract"] = matrix_contract

    logger.info("Calculating QC metrics...")
    processed_adata = sc_qc_utils.calculate_qc_metrics(
        processed_adata,
        species=effective_params["species"],
        calculate_ribo=effective_params["calculate_ribo"],
        inplace=True,
    )
    qc_obs_columns = [
        column
        for column in (
            "n_genes_by_counts",
            "total_counts",
            "pct_counts_mt",
            "pct_counts_ribo",
            "log10_total_counts",
            "log10_n_genes_by_counts",
        )
        if column in processed_adata.obs.columns
    ]

    summary = {
        "method": QC_METHOD,
        "n_cells": int(processed_adata.n_obs),
        "n_genes": int(processed_adata.n_vars),
        "median_genes": float(processed_adata.obs["n_genes_by_counts"].median()),
        "median_counts": float(processed_adata.obs["total_counts"].median()),
        "expression_source": prepared_input.expression_source,
        "gene_name_source": prepared_input.gene_name_source,
        "input_warnings": prepared_input.warnings,
        "qc_obs_columns": qc_obs_columns,
    }

    gallery_context = _prepare_qc_gallery_context(processed_adata, summary, effective_params, output_dir)

    logger.info("Generating QC figures...")
    generate_qc_figures(processed_adata, output_dir, summary, gallery_context=gallery_context)

    logger.info("Exporting tables...")
    export_tables(output_dir, gallery_context=gallery_context)

    logger.info("Writing report...")
    write_qc_report(output_dir, summary, effective_params, input_file, gallery_context=gallery_context)

    write_reproducibility(output_dir, public_params, input_file, demo_mode=args.demo)

    store_analysis_metadata(processed_adata, SKILL_NAME, QC_METHOD, effective_params)
    output_h5ad = output_dir / "processed.h5ad"
    save_h5ad(processed_adata, output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "method": QC_METHOD,
        "params": public_params,
        "effective_params": effective_params,
        "input_preparation": {
            "expression_source": prepared_input.expression_source,
            "gene_name_source": prepared_input.gene_name_source,
            "warnings": prepared_input.warnings,
            "qc_obs_columns": qc_obs_columns,
        },
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        "output_h5ad": "processed.h5ad",
        **summary,
        "visualization": {
            "recipe_id": "standard-sc-qc-gallery",
            "qc_metric_columns": gallery_context.get("qc_metric_columns", []),
            "available_figure_data": gallery_context.get("figure_data_files", {}),
        },
    }
    result_data["next_steps"] = [
        {"skill": "sc-filter", "reason": "Remove low-quality cells based on QC metrics", "priority": "recommended"},
        {"skill": "sc-doublet-detection", "reason": "Optional: detect doublets before filtering", "priority": "optional"},
    ]
    result_data["preprocessing_state_after"] = "qc_computed"
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    write_replot_hint(output_dir, SKILL_NAME, R_ENHANCED_PLOTS)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }

    # Final summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Output directory: {output_dir}")
    print(f"  Cells analyzed: {summary['n_cells']:,}")
    print(f"  Genes: {summary['n_genes']:,}")
    print(f"  Median genes/cell: {summary['median_genes']:.0f}")
    print(f"  Median UMIs/cell: {summary['median_counts']:.0f}")
    print(f"  QC expression source: {summary['expression_source']}")
    if "pct_counts_mt" in summary["qc_metrics"]:
        print(f"  Median MT%: {summary['qc_metrics']['pct_counts_mt']['median']:.2f}%")
    if summary["input_warnings"]:
        print(f"  Input warnings: {len(summary['input_warnings'])}")
    print(f"\nFiles generated:")
    print(f"  - report.md")
    print(f"  - README.md")
    print(f"  - processed.h5ad")
    print(f"  - figures/qc_violin.png")
    print(f"  - figures/qc_scatter.png")
    print(f"  - figures/qc_histograms.png")
    print(f"  - figures/highest_expr_genes.png")
    print(f"  - figures/barcode_rank.png")
    print(f"  - figures/qc_correlation_heatmap.png")
    print(f"  - figures/manifest.json")
    print(f"  - figure_data/manifest.json")
    print(f"  - tables/qc_metrics_summary.csv")
    print(f"  - tables/barcode_rank_curve.csv")
    print(f"  - tables/qc_metric_correlations.csv")
    print(f"  - reproducibility/analysis_notebook.ipynb")
    print(f"\nNote: No cells were filtered. Use sc-filter or sc-preprocessing skill for filtering.")
    print()
    print(">> Next step: Run sc-filter to remove low-quality cells")
    print(f"  python omicsclaw.py run sc-filter --input {output_h5ad} --output <dir>")
    print()
    print("[i] Optional: Run sc-doublet-detection before filtering")
    print(f"  python omicsclaw.py run sc-doublet-detection --input {output_h5ad} --output <dir>")


if __name__ == "__main__":
    main()
