## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── batch_info.csv
│   ├── batch_metrics.csv
│   ├── corrected_counts.csv
│   ├── corrected_expression.csv
│   └── counts.csv
└── figures/
    └── batch_assessment.png
```

## File contents

- `tables/batch_info.csv` — written by `bulkrna_batch_correction.py` (or its imported `_lib/` helpers).
- `tables/batch_metrics.csv` — written by `bulkrna_batch_correction.py` (or its imported `_lib/` helpers).
- `tables/corrected_counts.csv` — written by `bulkrna_batch_correction.py` (or its imported `_lib/` helpers).
- `tables/corrected_expression.csv` — written by `bulkrna_batch_correction.py` (or its imported `_lib/` helpers).
- `tables/counts.csv` — written by `bulkrna_batch_correction.py` (or its imported `_lib/` helpers).
- `figures/batch_assessment.png` — written by `bulkrna_batch_correction.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_batch_correction.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_bulkrna_batch_expr.csv` — generated only on `--demo`.
- `demo_bulkrna_batch_info.csv` — generated only on `--demo`.

## Notes

Auto-generated from `bulkrna_batch_correction.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
