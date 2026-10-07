# Output contract

## Function library

The computation returns the same AnnData. Table accessors return DataFrames;
plot functions return Figures without writing files. Diagnostics are a JSON string
in `uns['omicsclaw_spatial_velocity_run']`; `run_info(keep=False)` removes it.

The library filters genes and changes X and count layers during preprocessing, adds Ms/Mu/velocity layers, and stores available fitted parameters in var. VELOVI adds latent_time_velovi and fit_t layers plus mean latent time. run_info warnings identify optional estimates that failed.

## CLI artifacts

`processed.h5ad`, `report.md` and `result.json` are written after a successful run.
Commands and R plotting helpers live under `reproducibility/`.
That directory also contains requirements.txt and environment.txt.

All six table files are written. Their columns and row counts depend on the fitted backend; optional metrics may be absent. scVelo velocity_pseudotime is not numerically repeatable because its eigensolver exposes no seed; the example's CSV omits that column while its H5AD retains it.

- `tables/cell_velocity_metrics.csv`
- `tables/gene_velocity_summary.csv`
- `tables/velocity_gene_hits.csv`
- `tables/velocity_cluster_summary.csv`
- `tables/top_velocity_cells.csv`
- `tables/top_velocity_genes.csv`

Figure-ready summaries and coordinate tables live under `figure_data/`, with
`figure_data/manifest.json`. They are not additional files under `tables/`.
The gallery records rendered/skipped artifacts in `figures/manifest.json`.
A renderer can skip an otherwise eligible plot if its backend cannot render it.

| Figure | Required result |
|---|---|
| `figures/velocity_cluster_summary.png` | cluster summaries |
| `figures/velocity_confidence_distribution.png` | velocity confidence |
| `figures/velocity_confidence_spatial.png` | confidence and spatial coordinates |
| `figures/velocity_confidence_umap.png` | confidence and UMAP |
| `figures/velocity_heatmap.png` | velocity graph and pseudotime/latent time |
| `figures/velocity_latent_time_spatial.png` | latent time and spatial coordinates |
| `figures/velocity_layer_proportions.png` | spliced/unspliced layers and cluster labels |
| `figures/velocity_paga.png` | cluster labels and a usable graph |
| `figures/velocity_phase.png` | velocity, Ms and Mu layers |
| `figures/velocity_pseudotime_spatial.png` | pseudotime and spatial coordinates |
| `figures/velocity_speed_distribution.png` | velocity speed |
| `figures/velocity_speed_spatial.png` | speed and spatial coordinates |
| `figures/velocity_speed_umap.png` | speed and UMAP |
| `figures/velocity_stream_spatial.png` | velocity graph and spatial coordinates |
| `figures/velocity_stream_umap.png` | velocity graph and UMAP |
| `figures/velocity_top_genes_barplot.png` | ranked fitted genes |
| `figures/velocity_transition_confidence_umap.png` | transition confidence and UMAP |
