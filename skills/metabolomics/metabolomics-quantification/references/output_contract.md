# Output contract

`tables/quantified_features.csv`, `report.md` and `result.json`. Demo mode also writes its synthetic input CSV at the output root.

The function library returns tables and Figures without file writes.
`run_info` reads DataFrame diagnostics; `keep=False` removes them.

`quantify` detects sample/intensity prefixes, then numeric columns excluding feature_id, mz, rt, name and id. Every sample needs a positive observed intensity; completely missing samples raise ValueError for all methods.
