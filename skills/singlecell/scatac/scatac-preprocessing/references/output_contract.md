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
│   ├── cluster_summary.csv
│   ├── lsi_variance_ratio.csv
│   ├── peak_summary.csv
│   ├── preprocess_summary.csv
│   ├── qc_metrics_per_cell.csv
│   └── umap_points.csv
└── figures/
    ├── clustering_comparison.png
    ├── feature_umap.png
    ├── lsi_variance.png
    ├── pca_loadings.png
    ├── pca_scatter.png
    ├── pca_variance.png
    ├── qc_violin.png
    └── top_accessible_peaks.png
```

## File contents

- `tables/cell_metadata.csv` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `tables/cluster_summary.csv` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `tables/lsi_variance_ratio.csv` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `tables/peak_summary.csv` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `tables/preprocess_summary.csv` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `tables/qc_metrics_per_cell.csv` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `tables/umap_points.csv` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `figures/clustering_comparison.png` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `figures/feature_umap.png` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `figures/lsi_variance.png` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `figures/pca_loadings.png` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `figures/pca_scatter.png` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `figures/pca_variance.png` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `figures/qc_violin.png` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `figures/top_accessible_peaks.png` — written by `scatac_preprocessing.py` (or its imported `_lib/` helpers).
- `analysis_summary.txt` — written by `scatac_preprocessing.py`.
- `commands.sh` — written by `scatac_preprocessing.py`.
- `manifest.json` — written by `scatac_preprocessing.py`.
- `processed.h5ad` — written by `scatac_preprocessing.py`.
- `requirements.txt` — written by `scatac_preprocessing.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `scatac_preprocessing.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
