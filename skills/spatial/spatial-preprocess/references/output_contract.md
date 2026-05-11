## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── environment.txt
├── manifest.json
├── processed.h5ad
├── r_visualization.sh
├── tables/
│   ├── cluster_summary.csv
│   ├── multi_resolution_summary.csv
│   ├── pca_variance_ratio.csv
│   ├── preprocess_run_summary.csv
│   ├── preprocess_spatial_points.csv
│   ├── preprocess_umap_points.csv
│   ├── qc_metric_distributions.csv
│   └── qc_summary.csv
└── figures/
    ├── cluster_size_barplot.png
    ├── leiden_resolution_sweep.png
    ├── pca_variance_curve.png
    ├── qc_metric_distributions.png
    ├── qc_metrics_spatial.png
    ├── spatial_leiden.png
    └── umap_leiden.png
```

## File contents

- `tables/cluster_summary.csv` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `tables/multi_resolution_summary.csv` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `tables/pca_variance_ratio.csv` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `tables/preprocess_run_summary.csv` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `tables/preprocess_spatial_points.csv` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `tables/preprocess_umap_points.csv` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `tables/qc_metric_distributions.csv` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `tables/qc_summary.csv` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `figures/cluster_size_barplot.png` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `figures/leiden_resolution_sweep.png` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `figures/pca_variance_curve.png` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `figures/qc_metric_distributions.png` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `figures/qc_metrics_spatial.png` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `figures/spatial_leiden.png` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `figures/umap_leiden.png` — written by `spatial_preprocess.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_preprocess.py`.
- `environment.txt` — written by `spatial_preprocess.py`.
- `manifest.json` — written by `spatial_preprocess.py`.
- `processed.h5ad` — written by `spatial_preprocess.py`.
- `r_visualization.sh` — written by `spatial_preprocess.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

### Demo-only outputs

- `demo_visium.h5ad` — generated only on `--demo`.

## Notes

Auto-generated from `spatial_preprocess.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
