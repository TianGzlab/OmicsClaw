# Methodology

ttest is the CLI default; welch and mann_whitney are alternatives. Groups default to the first and second half of columns.

differential_abundance reports group2 minus group1. Nonpositive intensities do not enter the tests. significant uses BH-adjusted p values.
