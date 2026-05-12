## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── annotations.csv
```

## File contents

- `tables/annotations.csv` — per-feature annotation match against the 15-entry `DEMO_METABOLITES` list (`metabolomics_annotation.py:57-74`). Columns: input `feature_id` / `mz`, plus matched `name`, `hmdb_id`, `formula`, `adduct`, `mass_error_ppm`. Written at `metabolomics_annotation.py:279`.
- `report.md` — number of features matched, per-database / per-adduct counts.
- `result.json` — `summary` includes `n_features`, `n_annotated`, `database` (recorded value, NOT used for lookup), `ppm`, `adducts`.

## Notes

- No `figures/` directory.
- A feature with multiple matching candidates yields multiple rows.
- The `--database` flag is metadata-only — annotation always uses the embedded HMDB list regardless.
