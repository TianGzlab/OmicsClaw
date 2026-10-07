# Output contract

The API returns a copied AnnData, tables or a Figure without writing files.
The CLI writes:

- `processed.h5ad`: filtered cells and peaks, TF-IDF in `.X`, pre-transform
  counts in `layers["counts"]` and `.raw`, `obsm["X_lsi"]`,
  `obsm["X_umap"]`, and `obs["leiden"]`.
- Six tables under `tables/`: `preprocess_summary.csv`,
  `qc_metrics_per_cell.csv`, `peak_summary.csv`, `lsi_variance_ratio.csv`,
  `cluster_summary.csv` and `umap_points.csv`.
- Four figures under `figures/`: `umap_leiden.png`, `lsi_variance.png`,
  `qc_violin.png` and `top_accessible_peaks.png`.
- `figures/manifest.json`, `figure_data/manifest.json` and plot-data CSV files.
- `report.md`, `result.json`, `reproducibility/commands.sh` and
  `reproducibility/requirements.txt`.

QC totals describe counts before top-peak selection; they can exceed sums
over the retained peaks. Input features removed by filtering are not kept
in the output. This skill does not write fragment metrics, gene activity,
motifs, RNA PCA plots or cell metadata exports.
