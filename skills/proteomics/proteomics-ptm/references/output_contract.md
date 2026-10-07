# Output contract

- tables/ptm_sites.csv
- tables/ptm_class_I_sites.csv
- report.md
- result.json
- `demo_ptm_sites.csv` is written only with `--demo`.

The CLI owns these files; the library returns DataFrames. Plotting functions return
Figures to the caller and do not add files to a CLI run.
