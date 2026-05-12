## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   └── alignment_stats.csv
└── figures/
    ├── alignment_composition.png
    ├── gene_body_coverage.png
    └── mapping_summary.png
```

## File contents

- `tables/alignment_stats.csv` — written by `bulkrna_read_alignment.py` (or its imported `_lib/` helpers).
- `figures/alignment_composition.png` — written by `bulkrna_read_alignment.py` (or its imported `_lib/` helpers).
- `figures/gene_body_coverage.png` — written by `bulkrna_read_alignment.py` (or its imported `_lib/` helpers).
- `figures/mapping_summary.png` — written by `bulkrna_read_alignment.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_read_alignment.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `bulkrna_read_alignment.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
