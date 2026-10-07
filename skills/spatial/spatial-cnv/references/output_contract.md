# Output contract

## Function library

The computation returns the same AnnData. Table accessors return DataFrames;
plot functions return Figures without writing files. Diagnostics are a JSON string
in `uns['omicsclaw_spatial_cnv_run']`; `run_info(keep=False)` removes it.

infercnvpy adds CNV matrices, obs['cnv_leiden'] and obs['cnv_score']. Numbat adds optional clone labels, posterior scores, entropy and call tables. Scores are expression-based research estimates, not DNA copy-number measurements.

## CLI artifacts

`processed.h5ad`, `report.md` and `result.json` are written after a successful run.
Commands and R plotting helpers live under `reproducibility/`.

The scores and run-summary tables are always written. Group sizes need cluster/clone labels, bin summaries need a CNV matrix, and the two Numbat tables need R results. Numbat counts.mtx, barcodes.tsv, features.tsv, obs.csv, allele CSV and R intermediates stay in a temporary directory; they are not top-level output artifacts.

- `tables/cnv_scores.csv`
- `tables/cnv_run_summary.csv`
- `tables/cnv_group_sizes.csv`
- `tables/cnv_bin_summary.csv`
- `tables/numbat_calls.csv`
- `tables/numbat_clone_post.csv`

Figure-ready summaries and coordinate tables live under `figure_data/`, with
`figure_data/manifest.json`. They are not additional files under `tables/`.
The gallery records rendered/skipped artifacts in `figures/manifest.json`.
A renderer can skip an otherwise eligible plot if its backend cannot render it.

| Figure | Required result |
|---|---|
| `figures/cnv_bin_summary.png` | CNV matrix and bin summaries |
| `figures/cnv_group_sizes.png` | cluster/clone labels |
| `figures/cnv_groups_umap.png` | cluster/clone labels and UMAP |
| `figures/cnv_heatmap.png` | infercnvpy CNV matrix |
| `figures/cnv_score_distribution.png` | a CNV score |
| `figures/cnv_spatial.png` | CNV score and spatial coordinates |
| `figures/cnv_umap.png` | CNV score and UMAP |
| `figures/cnv_uncertainty_distribution.png` | Numbat entropy |
| `figures/cnv_uncertainty_spatial.png` | Numbat entropy and spatial coordinates |
