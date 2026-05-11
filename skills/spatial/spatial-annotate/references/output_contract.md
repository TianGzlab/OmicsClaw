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
│   ├── annotation_cell_type_counts.csv
│   ├── annotation_probabilities.csv
│   ├── annotation_spatial_points.csv
│   ├── annotation_summary.csv
│   ├── annotation_umap_points.csv
│   ├── cell_type_assignments.csv
│   ├── cluster_annotations.csv
│   └── marker_overlap_scores.csv
└── figures/
    ├── annotation_confidence_histogram.png
    ├── annotation_confidence_spatial.png
    ├── annotation_probability_heatmap.png
    ├── cell_type_barplot.png
    ├── cell_type_spatial.png
    ├── cell_type_umap.png
    └── marker_overlap_heatmap.png
```

## File contents

- `tables/annotation_cell_type_counts.csv` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `tables/annotation_probabilities.csv` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `tables/annotation_spatial_points.csv` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `tables/annotation_summary.csv` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `tables/annotation_umap_points.csv` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `tables/cell_type_assignments.csv` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `tables/cluster_annotations.csv` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `tables/marker_overlap_scores.csv` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `figures/annotation_confidence_histogram.png` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `figures/annotation_confidence_spatial.png` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `figures/annotation_probability_heatmap.png` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `figures/cell_type_barplot.png` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `figures/cell_type_spatial.png` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `figures/cell_type_umap.png` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `figures/marker_overlap_heatmap.png` — written by `spatial_annotate.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_annotate.py`.
- `manifest.json` — written by `spatial_annotate.py`.
- `processed.h5ad` — written by `spatial_annotate.py`.
- `r_visualization.sh` — written by `spatial_annotate.py`.
- `requirements.txt` — written by `spatial_annotate.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_annotate.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
