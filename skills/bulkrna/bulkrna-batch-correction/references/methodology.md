# Batch correction methods

The R backend calls `sva::ComBat` on the supplied expression scale. It
supports parametric or non-parametric empirical Bayes and an optional
`condition` covariate. The input is not automatically transformed.

The Python backend retains the repository's parametric location/scale
shrinkage approximation. It is not numerically interchangeable with sva
and does not preserve condition covariates. Automatic fallback is allowed
only for parametric correction without those covariates; it warns and
records the requested method, executed method and reason.

PCA uses signed log2(1+abs(x)), then gene-centering and SVD. This accepts
negative corrected values. The silhouette score measures batch separation
in the first two PCs; no kBET statistic is computed and batches are never
inferred from sample names.

Use corrected expression for visualization or exploratory networks.
Differential count models should use the original counts with an appropriate
batch covariate. Confounded batch and condition cannot be separated by this
correction alone.
