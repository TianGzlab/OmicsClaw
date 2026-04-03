"""Unified visualization primitives for single-cell OmicsClaw skills."""

from .core import QC_PALETTE, apply_singlecell_theme, save_figure
from .qc import (
    plot_barcode_rank,
    plot_highest_expr_genes,
    plot_qc_correlation_heatmap,
    plot_qc_histograms,
    plot_qc_scatter,
    plot_qc_violin,
)
from .upstream import (
    plot_barcode_rank,
    plot_count_distributions,
    plot_feature_type_totals,
    plot_fastq_per_base_quality,
    plot_fastq_sample_summary,
    plot_velocity_gene_balance,
    plot_velocity_layer_summary,
)

__all__ = [
    "QC_PALETTE",
    "apply_singlecell_theme",
    "save_figure",
    "plot_qc_violin",
    "plot_qc_scatter",
    "plot_qc_histograms",
    "plot_highest_expr_genes",
    "plot_barcode_rank",
    "plot_qc_correlation_heatmap",
    "plot_fastq_sample_summary",
    "plot_fastq_per_base_quality",
    "plot_count_distributions",
    "plot_barcode_rank",
    "plot_feature_type_totals",
    "plot_velocity_layer_summary",
    "plot_velocity_gene_balance",
]
