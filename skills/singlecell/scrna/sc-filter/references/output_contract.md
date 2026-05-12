## Output Structure

```
output_directory/
├── report.md
├── result.json
├── analysis_summary.txt
├── commands.sh
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── cell_metadata.csv
│   ├── filter_reasons.csv
│   ├── filter_state.csv
│   ├── filter_stats.csv
│   ├── filter_summary.csv
│   ├── gene_expression.csv
│   └── retention_summary.csv
└── figures/
    ├── filter_comparison.png
    ├── filter_reason_summary.png
    ├── filter_state_scatter.png
    ├── filter_summary.png
    ├── filter_thresholds.png
    └── r_feature_violin.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `tables/filter_reasons.csv` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `tables/filter_state.csv` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `tables/filter_stats.csv` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `tables/filter_summary.csv` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `tables/retention_summary.csv` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `figures/filter_comparison.png` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `figures/filter_reason_summary.png` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `figures/filter_state_scatter.png` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `figures/filter_summary.png` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `figures/filter_thresholds.png` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `figures/r_feature_violin.png` — written by `sc_filter.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_filter.py`.
- `commands.sh` — written by `sc_filter.py`.
- `manifest.json` — written by `sc_filter.py`.
- `processed.h5ad` — written by `sc_filter.py`.
- `requirements.txt` — written by `sc_filter.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_filter.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
