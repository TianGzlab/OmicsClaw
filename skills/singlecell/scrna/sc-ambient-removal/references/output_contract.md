## Output Structure

```
output_directory/
├── report.md
├── result.json
├── README.md
├── analysis_summary.txt
├── cellbender_output_report.html
├── commands.sh
├── contamination.json
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── cell_metadata.csv
│   ├── cellbender_output_cell_barcodes.csv
│   ├── cellbender_output_metrics.csv
│   ├── cells.csv
│   ├── corrected_counts.csv
│   ├── correction_summary.csv
│   ├── gene_expression.csv
│   └── genes.csv
└── figures/
    ├── barcode_rank.png
    ├── count_distribution.png
    ├── counts_comparison.png
    └── r_ambient_violin.png
```

## File contents

- `tables/cell_metadata.csv` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `tables/cellbender_output_cell_barcodes.csv` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `tables/cellbender_output_metrics.csv` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `tables/cells.csv` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `tables/corrected_counts.csv` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `tables/correction_summary.csv` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `tables/genes.csv` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `figures/barcode_rank.png` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `figures/count_distribution.png` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `figures/counts_comparison.png` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `figures/r_ambient_violin.png` — written by `sc_ambient.py` (or its imported `_lib/` helpers).
- `README.md` — written by `sc_ambient.py`.
- `analysis_summary.txt` — written by `sc_ambient.py`.
- `cellbender_output_report.html` — written by `sc_ambient.py`.
- `commands.sh` — written by `sc_ambient.py`.
- `contamination.json` — written by `sc_ambient.py`.
- `manifest.json` — written by `sc_ambient.py`.
- `processed.h5ad` — written by `sc_ambient.py`.
- `requirements.txt` — written by `sc_ambient.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_ambient.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
