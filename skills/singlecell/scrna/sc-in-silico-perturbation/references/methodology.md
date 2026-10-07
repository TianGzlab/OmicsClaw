# Descriptive associations and R network analysis

The legacy grn_ko method selects high-variance genes plus the chosen target,
computes Pearson correlations from counts (or X), zeros the target row and
column, and reports mean absolute edge changes as dr_score. wt_ko_corr is the
absolute target correlation. The target itself loses all its edges, unlike
other genes, so its score has a different interpretation.

This is a descriptive correlation calculation, not a causal knockout model.
The previous normal-approximation p-values, z-score and FC alias were not
calibrated statistical tests and have been removed. Results are now ranked by
dr_score. The old corr-threshold CLI argument remains inactive for compatibility.

sctenifoldknk runs the separate R package through temporary genes-by-cells CSV
files. The checked-in R script calls set.seed before scTenifoldKnk and preserves
the backend's diffRegulation columns. Missing R packages and method failures
propagate; the skill does not install packages or substitute another algorithm.
