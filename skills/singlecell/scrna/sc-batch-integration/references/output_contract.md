# Batch integration outputs

The CLI writes `processed.h5ad`, `report.md`, `result.json` and
`reproducibility/commands.sh` plus `requirements.txt` in that same directory.
It does not copy its input to the output directory.

Non-empty tables in `tables/` are `integration_summary.csv`, `batch_sizes.csv`,
`integration_metrics.csv`, and, when labels exist, `cluster_sizes.csv` and
`batch_mixing_matrix.csv`. Metrics unavailable in the current environment are
omitted. Per-cell plot coordinates are `figure_data/umap_points.csv`.
`figure_data/manifest.json` lists the plot tables and render status.

Figures include `umap_<batch_key>.png`, `integration_metrics.png`, and, with
labels, `umap_<label_key>.png` and `batch_mixing_heatmap.png`.
`--r-enhanced` optionally adds `figures/r_embedding_discrete.png`.

The H5AD contains the method's `X_<method>` representation, except BBKNN,
which changes the graph while retaining `X_pca`. The CLI also stores UMAP.
The function library leaves neighbours and UMAP to the caller (BBKNN's graph
is intrinsic to that method). `run_info` contains requested/executed methods
and fallback details; the CLI removes this temporary summary before saving.
