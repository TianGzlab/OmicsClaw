# Output contract

Functions return the same AnnData, native score DataFrames and a Figure.
All methods store `uns['spatial_genes_results']` and
`uns['spatial_genes_summary']`; Moran's I also stores `uns['moranI']`.
The CLI removes the transient JSON diagnostics before writing `processed.h5ad`.

The CLI writes `processed.h5ad`, `report.md`, `result.json`, `reproducibility/commands.sh`,
`reproducibility/requirements.txt` and `reproducibility/r_visualization.sh`.

## Tables

- `tables/svg_results.csv`: native method scores and significance columns;
  their names are recorded in the summary.
- `tables/top_svg_scores.csv`: ranked display selection.
- `tables/significant_svgs.csv`: the selected significance threshold.
- `tables/svg_observation_metrics.csv`: gallery metrics when available.
- `tables/svg_run_summary.csv`: method and diagnostic metadata.
- `tables/top_svg_spatial_points.csv` and `tables/top_svg_umap_points.csv`:
  only when the corresponding coordinates exist.

SPARK-X's counts, coordinates and R result CSVs are temporary exchange files.
They are deleted with the temporary directory, not delivered under tables.

## Conditional figures

- `figures/top_svg_spatial.png`: selected genes and spatial coordinates.
- `figures/top_svg_umap.png`: selected genes and UMAP.
- `figures/top_svg_scores.png`: score column available.
- `figures/svg_score_vs_significance.png`: score and significance columns.
- `figures/svg_significance_distribution.png`: significance column available.
- `figures/moran_ranking.png`: Moran's I results in uns.

The gallery also writes `figure_data/manifest.json` and per-plot data. Plot
failures are logged; optional panels are not unconditional outputs.
