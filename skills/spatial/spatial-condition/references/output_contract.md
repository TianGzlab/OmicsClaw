# Output contract

Functions return AnnData, DataFrame or Figure without file I/O.
Both methods aggregate raw counts per biological sample and cluster.

## Data and tables

- Successful CLI runs write `processed.h5ad`, `report.md`, `result.json`.
- `tables/pseudobulk_de.csv` exists only when DE results are nonempty.
- `tables/per_cluster_summary.csv` exists only when contrasts were tested.
- `tables/skipped_contrasts.csv` exists only when contrasts were skipped.
- Plot-data exports are always created, sometimes empty:
  `figure_data/pseudobulk_de.csv`, `figure_data/pseudobulk_volcano_points.csv`,
  `figure_data/per_cluster_summary.csv`, `figure_data/skipped_contrasts.csv`,
  `figure_data/cluster_de_metrics.csv`, `figure_data/top_de_genes.csv`,
  `figure_data/sample_counts_by_condition.csv`, `figure_data/condition_run_summary.csv`.
- `figure_data/condition_spatial_points.csv` and
  `figure_data/condition_umap_points.csv` require the corresponding coordinates.
- `figures/manifest.json`, `figure_data/manifest.json`,
  `reproducibility/commands.sh`, `reproducibility/requirements.txt` and
  `reproducibility/r_visualization.sh` describe the gallery and CLI.

## Figures

- `figures/condition_spatial_context.png`: spatial coordinates and condition labels.
- `figures/pseudobulk_volcano.png`: DE results with fold changes and p-values.
- `figures/condition_effect_burden_spatial.png`: spatial coordinates and cluster effects.
- `figures/condition_effect_burden_umap.png`: UMAP and cluster effects.
- `figures/condition_de_barplot.png` and `figures/cluster_de_burden.png`: tested contrasts.
- `figures/condition_pvalue_distribution.png`: available adjusted p-values.
- `figures/sample_counts_by_condition.png`: sample-count summary.
- `figures/skipped_contrasts.png`: nonempty skipped-contrast summary.

The gene table includes gene, base_mean, log2fc, stat, pvalue, pvalue_adj,
method, cluster, contrast and replicate counts; PyDESeq2 also supplies lfc_se.
An empty or skipped contrast is not evidence of no differential expression.
Fit fallback is recorded with requested/executed methods and the reason.
