## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── clinical.csv
│   ├── expr.csv
│   ├── km_data.csv
│   └── survival_results.csv
└── figures/
    └── forest_plot.png
```

## File contents

- `tables/clinical.csv` — written by `bulkrna_survival.py` (or its imported `_lib/` helpers).
- `tables/expr.csv` — written by `bulkrna_survival.py` (or its imported `_lib/` helpers).
- `tables/km_data.csv` — written by `bulkrna_survival.py` (or its imported `_lib/` helpers).
- `tables/survival_results.csv` — written by `bulkrna_survival.py` (or its imported `_lib/` helpers).
- `figures/forest_plot.png` — written by `bulkrna_survival.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_survival.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_bulkrna_survival_clinical.csv` — generated only on `--demo`.
- `demo_bulkrna_survival_expr.csv` — generated only on `--demo`.

## Notes

Auto-generated from `bulkrna_survival.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
