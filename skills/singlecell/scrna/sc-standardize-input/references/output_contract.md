# Output contract

The CLI writes `processed.h5ad`, `report.md`, `result.json` and
`reproducibility/{commands.sh,requirements.txt}`. It does not write tables
or plots.

The standardized AnnData contains the selected counts in `X`,
`layers["counts"]` and `raw`. Its `uns` contains the input and matrix
contracts. `result.json["summary"]` reports the expression source, species,
feature-name source and warnings.

The API returns a new AnnData without writing files. Use `run_info` to
read its JSON diagnostics and `write_output` to save the object.
