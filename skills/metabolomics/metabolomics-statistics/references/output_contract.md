## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    ├── statistics.csv
    └── significant.csv
```

## File contents

- `tables/statistics.csv` — per-feature univariate test result with columns `feature`, `group1_mean`, `group2_mean`, `fold_change`, `log2fc`, `statistic`, `pvalue`, `fdr` (BH-adjusted). Written at `metabolomics_statistics.py:360`.
- `tables/significant.csv` — subset of `statistics.csv` filtered by `fdr < args.alpha`. Written at `metabolomics_statistics.py:363`.
- `report.md` — run parameters (`--method`, `--alpha`, group prefixes) plus significance counts.
- `result.json` — `summary` includes `method`, `alpha`, `n_features`, `n_significant`, group sizes.

## Notes

- No `figures/` directory.
- Group columns are derived from `--group1-prefix` / `--group2-prefix` when both are passed; otherwise midpoint split with a warning.
