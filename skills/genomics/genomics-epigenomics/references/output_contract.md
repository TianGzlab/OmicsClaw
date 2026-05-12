## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    ├── peaks_per_chromosome.csv
    └── peaks_summary.csv
```

## File contents

- `tables/peaks_per_chromosome.csv` — written by `genomics_epigenomics.py` (or its imported `_lib/` helpers).
- `tables/peaks_summary.csv` — written by `genomics_epigenomics.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `genomics_epigenomics.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
