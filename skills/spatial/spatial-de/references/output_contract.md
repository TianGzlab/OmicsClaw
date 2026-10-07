# Output contract

Functions return the same AnnData, result DataFrames and a Figure without
writing files. `run_info` holds a JSON diagnostic record; the CLI removes it
before writing `processed.h5ad`. Existing Scanpy ranking keys remain.

The CLI writes `report.md`, `result.json`, `processed.h5ad`, `reproducibility/commands.sh`,
`reproducibility/requirements.txt` and `reproducibility/r_visualization.sh`.

## Tables

- `tables/de_full.csv`: every tested gene, with native Scanpy or PyDESeq2 columns.
- `tables/markers_top.csv` and `tables/top_de_hits.csv`: ranked display selections.
- `tables/de_significant.csv`: adjusted significance and absolute effect thresholds.
- `tables/group_de_metrics.csv`: group-level hit counts.
- `tables/sample_counts_by_group.csv`: pseudobulk support; empty for Scanpy.
- `tables/skipped_sample_groups.csv`: excluded sample-group bins; may be empty.
- `tables/de_plot_points.csv` and `tables/de_run_summary.csv`: gallery data.
- `tables/de_spatial_points.csv` and `tables/de_umap_points.csv`: only when
  their respective coordinates exist.

## Conditional figures

- `figures/de_group_spatial_context.png`: group labels and spatial coordinates.
- `figures/de_marker_dotplot.png` and `figures/de_marker_heatmap.png`: selected
  marker genes and labels.
- `figures/de_volcano.png` and `figures/de_pvalue_distribution.png`: nonempty DE table.
- `figures/de_effect_burden_spatial.png` and `figures/de_effect_burden_umap.png`:
  group effect metrics and their respective coordinates.
- `figures/de_top_hits_barplot.png`: nonempty top-hit table.
- `figures/group_de_burden.png`: group metrics.
- `figures/sample_counts_by_group.png`: pseudobulk sample counts.
- `figures/skipped_sample_groups.png`: at least one excluded bin.

The gallery also writes `figure_data/manifest.json` and data for rendered plots.
Figure failures are logged; the inventory does not guarantee every PNG.
