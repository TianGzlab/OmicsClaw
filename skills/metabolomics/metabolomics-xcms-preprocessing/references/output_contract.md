## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── peak_table.csv
```

## File contents

- `tables/peak_table.csv` — feature-level peak table with columns `mz`, `rt`, plus per-sample intensity columns (long form). Written at `metabolomics_xcms_preprocessing.py:211`.
- `report.md` — Markdown summary with run parameters and feature count.
- `result.json` — standardised envelope with `summary` (`n_features`, `n_samples`, `ppm`, `peakwidth_min`, `peakwidth_max`) and `data` (empty).

## Notes

- No `figures/` directory is generated — this skill emits the peak table only.
- No `processed.h5ad` (this is a metabolomics file pipeline, not AnnData).
