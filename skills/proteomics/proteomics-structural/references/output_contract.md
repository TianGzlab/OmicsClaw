# Output contract

- tables/crosslinks.csv
- tables/inter_protein_crosslinks.csv (when link_type exists; can be empty)
- report.md
- result.json
- `demo_crosslinks.csv` is written only with `--demo`.

The CLI owns these files; the library returns DataFrames. Plotting functions return
Figures to the caller and do not add files to a CLI run.
