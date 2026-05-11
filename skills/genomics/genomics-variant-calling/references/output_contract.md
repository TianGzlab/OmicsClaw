## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    ├── variants.csv
    └── variants_per_chrom.csv
```

## File contents

- `tables/variants.csv` — written by `genomics_variant_calling.py` (or its imported `_lib/` helpers).
- `tables/variants_per_chrom.csv` — written by `genomics_variant_calling.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_variants.vcf` — generated only on `--demo`.

## Notes

Auto-generated from `genomics_variant_calling.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
