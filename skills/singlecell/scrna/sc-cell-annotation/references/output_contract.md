## Output Structure

```
output_directory/
├── report.md
├── result.json
├── _demo_ref.h5ad
├── analysis_summary.txt
├── commands.sh
├── input.h5ad
├── manifest.json
├── processed.h5ad
├── requirements.txt
├── tables/
│   ├── annotation_embedding_points.csv
│   ├── annotation_summary.csv
│   ├── cell_metadata.csv
│   ├── cell_type_counts.csv
│   ├── cellmarker2_markers.csv
│   ├── cluster_annotation_matrix.csv
│   ├── popv_predictions.csv
│   ├── scmap_results.csv
│   └── singler_results.csv
└── figures/
    ├── cell_type_counts.png
    ├── cluster_to_cell_type_heatmap.png
    ├── embedding_annotation_score.png
    ├── embedding_cell_type.png
    ├── embedding_cluster_vs_cell_type.png
    ├── r_cell_barplot.png
    ├── r_cell_proportion.png
    ├── r_cell_sankey.png
    ├── r_embedding_discrete.png
    └── r_embedding_feature.png
```

## File contents

- `tables/annotation_embedding_points.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `tables/annotation_summary.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `tables/cell_metadata.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `tables/cell_type_counts.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `tables/cellmarker2_markers.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `tables/cluster_annotation_matrix.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `tables/popv_predictions.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `tables/scmap_results.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `tables/singler_results.csv` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/cell_type_counts.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/cluster_to_cell_type_heatmap.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/embedding_annotation_score.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/embedding_cell_type.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/embedding_cluster_vs_cell_type.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/r_cell_barplot.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/r_cell_proportion.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/r_cell_sankey.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_discrete.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `figures/r_embedding_feature.png` — written by `sc_annotate.py` (or its imported `_lib/` helpers).
- `_demo_ref.h5ad` — written by `sc_annotate.py`.
- `analysis_summary.txt` — written by `sc_annotate.py`.
- `commands.sh` — written by `sc_annotate.py`.
- `input.h5ad` — written by `sc_annotate.py`.
- `manifest.json` — written by `sc_annotate.py`.
- `processed.h5ad` — written by `sc_annotate.py`.
- `requirements.txt` — written by `sc_annotate.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `sc_annotate.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
