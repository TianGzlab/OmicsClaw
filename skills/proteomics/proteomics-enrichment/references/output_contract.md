## Output Structure

```
output_directory/
├── report.md
├── result.json
└── tables/
    └── enrichment_results.csv
```

## File contents

- `tables/enrichment_results.csv` — written by `prot_enrichment.py` (or its imported `_lib/` helpers).
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_proteins.csv` — generated only on `--demo`.

## Notes

Auto-generated from `prot_enrichment.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
