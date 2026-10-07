# Output contract

`tables/differential_features.csv`, `report.md` and `result.json`. The CLI also writes `tables/significant_features.csv` and, when PCA succeeds, `figures/pca_scores.png`. Demo mode also writes its synthetic input CSV at the output root.

The function library returns tables and Figures without file writes.
`run_info` reads DataFrame diagnostics; `keep=False` removes them.

`differential_expression` treats the first column as feature IDs. Both groups must be nonempty and disjoint. `tables/significant_features.csv` uses fdr < 0.05. The CLI logs optional PCA failures.
