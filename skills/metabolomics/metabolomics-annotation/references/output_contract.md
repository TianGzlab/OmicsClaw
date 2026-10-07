# Output contract

`tables/annotations.csv`, `report.md` and `result.json`. The CLI writes `reproducibility/commands.sh`.

The function library returns tables and Figures without file writes.
`run_info` reads DataFrame diagnostics; `keep=False` removes them.

`annotate` rejects missing reference data. Each query can have multiple candidate rows in `tables/annotations.csv`; Unknown rows retain unmatched queries. Confidence labels describe ppm bins, not identification probability. `result.json` preserves `data.run_info.reference_scope` as demo or provided.
