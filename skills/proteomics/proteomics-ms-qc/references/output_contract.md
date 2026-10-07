# Output contract

- tables/qc_metrics.csv
- report.md
- result.json
- `demo_proteomics.csv` is written only with `--demo`.

- `reproducibility/commands.sh` records the CLI invocation template.

The CLI owns these files; the library returns DataFrames. Plotting functions return
Figures to the caller and do not add files to a CLI run.
