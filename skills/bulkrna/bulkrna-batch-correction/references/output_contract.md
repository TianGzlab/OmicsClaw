# Output contract

The CLI owns these files:

- `tables/corrected_expression.csv`
- `tables/batch_metrics.csv`
- `figures/pca_before_correction.png`
- `figures/pca_after_correction.png`
- `figures/batch_assessment.png`
- `report.md`, `result.json`
- `reproducibility/commands.sh`

The function library returns DataFrames and Figures. R matrix exchanges and
backend CSVs live in temporary directories and are removed after the call.
Backend diagnostics are available through `run_info` and the CLI's
`result.json` data section. Reports carry the research-use disclaimer.
