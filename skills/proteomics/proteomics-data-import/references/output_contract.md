# Output contract

- tables/proteins.csv
- report.md
- result.json
- `demo_proteinGroups.txt` is written only with `--demo`.

The CLI owns these files; the library returns DataFrames. Plotting functions return
Figures to the caller and do not add files to a CLI run.
