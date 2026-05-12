## Output Structure

```
output_directory/
├── report.md
├── result.json
├── demo.vcf
├── filtered.vcf
└── tables/
    └── variants.csv
```

## File contents

- `tables/variants.csv` — written by `genomics_vcf_operations.py` (or its imported `_lib/` helpers).
- `demo.vcf` — written by `genomics_vcf_operations.py`.
- `filtered.vcf` — written by `genomics_vcf_operations.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `genomics_vcf_operations.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
