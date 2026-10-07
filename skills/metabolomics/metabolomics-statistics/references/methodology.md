# Methodology

The wilcoxon label calls scipy.stats.ranksums, not paired Wilcoxon or Mann-Whitney U. ANOVA and Kruskal accept exactly two groups here. BH FDR covers every returned feature.

`test_groups` falls back to midpoint grouping with a warning when both prefixes are not supplied; run_info records the columns. `tables/significant.csv` uses fdr < alpha. log2fc is group2/group1.
