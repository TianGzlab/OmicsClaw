# Output contract

## Library

`communicate` mutates and returns AnnData. `interactions` returns a copy of
the canonical ligand, receptor, source, target, score and pvalue columns,
plus any backend fields such as pathway. Missing p values remain NaN.
`run_info` returns counts, effective parameters, lr_df, pathway_df,
signaling_roles_df and optional extra_tables. Diagnostics are JSON encoded
in `uns["_spatial_communication_run_info"]` and survive h5ad serialization.

Canonical keys are `uns["ccc_results"]`, `communication_summary`,
`communication_signaling_roles` and `spatial_communication`.
The selected backend also writes liana_results, cellphonedb_results,
fastccc_results or cellchat_results. Empty results are valid tables.

## CLI

Always on success: `processed.h5ad`, `report.md`, `result.json`,
`reproducibility/commands.sh`, `reproducibility/requirements.txt`,
`reproducibility/r_visualization.sh`, `figure_data/manifest.json`, and
`figures/manifest.json`.

Conditional files under `tables/`:

- `lr_interactions.csv` and `top_interactions.csv`: nonempty interactions.
- `communication_summary.csv`: nonempty aggregate.
- `signaling_roles.csv`: nonempty population scores.
- `source_target_summary.csv`: nonempty pair summary.
- `cellchat_pathways.csv`, `cellchat_centrality.csv`,
  `cellchat_count_matrix.csv`, `cellchat_weight_matrix.csv`: only when
  CellChat supplies the corresponding nonempty table.

`figure_data/` includes lr_interactions.csv, top_interactions.csv,
communication_summary.csv, signaling_roles.csv, source_target_summary.csv
and communication_run_summary.csv even when the corresponding data are empty.
communication_spatial_points.csv and communication_umap_points.csv require
their coordinates. Optional CellChat tables are also copied there.

Conditional PNGs under `figures/`: lr_dotplot.png, lr_heatmap.png,
signaling_roles.png and source_target_summary.png require suitable nonempty
tables; lr_spatial.png, communication_roles_spatial.png and
communication_hub_spatial.png require spatial coordinates;
communication_hub_umap.png uses available UMAP coordinates.
communication_pvalue_distribution.png and
communication_score_vs_significance.png require measured p values.
The gallery skips plots without usable data.

CellPhoneDB metadata, database CSVs, FastCCC input h5ad and the CellChat RDS
are temporary transport artifacts, not delivered report files.
No CLI replay capsule or top-level README is promised.
