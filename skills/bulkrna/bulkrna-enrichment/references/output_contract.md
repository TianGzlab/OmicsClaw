## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── enrichment_results.csv
│   └── enrichment_significant.csv
└── figures/
    ├── enrichment_barplot.png
    └── enrichment_dotplot.png
```

## File contents

- `tables/enrichment_results.csv` — written by `bulkrna_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_significant.csv` — written by `bulkrna_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_barplot.png` — written by `bulkrna_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_dotplot.png` — written by `bulkrna_enrichment.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_enrichment.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `bulkrna_enrichment.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
