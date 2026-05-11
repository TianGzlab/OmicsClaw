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
│   ├── card_proportions.csv
│   ├── card_refined_proportions.csv
│   ├── celltype_diversity.csv
│   ├── deconv_run_summary.csv
│   ├── deconv_spatial_points.csv
│   ├── deconv_spot_metrics.csv
│   ├── deconv_umap_points.csv
│   ├── dominant_celltype.csv
│   ├── dominant_celltype_counts.csv
│   ├── mean_proportions.csv
│   ├── proportions.csv
│   ├── rctd_proportions.csv
│   ├── ref_celltypes.csv
│   ├── ref_counts.csv
│   ├── ref_meta.csv
│   ├── spatial_coords.csv
│   ├── spatial_counts.csv
│   └── spotlight_proportions.csv
└── figures/
    ├── assignment_margin_distribution.png
    ├── assignment_margin_spatial.png
    ├── celltype_diversity.png
    ├── dominant_celltype.png
    ├── dominant_celltype_distribution.png
    ├── mean_proportions.png
    ├── spatial_proportions.png
    └── umap_proportions.png
```

## File contents

- `tables/card_proportions.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/card_refined_proportions.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/celltype_diversity.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/deconv_run_summary.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/deconv_spatial_points.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/deconv_spot_metrics.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/deconv_umap_points.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/dominant_celltype.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/dominant_celltype_counts.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/mean_proportions.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/proportions.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/rctd_proportions.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/ref_celltypes.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/ref_counts.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/ref_meta.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/spatial_coords.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/spatial_counts.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `tables/spotlight_proportions.csv` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `figures/assignment_margin_distribution.png` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `figures/assignment_margin_spatial.png` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `figures/celltype_diversity.png` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `figures/dominant_celltype.png` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `figures/dominant_celltype_distribution.png` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `figures/mean_proportions.png` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `figures/spatial_proportions.png` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `figures/umap_proportions.png` — written by `spatial_deconv.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_deconv.py`.
- `environment.txt` — written by `spatial_deconv.py`.
- `manifest.json` — written by `spatial_deconv.py`.
- `processed.h5ad` — written by `spatial_deconv.py`.
- `r_visualization.sh` — written by `spatial_deconv.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_deconv.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
