## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── structural_variants.csv
```

## File contents

- `tables/structural_variants.csv` — written by `sv_detection.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_structural_variants.vcf` — generated only on `--demo`.

## Notes

Auto-generated from `sv_detection.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
