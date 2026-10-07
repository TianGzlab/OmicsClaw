# Methodology

Mass matching requires a supplied reference with name, neutral_mass, database_id and formula, read through `--reference-file` in the CLI. No network lookup runs. `demo_reference()` or CLI `--demo` explicitly selects the 15-entry example reference.

`annotate` rejects missing reference data and relabelled demo references. Each query can have multiple candidate rows in `tables/annotations.csv`; Unknown rows retain unmatched queries. Confidence labels describe ppm bins, not identification probability.
