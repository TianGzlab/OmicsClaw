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

_SDK_ANCHOR = next(
    (p for p in Path(__file__).resolve().parents if (p / "skills" / "_sdk" / "__init__.py").is_file()),
    None,
)
if _SDK_ANCHOR is not None and str(_SDK_ANCHOR) not in sys.path:
    sys.path.insert(0, str(_SDK_ANCHOR))

from skills._sdk.report import (
    generate_report_header,
    generate_report_footer,
)
from skills._sdk.result import (
    load_result_json,
    write_result_json,
)
from skills._sdk.checksums import sha256_file
from skills._sdk.notebook import load_skill
from skills.singlecell._lib.adata_utils import (
    store_analysis_metadata,
)
from skills.singlecell._lib.gallery import PlotSpec, VisualizationRecipe, render_plot_specs
from skills.singlecell._lib import io as sc_io
from skills.singlecell._lib.preflight import apply_preflight, preflight_sc_filter
from skills.singlecell._lib.viz import (
    plot_filter_metric_comparison,
    plot_filter_reason_summary,
    plot_filter_retention_summary,
    plot_filter_state_scatter,
    plot_filter_threshold_panels,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

SKILL_NAME = "sc-filter"
SKILL_VERSION = "0.3.0"

R_ENHANCED_PLOTS: dict[str, str] = {
    # sc-filter runs before clustering — no cell-type compositions yet.
    # plot_feature_violin reads gene_expression.csv (QC metrics in long format).
    "plot_feature_violin": "r_feature_violin.png",
}


def _render_r_enhanced(output_dir: Path, figure_data_dir: Path, r_enhanced: bool) -> list[str]:
    if not r_enhanced:
        return []
    from skills.singlecell._lib.viz.r import call_r_plot
    r_figures_dir = output_dir / "figures" / "r_enhanced"
    r_figures_dir.mkdir(parents=True, exist_ok=True)
    r_figure_paths: list[str] = []
    for renderer, filename in R_ENHANCED_PLOTS.items():
        out_path = r_figures_dir / filename
        call_r_plot(renderer, figure_data_dir, out_path)
        if out_path.exists():
            r_figure_paths.append(str(out_path))
    return r_figure_paths


def _write_repro_requirements(repro_dir: Path, packages: list[str]) -> None:
    try:
        from importlib.metadata import PackageNotFoundError, version as get_version
    except ImportError:  # pragma: no cover
        PackageNotFoundError = Exception
        from importlib_metadata import version as get_version  # type: ignore

    lines: list[str] = []
    for pkg in packages:
        try:
            lines.append(f"{pkg}=={get_version(pkg)}")
        except PackageNotFoundError:
            continue
        except Exception:
            continue
    (repro_dir / "requirements.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")




def build_public_params(args) -> dict:
    return {
        "min_genes": args.min_genes,
        "max_genes": args.max_genes,
        "min_counts": args.min_counts,
        "max_counts": args.max_counts,
        "max_mt_percent": args.max_mt_percent,
        "min_cells": args.min_cells,
        "tissue": args.tissue,
        "remove_doublets": args.remove_doublets,
        "doublet_score_threshold": args.doublet_score_threshold,
    }


def _prepare_filter_gallery_context(adata_before, adata_after, summary: dict, params: dict, output_dir: Path) -> dict:
    api = load_skill(SKILL_NAME)
    metric_columns = [column for column in ("n_genes_by_counts", "total_counts", "pct_counts_mt") if column in adata_before.obs.columns]
    before_qc = adata_before.obs.loc[:, metric_columns].copy() if metric_columns else pd.DataFrame()
    after_qc = adata_after.obs.loc[:, metric_columns].copy() if metric_columns else pd.DataFrame()
    state_df = adata_before.obs.loc[:, metric_columns].copy() if metric_columns else pd.DataFrame()
    state_df["state"] = "Removed"
    retained_cells = set(adata_after.obs_names.astype(str))
    state_df.index = adata_before.obs_names.astype(str)
    state_df.loc[state_df.index.isin(retained_cells), "state"] = "Retained"
    reason_labels = {
        "min_genes_removed": "Below min genes",
        "max_genes_removed": "Above max genes",
        "min_counts_removed": "Below min counts",
        "max_counts_removed": "Above max counts",
        "mt_removed": "Above MT threshold",
        "outliers_flagged": "Existing outlier flag",
        "doublets_removed": "Doublet (sc-doublet-detection)",
    }
    reason_df = pd.DataFrame(
        [
            {"reason": reason_labels.get(key, key.replace("_", " ")), "count": int(value)}
            for key, value in summary.get("filter_stats", {}).items()
            if int(value) > 0
        ]
    )
    return {
        "output_dir": Path(output_dir),
        "metric_columns": metric_columns,
        "before_qc_df": before_qc,
        "after_qc_df": after_qc,
        "state_df": state_df.reset_index(drop=True),
        "reason_df": reason_df,
        "filter_summary_df": api.filter_summary(adata_after),
        "filter_stats_df": api.filter_stats_table(adata_after),
        "retention_df": api.retention_table(adata_after),
        "thresholds": {
            "min_genes": params.get("min_genes"),
            "max_genes": params.get("max_genes"),
            "min_counts": params.get("min_counts"),
            "max_counts": params.get("max_counts"),
            "max_mt_percent": params.get("max_mt_percent"),
        },
    }


def _build_filter_visualization_recipe() -> VisualizationRecipe:
    plots = [
        PlotSpec(
            plot_id="filter_metric_comparison",
            role="diagnostic",
            renderer="filter_metric_comparison",
            filename="filter_comparison.png",
            title="QC metrics before and after filtering",
            description="Compare core QC distributions before and after threshold filtering.",
        ),
        PlotSpec(
            plot_id="filter_retention_summary",
            role="overview",
            renderer="filter_retention_summary",
            filename="filter_summary.png",
            title="Retention summary",
            description="Cells and genes retained after filtering.",
        ),
        PlotSpec(
            plot_id="filter_threshold_panels",
            role="diagnostic",
            renderer="filter_threshold_panels",
            filename="filter_thresholds.png",
            title="Threshold-aware distributions",
            description="Before/after distributions with filter thresholds overlaid.",
        ),
        PlotSpec(
            plot_id="filter_state_scatter",
            role="diagnostic",
            renderer="filter_state_scatter",
            filename="filter_state_scatter.png",
            title="Retained vs removed in QC space",
            description="QC-space scatterplots colored by retained vs removed cells.",
        ),
        PlotSpec(
            plot_id="filter_reason_summary",
            role="supporting",
            renderer="filter_reason_summary",
            filename="filter_reason_summary.png",
            title="Removal reasons",
            description="How many cells were flagged by each filtering rule.",
        ),
    ]
    return VisualizationRecipe(
        recipe_id="standard-sc-filter-gallery",
        skill_name=SKILL_NAME,
        title="Single-cell filtering gallery",
        description="Default OmicsClaw gallery for threshold-based single-cell filtering.",
        plots=plots,
    )


def _render_filter_metric_comparison(_adata, spec: PlotSpec, context: dict) -> object:
    plot_filter_metric_comparison(
        context.get("before_qc_df", pd.DataFrame()),
        context.get("after_qc_df", pd.DataFrame()),
        context["output_dir"],
        metrics=context.get("metric_columns", []),
        filename=spec.filename,
    )
    path = Path(context["output_dir"]) / "figures" / spec.filename
    return path if path.exists() else None


def _render_filter_retention_summary(_adata, spec: PlotSpec, context: dict) -> object:
    plot_filter_retention_summary(
        context.get("retention_df", pd.DataFrame()),
        context["output_dir"],
        filename=spec.filename,
    )
    path = Path(context["output_dir"]) / "figures" / spec.filename
    return path if path.exists() else None


def _render_filter_threshold_panels(_adata, spec: PlotSpec, context: dict) -> object:
    plot_filter_threshold_panels(
        context.get("before_qc_df", pd.DataFrame()),
        context.get("after_qc_df", pd.DataFrame()),
        context["output_dir"],
        thresholds=context.get("thresholds", {}),
        filename=spec.filename,
    )
    path = Path(context["output_dir"]) / "figures" / spec.filename
    return path if path.exists() else None


def _render_filter_state_scatter(_adata, spec: PlotSpec, context: dict) -> object:
    plot_filter_state_scatter(
        context.get("state_df", pd.DataFrame()),
        context["output_dir"],
        filename=spec.filename,
    )
    path = Path(context["output_dir"]) / "figures" / spec.filename
    return path if path.exists() else None


def _render_filter_reason_summary(_adata, spec: PlotSpec, context: dict) -> object:
    plot_filter_reason_summary(
        context.get("reason_df", pd.DataFrame()),
        context["output_dir"],
        filename=spec.filename,
    )
    path = Path(context["output_dir"]) / "figures" / spec.filename
    return path if path.exists() else None


FILTER_GALLERY_RENDERERS = {
    "filter_metric_comparison": _render_filter_metric_comparison,
    "filter_retention_summary": _render_filter_retention_summary,
    "filter_threshold_panels": _render_filter_threshold_panels,
    "filter_state_scatter": _render_filter_state_scatter,
    "filter_reason_summary": _render_filter_reason_summary,
}


def generate_filter_figures(_adata, output_dir: Path, *, gallery_context: dict) -> list[str]:
    recipe = _build_filter_visualization_recipe()
    artifacts = render_plot_specs(
        _adata,
        output_dir,
        recipe,
        FILTER_GALLERY_RENDERERS,
        context=gallery_context,
    )
    gallery_context["recipe"] = recipe
    gallery_context["artifacts"] = artifacts
    gallery_context["figure_data_files"] = {
        "filter_summary": "filter_summary.csv",
        "filter_stats": "filter_stats.csv",
        "retention": "retention_summary.csv",
        "filter_state": "filter_state.csv",
        "filter_reasons": "filter_reasons.csv",
    }
    figures_dir = Path(output_dir) / "figure_data"
    figures_dir.mkdir(parents=True, exist_ok=True)
    gallery_context["filter_summary_df"].to_csv(figures_dir / "filter_summary.csv", index=False)
    gallery_context["filter_stats_df"].to_csv(figures_dir / "filter_stats.csv", index=False)
    gallery_context["retention_df"].to_csv(figures_dir / "retention_summary.csv", index=False)
    gallery_context["state_df"].to_csv(figures_dir / "filter_state.csv", index=False)
    gallery_context["reason_df"].to_csv(figures_dir / "filter_reasons.csv", index=False)

    # Write gene_expression.csv in long format for plot_feature_violin R renderer.
    # Uses QC metric columns from filter_state.csv (n_genes_by_counts, total_counts, etc.)
    state_df = gallery_context.get("state_df")
    if isinstance(state_df, pd.DataFrame) and not state_df.empty:
        metric_cols = [c for c in state_df.columns if c not in ("state",) and state_df[c].dtype.kind in ("f", "i", "u")]
        if metric_cols:
            # Add a synthetic cell_id index if not present
            if "cell_id" not in state_df.columns:
                state_df = state_df.copy()
                state_df.insert(0, "cell_id", [f"cell_{i}" for i in range(len(state_df))])
            long_rows = []
            for col in metric_cols:
                for _, row in state_df[["cell_id", col]].iterrows():
                    long_rows.append({"cell_id": row["cell_id"], "gene": col, "expression": row[col]})
            pd.DataFrame(long_rows).to_csv(figures_dir / "gene_expression.csv", index=False)
            gallery_context["figure_data_files"]["gene_expression"] = "gene_expression.csv"
    (figures_dir / "manifest.json").write_text(
        json.dumps(
            {
                "skill": SKILL_NAME,
                "recipe_id": recipe.recipe_id,
                "available_files": gallery_context["figure_data_files"],
                "plots": [
                    {
                        "plot_id": artifact.plot_id,
                        "filename": artifact.filename,
                        "status": artifact.status,
                        "role": artifact.role,
                    }
                    for artifact in artifacts
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return [artifact.path for artifact in artifacts if artifact.status == "rendered" and artifact.path]


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
        "## Matrix Contract\n",
        f"- **X**: {params.get('matrix_contract', {}).get('X')}",
        f"- **raw**: {params.get('matrix_contract', {}).get('raw')}",
        f"- **counts layer**: {params.get('matrix_contract', {}).get('layers', {}).get('counts')}",
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
    # Doublet removal status
    doublets_removed = summary.get('filter_stats', {}).get('doublets_removed', 0)
    if params.get('remove_doublets', True):
        if doublets_removed > 0:
            body_lines.append(f"- **Doublet removal**: enabled — removed {doublets_removed:,} doublets")
        else:
            body_lines.append(
                "- **Doublet removal**: enabled — no doublet columns found "
                "(run sc-doublet-detection upstream to activate)"
            )
    else:
        body_lines.append("- **Doublet removal**: disabled (--no-remove-doublets)")

    # Filter breakdown
    body_lines.extend(["", "## Filter counts\n"])
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
        body_lines.append("[!] **Warning**: Low retention rate (< 50%). Check QC thresholds and data quality.")
    elif retention < 70:
        body_lines.append("⚡ **Note**: Moderate retention rate (50-70%). Review filtering parameters.")
    else:
        body_lines.append("[ok] Good retention rate (> 70%).")

    body_lines.extend([
        "",
        "## Output Files\n",
        "- `processed.h5ad` — Filtered AnnData object ready for downstream steps",
        "- `figures/filter_comparison.png` — Before/after QC comparison",
        "- `figures/filter_summary.png` — Cell/gene retention summary",
        "- `tables/filter_stats.csv` — Detailed filtering statistics",
        "- `figure_data/` — Plot-ready exports for downstream customization",
        "",
    ])

    footer = generate_report_footer()
    report = header + "\n" + "\n".join(body_lines) + "\n" + footer

    (output_dir / "report.md").write_text(report)


def generate_demo_data():
    """Generate demo data with QC metrics."""
    logger.info("Generating demo data...")
    try:
        adata, demo_path = sc_io.load_repo_demo_data("pbmc3k_raw")
        logger.info(
            "Loaded demo dataset: %s (%d cells x %d genes)",
            demo_path or "scanpy-pbmc3k",
            adata.n_obs,
            adata.n_vars,
        )
    except Exception:
        import scanpy as sc
        # Synthetic fallback
        np.random.seed(42)
        n_cells, n_genes = 500, 1000
        counts = np.random.negative_binomial(2, 0.02, size=(n_cells, n_genes))
        import scanpy as sc
        adata = sc.AnnData(
            X=counts.astype("float32"),
            obs=pd.DataFrame(index=[f"cell_{i}" for i in range(n_cells)]),
            var=pd.DataFrame(index=[f"gene_{i}" for i in range(n_genes)]),
        )

    return adata


def write_reproducibility(output_dir: Path, public_params: dict, input_file: str | None, *, demo_mode: bool = False) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(exist_ok=True)

    command_parts = ["python", "skills/singlecell/scrna/sc-filter/sc_filter.py"]
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
        command_parts.extend([f"--{key.replace('_', '-')}", str(value)])
    command = " ".join(shlex.quote(part) for part in command_parts)
    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    _write_repro_requirements(repro_dir, ["scanpy", "anndata", "numpy", "pandas", "matplotlib"])


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
    parser.add_argument("--no-remove-doublets", dest="remove_doublets", action="store_false",
                        default=True,
                        help="Disable automatic doublet removal (doublets are removed by default when "
                             "predicted_doublet / doublet_score columns from sc-doublet-detection are present)")
    parser.add_argument("--doublet-score-threshold", type=float, default=0.25,
                        help="Score cutoff used when only doublet_score (not predicted_doublet) is available "
                             "(default: 0.25)")
    parser.add_argument("--r-enhanced", action="store_true", default=False,
                        help="Generate R-enhanced figures via ggplot2 renderers")
    args = parser.parse_args()

    # -- Parameter validation --
    from skills.singlecell._lib.param_validators import ParamValidator
    v = ParamValidator(SKILL_NAME)
    v.non_negative("min_genes", args.min_genes)
    v.non_negative("max_genes", args.max_genes)
    v.non_negative("min_counts", args.min_counts)
    v.non_negative("max_counts", args.max_counts)
    v.non_negative("min_cells", args.min_cells)
    v.percentage("max_mt_percent", args.max_mt_percent)
    v.min_max_consistent("min_genes", args.min_genes, "max_genes", args.max_genes)
    v.min_max_consistent("min_counts", args.min_counts, "max_counts", args.max_counts)
    v.check()

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
        adata = sc_io.smart_load(input_path, skill_name=SKILL_NAME, preserve_all=True)
        input_file = str(input_path)

    logger.info(f"Input: {adata.n_obs} cells x {adata.n_vars} genes")
    apply_preflight(
        preflight_sc_filter(
            adata,
            tissue=args.tissue,
            min_counts=args.min_counts,
            max_counts=args.max_counts,
            max_mt_percent=args.max_mt_percent,
            min_genes=args.min_genes,
            max_genes=args.max_genes,
            min_cells=args.min_cells,
            remove_doublets=args.remove_doublets,
            doublet_score_threshold=args.doublet_score_threshold,
            source_path=input_file,
        ),
        logger,
    )

    had_qc_metrics = {
        "n_genes_by_counts",
        "total_counts",
        "pct_counts_mt",
    }.issubset(set(adata.obs.columns))
    if not had_qc_metrics:
        print()
        print("[i] No QC metrics found. Computing automatically.")
        print("  Tip: Run sc-qc first for detailed QC visualization.")
        print()
    params = build_public_params(args)
    api = load_skill(SKILL_NAME)
    adata_filtered = api.filter_cells(adata, **params)
    info = api.run_info(adata_filtered)
    summary = info["summary"]
    effective_params = info["effective_params"]
    input_contract, matrix_contract = info["input_contract"], info["matrix_contract"]
    adata_before = adata.copy()
    adata_before.obs = api.filter_state_table(adata, adata_filtered).drop(columns="state")

    # Generate figures
    logger.info("Generating figures...")
    gallery_context = _prepare_filter_gallery_context(adata_before, adata_filtered, summary, effective_params, output_dir)
    figures = generate_filter_figures(adata_filtered, output_dir, gallery_context=gallery_context)

    # Save tables
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(exist_ok=True)
    gallery_context["filter_stats_df"].to_csv(tables_dir / "filter_stats.csv", index=False)
    gallery_context["filter_summary_df"].to_csv(tables_dir / "filter_summary.csv", index=False)
    gallery_context["retention_df"].to_csv(tables_dir / "retention_summary.csv", index=False)

    # Write report
    logger.info("Writing report...")
    report_params = dict(effective_params)
    report_params["matrix_contract"] = matrix_contract
    write_filter_report(output_dir, summary, report_params, input_file)

    # Save filtered data
    output_h5ad = output_dir / "processed.h5ad"
    api.run_info(adata_filtered, keep=False)
    store_analysis_metadata(adata_filtered, SKILL_NAME, "threshold_filtering", effective_params)
    from skills.singlecell._lib.export import save_h5ad
    save_h5ad(adata_filtered, output_h5ad)
    logger.info(f"Saved: {output_h5ad}")

    # Reproducibility
    write_reproducibility(output_dir, params, input_file, demo_mode=args.demo)

    # Result.json
    checksum = sha256_file(input_file) if input_file and Path(input_file).exists() else ""
    result_data = {
        "workflow": "threshold_filtering",
        "params": params,
        "effective_params": effective_params,
        "input_contract": input_contract,
        "matrix_contract": matrix_contract,
        "visualization": {
            "recipe_id": "standard-sc-filter-gallery",
            "available_figure_data": gallery_context.get("figure_data_files", {}),
            "qc_metric_columns": gallery_context.get("metric_columns", []),
        },
    }
    result_data["next_steps"] = [
        {"skill": "sc-preprocessing", "reason": "Normalize, select HVGs, and reduce dimensions", "priority": "recommended"},
        {"skill": "sc-ambient-removal", "reason": "Optional: remove ambient RNA contamination", "priority": "optional"},
    ]
    result_data["preprocessing_state_after"] = "filtered"
    r_enhanced_figures = _render_r_enhanced(output_dir, output_dir / "figure_data", args.r_enhanced)
    result_data["r_enhanced_figures"] = r_enhanced_figures
    write_result_json(output_dir, SKILL_NAME, SKILL_VERSION, summary, result_data, checksum)
    result_payload = load_result_json(output_dir) or {
        "skill": SKILL_NAME,
        "summary": summary,
        "data": result_data,
    }

    # Summary
    print(f"\n{'='*60}")
    print(f"Success: {SKILL_NAME} v{SKILL_VERSION}")
    print(f"{'='*60}")
    print(f"  Cells: {summary['n_cells_before']:,} -> {summary['n_cells_after']:,} ({summary['cells_retained_pct']}%)")
    print(f"  Genes: {summary['n_genes_before']:,} -> {summary['n_genes_after']:,} ({summary['genes_retained_pct']}%)")
    print(f"  Output: {output_dir}")
    print()
    print(">> Next step: Run sc-preprocessing for normalization, HVG selection, and PCA")
    print(f"  python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py --input {output_h5ad} --output <dir>")
    print()
    print("[i] Optional: Run sc-doublet-detection or sc-ambient-removal before preprocessing")


if __name__ == "__main__":
    main()
