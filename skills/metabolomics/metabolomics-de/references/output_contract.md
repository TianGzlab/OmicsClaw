## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   └── pca_scores.png            (best-effort, ≥ 3 samples per group)
└── tables/
    ├── differential_features.csv
    └── significant_features.csv
```

## File contents

- `tables/differential_features.csv` — per-feature univariate t-test result with columns including `feature`, `group_a_mean`, `group_b_mean`, `log2fc`, `pvalue`, `fdr` (BH-adjusted). Written at `met_diff.py:301`.
- `tables/significant_features.csv` — subset filtered by HARD-CODED `fdr < 0.05` (no `--alpha` flag). Written at `met_diff.py:305`.
- `figures/pca_scores.png` — 2D PCA scatter colored by group, written best-effort by `run_pca` (`met_diff.py:216`); silently skipped on small inputs.
- `report.md` — run parameters (group prefixes) plus significance counts.
- `result.json` — `summary` includes `n_features`, `n_significant`, group sizes.

## Notes

- FDR threshold is hard-coded at 0.05 (use `metabolomics-statistics` for tunable `--alpha`).
- Test backend is fixed at Welch t-test (use `metabolomics-statistics` for Wilcoxon / ANOVA / Kruskal).
