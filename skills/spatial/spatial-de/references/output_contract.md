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
│   ├── de_full.csv
│   ├── de_plot_points.csv
│   ├── de_run_summary.csv
│   ├── de_significant.csv
│   ├── de_spatial_points.csv
│   ├── de_umap_points.csv
│   ├── group_de_metrics.csv
│   ├── markers_top.csv
│   ├── sample_counts_by_group.csv
│   ├── skipped_sample_groups.csv
│   └── top_de_hits.csv
└── figures/
    ├── de_effect_burden_spatial.png
    ├── de_effect_burden_umap.png
    ├── de_group_spatial_context.png
    ├── de_marker_dotplot.png
    ├── de_marker_heatmap.png
    ├── de_pvalue_distribution.png
    ├── de_top_hits_barplot.png
    ├── de_volcano.png
    ├── group_de_burden.png
    ├── sample_counts_by_group.png
    └── skipped_sample_groups.png
```

## File contents

- `tables/de_full.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/de_plot_points.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/de_run_summary.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/de_significant.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/de_spatial_points.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/de_umap_points.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/group_de_metrics.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/markers_top.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/sample_counts_by_group.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/skipped_sample_groups.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `tables/top_de_hits.csv` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/de_effect_burden_spatial.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/de_effect_burden_umap.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/de_group_spatial_context.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/de_marker_dotplot.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/de_marker_heatmap.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/de_pvalue_distribution.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/de_top_hits_barplot.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/de_volcano.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/group_de_burden.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/sample_counts_by_group.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `figures/skipped_sample_groups.png` — written by `spatial_de.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_de.py`.
- `manifest.json` — written by `spatial_de.py`.
- `processed.h5ad` — written by `spatial_de.py`.
- `r_visualization.sh` — written by `spatial_de.py`.
- `requirements.txt` — written by `spatial_de.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_de.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
