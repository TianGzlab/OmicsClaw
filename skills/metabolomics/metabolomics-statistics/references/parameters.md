# Parameters

Run `python skills/metabolomics/metabolomics-statistics/metabolomics_statistics.py --help` for CLI flags.
The generated API section in [SKILL.md](../SKILL.md) defines function defaults.

The wilcoxon label calls scipy.stats.ranksums, not paired Wilcoxon or Mann-Whitney U. ANOVA and Kruskal accept exactly two groups here. BH FDR covers every returned feature.
