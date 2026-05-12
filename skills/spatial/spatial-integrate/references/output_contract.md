## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── manifest.json
├── processed.h5ad
├── r_visualization.sh
├── requirements.txt
├── tables/
│   ├── batch_sizes.csv
│   ├── corrected_embedding_points.csv
│   ├── integration_metrics.csv
│   ├── integration_observations.csv
│   ├── umap_after_points.csv
│   └── umap_before_points.csv
└── figures/
    ├── batch_entropy_after_umap.png
    ├── batch_entropy_distribution.png
    ├── batch_highlight.png
    ├── batch_mixing.png
    ├── batch_sizes.png
    ├── umap_before_by_batch.png
    ├── umap_by_batch.png
    └── umap_by_cluster.png
```

## File contents

- `tables/batch_sizes.csv` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `tables/corrected_embedding_points.csv` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `tables/integration_metrics.csv` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `tables/integration_observations.csv` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `tables/umap_after_points.csv` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `tables/umap_before_points.csv` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `figures/batch_entropy_after_umap.png` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `figures/batch_entropy_distribution.png` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `figures/batch_highlight.png` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `figures/batch_mixing.png` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `figures/batch_sizes.png` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `figures/umap_before_by_batch.png` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `figures/umap_by_batch.png` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `figures/umap_by_cluster.png` — written by `spatial_integrate.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_integrate.py`.
- `manifest.json` — written by `spatial_integrate.py`.
- `processed.h5ad` — written by `spatial_integrate.py`.
- `r_visualization.sh` — written by `spatial_integrate.py`.
- `requirements.txt` — written by `spatial_integrate.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_integrate.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
