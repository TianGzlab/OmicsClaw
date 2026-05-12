## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    ├── annotated_variants.csv
    └── impact_distribution.csv
```

## File contents

- `tables/annotated_variants.csv` — written by `variant_annotation.py` (or its imported `_lib/` helpers).
- `tables/impact_distribution.csv` — written by `variant_annotation.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_annotated_variants.csv` — generated only on `--demo`.

## Notes

Auto-generated from `variant_annotation.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
