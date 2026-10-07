# Outputs

The Python API returns in-memory objects and figures. It does not create a
report directory. Examples persist selected objects with `write_output`.

The standalone CLI writes `processed.h5ad`, `report.md` and `result.json`.
Its plots are under `figures/`; plot source tables are under `figure_data/`.
R exchange files live in temporary directories, not under `tables/`.

## Tables

All methods write sample-by-cell-type counts and proportions, plus
condition means, under `tables/sample_by_celltype_counts.csv`,
`tables/sample_by_celltype_proportions.csv` and
`tables/condition_mean_proportions.csv`.

Only the selected method writes its result table:

- `simple_da_results.csv`: cell type, contrast, group means, log2 fold change, U statistic, p-value, BH-adjusted p-value and significance flag.
- `milo_nhood_results.csv`: neighborhood statistics. Columns depend on official Milo versus the internal Milo-like backend; `backend` identifies the calculation.
- `sccoda_effects.csv`: the selected scCODA backend's effect table.
- `proportion_test_results.csv`: nonempty R permutation results with observed log2 difference, FDR and bootstrap intervals.

The CLI also writes `annotated_input.h5ad`. Plots depend on the method and
nonempty usable columns; R-enhanced plots require `--r-enhanced`.

## Diagnostics

`run_info(table)` distinguishes official Milo from `milo_like`, and
pertpy scCODA from standalone scCODA. It records fallback reasons and
effective seed limitations. CLI `result.json["summary"]["backend"]` names
the executed backend. R permutation errors now propagate; an empty
successful result is not substituted for a failed R process.
