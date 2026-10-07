# Output contract

`tables/normalized.csv`, `report.md` and `result.json`. The CLI writes `reproducibility/commands.sh`.

The function library returns tables and Figures without file writes.
`run_info` reads DataFrame diagnostics; `keep=False` removes them.

`normalize` preserves NaNs according to the method and performs no imputation. Zero divisors become NaN. The input index is retained in `tables/normalized.csv`.
