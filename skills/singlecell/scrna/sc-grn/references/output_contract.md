# Output contract

The function library returns adjacency tables, regulon mappings, score
tables and figures; it writes no files. `infer_adjacencies` uses the supplied
TF list, and `run_info` names the actual inference method and any fallback.
`score_regulons(..., method="mean")` computes target-gene mean expression;
it is not AUCell. Full AUCell scoring requires its optional backend.

The CLI writes `processed.h5ad`, `tables/grn_adjacencies.csv`,
`tables/grn_regulons.csv`, `tables/grn_auc_matrix.csv`,
`tables/grn_regulon_targets.csv`, `report.md` and `result.json`.
The historical `auc_matrix` filename and `regulon_*` obs names are kept
for compatibility even for mean scores; read
`result.json.data.scoring_method` before interpreting them.
Plot-source CSVs are under `figure_data/`; R figures are optional.
The demo writes its own TF list only when no caller-supplied list is used.
