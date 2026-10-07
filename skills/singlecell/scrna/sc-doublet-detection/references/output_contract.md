# Output contract

The CLI writes `processed.h5ad`, `report.md`, `result.json`,
`tables/doublet_calls.csv`, `tables/summary.csv` and
`reproducibility/{commands.sh,requirements.txt}`.

`processed.h5ad` keeps all cells and adds `doublet_score`,
`predicted_doublet` and `doublet_classification` to `obs`.
`doublet_calls.csv` has one row per cell; `summary.csv` has singlet and
doublet counts and percentages. `tables/group_summary.csv` is conditional
on an available comparison group.

`figures/doublet_score_distribution.png` is the score histogram. Embedding
plots require an existing or successfully computed preview embedding.
The corresponding tables live in `figure_data/`, with a manifest.
Successful optional R renders live in `figures/r_enhanced/`.

`result.json["summary"]` records `requested_method`, `executed_method`,
`fallback_used` and `fallback_reason`. The API exposes these through
`run_info`; for scds, inspect `requested_scds_mode` and
`executed_scds_mode` as well.

The API writes no files. Its table and Figure helpers return objects for
`write_output`. Temporary R input matrices and method-specific result
CSVs are removed after the call.
