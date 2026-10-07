# Output contract

- tables/enrichment_results.csv
- report.md
- result.json
- `demo_proteins.csv` is written only with `--demo`.

The CLI owns these files; the library returns DataFrames. Plotting functions return
Figures to the caller and do not add files to a CLI run.
