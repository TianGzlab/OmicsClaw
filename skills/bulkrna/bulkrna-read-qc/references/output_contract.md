## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   └── qc_summary.csv
└── figures/
    ├── gc_content.png
    ├── per_base_quality.png
    ├── quality_score_distribution.png
    └── read_length_distribution.png
```

## File contents

- `tables/qc_summary.csv` — written by `bulkrna_read_qc.py` (or its imported `_lib/` helpers).
- `figures/gc_content.png` — written by `bulkrna_read_qc.py` (or its imported `_lib/` helpers).
- `figures/per_base_quality.png` — written by `bulkrna_read_qc.py` (or its imported `_lib/` helpers).
- `figures/quality_score_distribution.png` — written by `bulkrna_read_qc.py` (or its imported `_lib/` helpers).
- `figures/read_length_distribution.png` — written by `bulkrna_read_qc.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_read_qc.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `bulkrna_read_qc.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
