## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    ├── phase_blocks.csv
    └── phased_variants.csv
```

## File contents

- `tables/phase_blocks.csv` — written by `genomics_phasing.py` (or its imported `_lib/` helpers).
- `tables/phased_variants.csv` — written by `genomics_phasing.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_phased.vcf` — generated only on `--demo`.

## Notes

Auto-generated from `genomics_phasing.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
