"""Contract helpers for the spatial-raw-processing skill."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shlex
from pathlib import Path
from typing import Any

import pandas as pd

from omicsclaw.common.report import (
    generate_report_footer,
    generate_report_header,
    write_repro_requirements,
)
from skills.spatial._lib.raw_processing import (
    build_gene_qc_table,
    build_run_summary_table,
    build_saturation_table,
    build_spatial_export_table,
    build_spot_qc_table,
    build_stage_summary_table,
    build_top_gene_table,
)
from skills.spatial._lib.viz import (
    PlotSpec,
    VisualizationRecipe,
    VizParams,
    plot_features,
    plot_saturation_curve,
    plot_spot_qc_histograms,
    plot_stage_attrition,
    plot_top_genes_bar,
    render_plot_specs,
)


@dataclass(frozen=True)
class RawProcessingContractSpec:
    skill_name: str
    skill_version: str
    method: str
    next_skill: str
    script_rel_path: str
    r_visualization_template: Path


def _append_cli_flag(command: str, key: str, value: Any) -> str:
    flag = f"--{str(key).replace('_', '-')}"
    if isinstance(value, bool):
        return f"{command} {flag}" if value else command
    if value in (None, ""):
        return command
    return f"{command} {flag} {shlex.quote(str(value))}"


def build_summary(
    adata,
    params: dict[str, Any],
    upstream_meta: dict[str, Any],
    *,
    spec: RawProcessingContractSpec,
) -> dict[str, Any]:
    stage_metrics = dict(upstream_meta.get("stats") or {})
    saturation = dict(upstream_meta.get("saturation") or {})

    total_counts_series = pd.to_numeric(adata.obs.get("total_counts"), errors="coerce").fillna(0.0)
    n_genes_series = pd.to_numeric(adata.obs.get("n_genes_by_counts"), errors="coerce").fillna(0.0)
    detected_series = adata.obs.get("detected_by_stpipeline")
    if detected_series is None:
        detected_spots = int(adata.n_obs)
    else:
        detected_spots = int(pd.Series(detected_series).astype(bool).sum())

    input_reads = stage_metrics.get("input_reads_reverse") or stage_metrics.get("input_reads_forward")
    reads_after_dedup = stage_metrics.get("reads_after_duplicates_removal")
    total_counts = int(total_counts_series.sum())
    if reads_after_dedup in (None, ""):
        reads_after_dedup = total_counts

    return {
        "method": spec.method,
        "platform": params.get("platform"),
        "exp_name": params.get("exp_name"),
        "n_spots": int(adata.n_obs),
        "n_genes": int(adata.n_vars),
        "detected_spots": detected_spots,
        "empty_barcodes": int(adata.n_obs - detected_spots),
        "total_counts": total_counts,
        "median_counts_per_spot": float(total_counts_series.median()) if adata.n_obs else 0.0,
        "median_genes_per_spot": float(n_genes_series.median()) if adata.n_obs else 0.0,
        "input_reads": int(input_reads) if input_reads not in (None, "") else None,
        "reads_after_dedup": int(reads_after_dedup) if reads_after_dedup not in (None, "") else None,
        "reads_retained_fraction": (
            float(reads_after_dedup) / float(input_reads)
            if input_reads not in (None, "", 0) and reads_after_dedup not in (None, "")
            else None
        ),
        "barcodes_found": int(stage_metrics.get("barcodes_found") or detected_spots),
        "genes_found": int(stage_metrics.get("genes_found") or adata.n_vars),
        "next_skill": spec.next_skill,
        "stage_metrics": stage_metrics,
        "saturation": saturation,
    }


def prepare_raw_processing_gallery_context(adata, summary: dict[str, Any]) -> dict[str, Any]:
    stage_summary_df = build_stage_summary_table(summary.get("stage_metrics", {}))
    spot_qc_df = build_spot_qc_table(adata)
    gene_qc_df = build_gene_qc_table(adata)
    top_gene_df = build_top_gene_table(adata, top_n=20)
    spatial_points_df = build_spatial_export_table(adata) if "spatial" in adata.obsm else pd.DataFrame()
    saturation_df = build_saturation_table(summary.get("saturation", {}))
    run_summary_df = build_run_summary_table(
        {
            "method": summary.get("method"),
            "platform": summary.get("platform"),
            "exp_name": summary.get("exp_name"),
            "n_spots": summary.get("n_spots"),
            "n_genes": summary.get("n_genes"),
            "detected_spots": summary.get("detected_spots"),
            "empty_barcodes": summary.get("empty_barcodes"),
            "total_counts": summary.get("total_counts"),
            "input_reads": summary.get("input_reads"),
            "reads_after_dedup": summary.get("reads_after_dedup"),
            "reads_retained_fraction": summary.get("reads_retained_fraction"),
            "barcodes_found": summary.get("barcodes_found"),
            "genes_found": summary.get("genes_found"),
            "next_skill": summary.get("next_skill"),
        }
    )

    return {
        "stage_summary_df": stage_summary_df,
        "spot_qc_df": spot_qc_df,
        "gene_qc_df": gene_qc_df,
        "top_gene_df": top_gene_df,
        "spatial_points_df": spatial_points_df,
        "saturation_df": saturation_df,
        "run_summary_df": run_summary_df,
        "obsm_keys": set(adata.obsm.keys()),
        "layer_keys": set(adata.layers.keys()),
    }


def _build_visualization_recipe(
    adata,
    summary: dict[str, Any],
    context: dict[str, Any],
    *,
    spec: RawProcessingContractSpec,
) -> VisualizationRecipe:
    plots: list[PlotSpec] = []

    if "spatial" in adata.obsm and "total_counts" in adata.obs.columns:
        plots.append(
            PlotSpec(
                plot_id="raw_total_counts_spatial",
                role="overview",
                renderer="feature_map",
                filename="raw_total_counts_spatial.png",
                title="Raw Count Density",
                description="Total molecule counts projected onto the supplied barcode coordinates.",
                required_obs=["total_counts"],
                required_obsm=["spatial"],
                params={"feature": "total_counts", "basis": "spatial"},
            )
        )

    if "spatial" in adata.obsm and "n_genes_by_counts" in adata.obs.columns:
        plots.append(
            PlotSpec(
                plot_id="raw_gene_complexity_spatial",
                role="diagnostic",
                renderer="feature_map",
                filename="raw_detected_genes_spatial.png",
                title="Detected Gene Complexity",
                description="Number of detected genes per barcode projected onto spatial coordinates.",
                required_obs=["n_genes_by_counts"],
                required_obsm=["spatial"],
                params={"feature": "n_genes_by_counts", "basis": "spatial"},
            )
        )

    if not context["stage_summary_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="st_pipeline_stage_attrition",
                role="diagnostic",
                renderer="stage_attrition",
                filename="st_pipeline_stage_attrition.png",
                title="Upstream Read Attrition",
                description="Read retention across trimming, mapping, demultiplexing, annotation, and UMI collapsing.",
            )
        )

    if not context["spot_qc_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="raw_spot_qc_histograms",
                role="supporting",
                renderer="spot_qc_histograms",
                filename="raw_spot_qc_histograms.png",
                title="Spot-Level QC Distributions",
                description="Distributions of total counts and detected genes across the raw matrix.",
            )
        )

    if not context["top_gene_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="raw_top_genes",
                role="supporting",
                renderer="top_genes_bar",
                filename="raw_top_genes_barplot.png",
                title="Top Detected Genes",
                description="Most abundant genes across all detected barcodes in the raw count matrix.",
            )
        )

    if not context["saturation_df"].empty:
        plots.append(
            PlotSpec(
                plot_id="st_pipeline_saturation_curve",
                role="uncertainty",
                renderer="saturation_curve",
                filename="st_pipeline_saturation_curve.png",
                title="Sequencing Saturation Summary",
                description="Saturation statistics reported by st_pipeline when available.",
            )
        )

    return VisualizationRecipe(
        recipe_id="standard-spatial-raw-processing-gallery",
        skill_name=spec.skill_name,
        title="Spatial Raw Processing Standard Gallery",
        description=(
            "Default OmicsClaw raw-processing story plots: coordinate-level raw "
            "signal overview, upstream read attrition, raw QC distributions, top genes, "
            "and optional saturation summaries."
        ),
        plots=plots,
    )


def _render_feature_map(adata, spec: PlotSpec, _context: dict[str, Any]) -> object:
    return plot_features(adata, VizParams(**spec.params))


def _render_stage_attrition(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    return plot_stage_attrition(
        context.get("stage_summary_df", pd.DataFrame()),
        title=spec.title or "Upstream Read Attrition",
    )


def _render_spot_qc_histograms(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    return plot_spot_qc_histograms(
        context.get("spot_qc_df", pd.DataFrame()),
        title=spec.title or "Spot-Level QC Distributions",
    )


def _render_top_genes_bar(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    return plot_top_genes_bar(
        context.get("top_gene_df", pd.DataFrame()),
        title=spec.title or "Top Detected Genes",
    )


def _render_saturation_curve(_adata, spec: PlotSpec, context: dict[str, Any]) -> object:
    return plot_saturation_curve(
        context.get("saturation_df", pd.DataFrame()),
        title=spec.title or "Sequencing Saturation Summary",
    )


RAW_PROCESSING_RENDERERS = {
    "feature_map": _render_feature_map,
    "stage_attrition": _render_stage_attrition,
    "spot_qc_histograms": _render_spot_qc_histograms,
    "top_genes_bar": _render_top_genes_bar,
    "saturation_curve": _render_saturation_curve,
}


def _write_figure_data_manifest(output_dir: Path, manifest: dict[str, Any]) -> None:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)
    (figure_data_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False)
    )


def _export_figure_data(
    output_dir: Path,
    summary: dict[str, Any],
    recipe: VisualizationRecipe,
    artifacts: list[Any],
    context: dict[str, Any],
    *,
    spec: RawProcessingContractSpec,
) -> dict[str, Any]:
    figure_data_dir = output_dir / "figure_data"
    figure_data_dir.mkdir(parents=True, exist_ok=True)

    context["run_summary_df"].to_csv(figure_data_dir / "raw_processing_run_summary.csv", index=False)
    context["stage_summary_df"].to_csv(figure_data_dir / "stage_summary.csv", index=False)
    context["spot_qc_df"].to_csv(figure_data_dir / "raw_spot_qc.csv", index=False)
    context["gene_qc_df"].to_csv(figure_data_dir / "raw_gene_qc.csv", index=False)
    context["top_gene_df"].to_csv(figure_data_dir / "raw_top_genes.csv", index=False)

    spatial_file = None
    if not context["spatial_points_df"].empty:
        spatial_file = "raw_processing_spatial_points.csv"
        context["spatial_points_df"].to_csv(figure_data_dir / spatial_file, index=False)

    saturation_file = None
    if not context["saturation_df"].empty:
        saturation_file = "saturation_curve.csv"
        context["saturation_df"].to_csv(figure_data_dir / saturation_file, index=False)

    contract = {
        "skill": spec.skill_name,
        "version": spec.skill_version,
        "method": summary.get("method"),
        "platform": summary.get("platform"),
        "recipe_id": recipe.recipe_id,
        "gallery_roles": list(dict.fromkeys(plot.role for plot in recipe.plots)),
        "available_files": {
            "raw_processing_run_summary": "raw_processing_run_summary.csv",
            "stage_summary": "stage_summary.csv",
            "raw_spot_qc": "raw_spot_qc.csv",
            "raw_gene_qc": "raw_gene_qc.csv",
            "raw_top_genes": "raw_top_genes.csv",
            "raw_processing_spatial_points": spatial_file,
            "saturation_curve": saturation_file,
        },
        "gallery_outputs": [
            {
                "plot_id": artifact.plot_id,
                "role": artifact.role,
                "filename": artifact.filename,
                "status": artifact.status,
            }
            for artifact in artifacts
        ],
        "next_skill": spec.next_skill,
    }
    _write_figure_data_manifest(output_dir, contract)
    return contract


def generate_figures(
    adata,
    output_dir: Path,
    summary: dict[str, Any],
    *,
    spec: RawProcessingContractSpec,
    gallery_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = gallery_context or prepare_raw_processing_gallery_context(adata, summary)
    recipe = _build_visualization_recipe(adata, summary, context, spec=spec)
    runtime_context = {"summary": summary, **context}
    artifacts = render_plot_specs(
        adata,
        output_dir,
        recipe,
        RAW_PROCESSING_RENDERERS,
        context=runtime_context,
    )
    return _export_figure_data(output_dir, summary, recipe, artifacts, context, spec=spec)


def export_tables(
    output_dir: Path,
    gallery_context: dict[str, Any],
) -> list[str]:
    tables_dir = output_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    exported: list[str] = []
    table_map = {
        "run_summary.csv": gallery_context["run_summary_df"],
        "stage_summary.csv": gallery_context["stage_summary_df"],
        "spot_qc.csv": gallery_context["spot_qc_df"],
        "gene_qc.csv": gallery_context["gene_qc_df"],
        "top_genes.csv": gallery_context["top_gene_df"],
    }
    if not gallery_context["spatial_points_df"].empty:
        table_map["spatial_coordinates.csv"] = gallery_context["spatial_points_df"]
    if not gallery_context["saturation_df"].empty:
        table_map["saturation_curve.csv"] = gallery_context["saturation_df"]

    for filename, dataframe in table_map.items():
        path = tables_dir / filename
        dataframe.to_csv(path, index=False)
        exported.append(str(path))

    return exported


def _write_r_visualization_helper(
    output_dir: Path,
    *,
    spec: RawProcessingContractSpec,
) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)
    cmd = f"Rscript {shlex.quote(str(spec.r_visualization_template))} {shlex.quote(str(output_dir))}"
    (repro_dir / "r_visualization.sh").write_text(f"#!/bin/bash\n{cmd}\n", encoding="utf-8")


def write_reproducibility(
    output_dir: Path,
    params: dict[str, Any],
    *,
    spec: RawProcessingContractSpec,
    demo_mode: bool,
) -> None:
    repro_dir = output_dir / "reproducibility"
    repro_dir.mkdir(parents=True, exist_ok=True)

    command = f"python {spec.script_rel_path}"
    if demo_mode:
        command = f"{command} --demo"
    command = f"{command} --output {shlex.quote(str(output_dir))}"

    ordered_keys = [
        "read1",
        "read2",
        "ids",
        "ref_map",
        "ref_annotation",
        "exp_name",
        "platform",
        "threads",
        "contaminant_index",
        "min_length_qual_trimming",
        "min_quality_trimming",
        "demultiplexing_mismatches",
        "demultiplexing_kmer",
        "umi_allowed_mismatches",
        "umi_start_position",
        "umi_end_position",
        "disable_clipping",
        "compute_saturation",
        "htseq_no_ambiguous",
        "transcriptome",
        "star_two_pass_mode",
        "stpipeline_repo",
        "bin_path",
    ]
    for key in ordered_keys:
        command = _append_cli_flag(command, key, params.get(key))

    (repro_dir / "commands.sh").write_text(f"#!/bin/bash\n{command}\n", encoding="utf-8")
    write_repro_requirements(
        output_dir,
        ["omicsclaw", "anndata", "numpy", "pandas", "scipy", "matplotlib"],
    )
    _write_r_visualization_helper(output_dir, spec=spec)


def write_report(
    output_dir: Path,
    summary: dict[str, Any],
    params: dict[str, Any],
    upstream_meta: dict[str, Any],
    *,
    spec: RawProcessingContractSpec,
    input_files: list[Path] | None = None,
) -> None:
    next_skill = str(summary.get("next_skill") or spec.next_skill)
    header = generate_report_header(
        title="Spatial Raw Processing Report",
        skill_name=spec.skill_name,
        input_files=input_files,
        extra_metadata={
            "Method": spec.method,
            "Platform": str(summary.get("platform") or "unknown"),
            "Experiment": str(summary.get("exp_name") or "unknown"),
        },
    )

    body_lines = [
        "## Summary\n",
        f"- **Method**: {spec.method}",
        f"- **Platform label**: {summary.get('platform')}",
        f"- **Barcodes in output**: {summary.get('n_spots')}",
        f"- **Genes in output**: {summary.get('n_genes')}",
        f"- **Detected barcodes**: {summary.get('detected_spots')}",
        f"- **Empty barcodes retained for coordinate completeness**: {summary.get('empty_barcodes')}",
        f"- **Total counts**: {summary.get('total_counts')}",
        f"- **Median counts per barcode**: {summary.get('median_counts_per_spot'):.2f}",
        f"- **Median genes per barcode**: {summary.get('median_genes_per_spot'):.2f}",
        f"- **Barcodes reported by st_pipeline**: {summary.get('barcodes_found')}",
        f"- **Genes reported by st_pipeline**: {summary.get('genes_found')}",
    ]
    if summary.get("input_reads") is not None:
        body_lines.append(f"- **Input reads**: {summary.get('input_reads')}")
    if summary.get("reads_after_dedup") is not None:
        body_lines.append(f"- **Reads after UMI collapsing**: {summary.get('reads_after_dedup')}")
    if summary.get("reads_retained_fraction") is not None:
        body_lines.append(
            f"- **Read retention after UMI collapsing**: {summary.get('reads_retained_fraction'):.2%}"
        )

    body_lines.extend(
        [
            "",
            "## Effective Parameters\n",
        ]
    )
    for key, value in params.items():
        body_lines.append(f"- `{key}`: {value}")

    body_lines.extend(
        [
            "",
            "## Upstream Artifacts\n",
            "- `upstream/st_pipeline/`: preserved raw upstream outputs, logs, stdout/stderr, and metadata JSON",
            f"- **Counts matrix**: `{upstream_meta.get('counts_path', 'N/A')}`",
            f"- **Reads BED**: `{upstream_meta.get('reads_path', 'N/A')}`",
            f"- **Pipeline log**: `{upstream_meta.get('pipeline_log', 'N/A')}`",
            f"- **Runner**: `{upstream_meta.get('runner', 'N/A')}`",
        ]
    )
    if upstream_meta.get("repo_path"):
        body_lines.append(f"- **Repository path**: `{upstream_meta.get('repo_path')}`")

    body_lines.extend(
        [
            "",
            "## Interpretation Notes\n",
            "- `raw_counts.h5ad` is intentionally unnormalized and is meant to be the handoff object for downstream `spatial-preprocess`.",
            "- OmicsClaw retains barcode coordinates from the IDs file even when some barcodes have zero detected molecules, so downstream neighborhood or masking steps can stay coordinate-aware.",
            "- The Python gallery summarizes upstream attrition and raw-matrix structure; publication styling should consume `figure_data/` instead of recomputing the upstream run.",
            "",
            "## Recommended Next Step\n",
            f"- Run `oc run {next_skill} --input {shlex.quote(str(output_dir / 'raw_counts.h5ad'))} --output <next_dir>` to perform QC, normalization, PCA, UMAP, and clustering.",
            "",
            "## Visualization Outputs\n",
            "- `figures/manifest.json`: standard raw-processing gallery manifest",
            "- `figure_data/manifest.json`: figure-ready CSV inventory",
            "- `reproducibility/r_visualization.sh`: optional R visualization entrypoint",
        ]
    )

    footer = generate_report_footer()
    (output_dir / "report.md").write_text(header + "\n".join(body_lines) + "\n" + footer, encoding="utf-8")


__all__ = [
    "RawProcessingContractSpec",
    "build_summary",
    "prepare_raw_processing_gallery_context",
    "generate_figures",
    "export_tables",
    "write_report",
    "write_reproducibility",
]
