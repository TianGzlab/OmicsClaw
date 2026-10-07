# Output contract

`tables/statistics.csv`, `report.md` and `result.json`. The CLI also writes `tables/significant.csv`. The CLI writes `reproducibility/commands.sh`.

The function library returns tables and Figures without file writes.
`run_info` reads DataFrame diagnostics; `keep=False` removes them.

`test_groups` falls back to midpoint grouping with a warning when both prefixes are not supplied; run_info records the columns. `tables/significant.csv` uses fdr < alpha. log2fc is group2/group1.
