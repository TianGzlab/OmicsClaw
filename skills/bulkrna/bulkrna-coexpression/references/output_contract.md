# Output contract

The CLI owns these files:

- `tables/module_assignments.csv`
- `tables/hub_genes.csv`
- `tables/threshold_fit.csv`
- `figures/scale_free_fit.png`
- `figures/module_sizes.png`
- `figures/module_dendrogram.png` (assignment overview, not a dendrogram)
- `report.md`, `result.json`
- `reproducibility/commands.sh`

The function library returns DataFrames and Figures. R matrix exchanges and
backend CSVs live in temporary directories and are removed after the call.
Backend diagnostics are available through `run_info` and the CLI's
`result.json` data section. Reports carry the research-use disclaimer.
