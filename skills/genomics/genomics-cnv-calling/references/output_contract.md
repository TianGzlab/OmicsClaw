## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    ├── cnv_per_chromosome.csv
    └── cnv_segments.csv
```

## File contents

- `tables/cnv_per_chromosome.csv` — written by `genomics_cnv_calling.py` (or its imported `_lib/` helpers).
- `tables/cnv_segments.csv` — written by `genomics_cnv_calling.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_cnv_bins.csv` — generated only on `--demo`.

## Notes

Auto-generated from `genomics_cnv_calling.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
