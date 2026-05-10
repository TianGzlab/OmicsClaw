## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── quantified_features.csv
```

## File contents

- `tables/quantified_features.csv` — feature × sample table after imputation + normalisation, same wide-form shape as the input. Written at `met_quantify.py:294`.
- `report.md` — run parameters (`--impute`, `--normalize`) plus per-feature missingness summary.
- `result.json` — `summary` includes `n_features`, `n_samples`, `impute`, `normalize`, plus pre/post imputation NA counts.

## Notes

- No `figures/` directory.
- Imputation runs BEFORE normalisation; ordering matters for the `min` strategy.
