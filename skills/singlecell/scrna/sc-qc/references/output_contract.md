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
│   ├── barcode_rank_curve.csv
│   ├── cell_metadata.csv
│   ├── gene_expression.csv
│   ├── highest_expr_genes.csv
│   ├── qc_metric_correlations.csv
│   ├── qc_metrics_per_cell.csv
│   ├── qc_metrics_summary.csv
│   └── qc_run_summary.csv
└── figures/
    ├── barcode_rank.png
    ├── highest_expr_genes.png
    ├── qc_correlation_heatmap.png
    ├── qc_histograms.png
    ├── qc_scatter.png
    ├── qc_violin.png
    └── r_qc_violin.png
```

## File contents

- `tables/barcode_rank_curve.csv` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `tables/gene_expression.csv` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `tables/highest_expr_genes.csv` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `tables/qc_metric_correlations.csv` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `tables/qc_metrics_per_cell.csv` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `tables/qc_metrics_summary.csv` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `tables/qc_run_summary.csv` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `figures/barcode_rank.png` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `figures/highest_expr_genes.png` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `figures/qc_correlation_heatmap.png` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `figures/qc_histograms.png` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `figures/qc_scatter.png` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `figures/qc_violin.png` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `figures/r_qc_violin.png` — written by `sc_qc.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `sc_qc.py`.
- `commands.sh` — written by `sc_qc.py`.
- `manifest.json` — written by `sc_qc.py`.
- `processed.h5ad` — written by `sc_qc.py`.
- `requirements.txt` — written by `sc_qc.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_qc.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
