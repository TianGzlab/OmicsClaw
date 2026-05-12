## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── tables/
│   ├── dominant_types.csv
│   └── proportions.csv
└── figures/
    ├── mean_proportions_pie.png
    ├── proportions_heatmap.png
    └── proportions_stacked.png
```

## File contents

- `tables/dominant_types.csv` — written by `bulkrna_deconvolution.py` (or its imported `_lib/` helpers).
- `tables/proportions.csv` — written by `bulkrna_deconvolution.py` (or its imported `_lib/` helpers).
- `figures/mean_proportions_pie.png` — written by `bulkrna_deconvolution.py` (or its imported `_lib/` helpers).
- `figures/proportions_heatmap.png` — written by `bulkrna_deconvolution.py` (or its imported `_lib/` helpers).
- `figures/proportions_stacked.png` — written by `bulkrna_deconvolution.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `bulkrna_deconvolution.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_bulkrna_counts.csv` — generated only on `--demo`.

## Notes

Auto-generated from `bulkrna_deconvolution.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
