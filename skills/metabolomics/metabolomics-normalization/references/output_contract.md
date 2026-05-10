## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── normalized.csv
```

## File contents

- `tables/normalized.csv` — feature × sample table after the chosen normalisation, same wide-form shape as the input (preserves the index). Written at `metabolomics_normalization.py:258`.
- `report.md` — run parameters (`--method`) plus pre/post per-sample summary statistics.
- `result.json` — `summary` includes `n_features`, `n_samples`, `method`.

## Notes

- No `figures/` directory.
- No imputation is performed — NaN values pass through (most methods skipna).
