# Output contract

The CLI owns these files:

- `tables/survival_results.csv`
- `figures/km_<gene>.png` per successful gene
- `figures/forest_plot.png` when at least two genes succeed
- `report.md`, `result.json`
- `reproducibility/commands.sh`

The function library returns DataFrames and Figures. R matrix exchanges and
backend CSVs live in temporary directories and are removed after the call.
Backend diagnostics are available through `run_info` and the CLI's
`result.json` data section. Reports carry the research-use disclaimer.
