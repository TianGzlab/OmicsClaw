# Methodology

Welch tests use raw supplied intensities, with BH FDR and a fixed CLI significance threshold of 0.05. PCA uses untransformed intensities and converts NaNs to zero.

`differential_expression` treats the first column as feature IDs. Both groups must be nonempty and disjoint. `tables/significant_features.csv` uses fdr < 0.05. The CLI logs optional PCA failures.
