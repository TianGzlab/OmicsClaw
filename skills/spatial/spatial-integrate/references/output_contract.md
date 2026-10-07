# Output contract

Functions return AnnData, DataFrame or Figure; only the CLI writes this gallery.

## Data and tables

- `processed.h5ad`, `report.md`, `result.json` are written on success.
- `tables/integration_metrics.csv`, `tables/batch_sizes.csv` and
  `tables/integration_observations.csv` contain aggregate and per-spot metrics.
- `figure_data/batch_sizes.csv` and `figure_data/integration_metrics.csv`
  contain plotting data.
- `figure_data/umap_before_points.csv` and `figure_data/umap_after_points.csv`
  are written when their UMAP snapshots exist.
- `figure_data/corrected_embedding_points.csv` is written when the method's
  embedding is available with at least two components.
- `figures/manifest.json` and `figure_data/manifest.json` describe rendered plots.
- `reproducibility/commands.sh`, `reproducibility/requirements.txt` and
  `reproducibility/r_visualization.sh` are CLI reproduction helpers.

## Figures

The CLI gallery requests these outputs when the corresponding data are available:

- `figures/umap_before_by_batch.png`: before-integration UMAP and batch labels.
- `figures/umap_by_batch.png`: after-integration UMAP and batch labels.
- `figures/umap_by_cluster.png`: UMAP and a resolved cluster column.
- `figures/batch_highlight.png`: UMAP and the largest-batch indicator.
- `figures/batch_sizes.png`: nonempty batch counts.
- `figures/batch_mixing.png`: batch entropy summary.
- `figures/batch_entropy_after_umap.png`: UMAP and entropy annotation.
- `figures/batch_entropy_distribution.png`: per-spot entropy profiles.

Harmony adds `X_pca_harmony`, Scanorama adds `X_scanorama`; these are PCA-based
embeddings, not corrected gene expression. BBKNN replaces the neighbor graph.
All methods preserve X, observation order and existing cluster labels.
