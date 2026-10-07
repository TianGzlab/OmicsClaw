# Output contract

- tables/protein_abundance.csv
- report.md
- result.json
- `reproducibility/commands.sh` records the CLI invocation template.

The CLI owns these files; the library returns DataFrames. Plotting functions return
Figures to the caller and do not add files to a CLI run.
