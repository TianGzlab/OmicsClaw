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
│   ├── cluster_de_metrics.csv
│   ├── condition_run_summary.csv
│   ├── condition_spatial_points.csv
│   ├── condition_umap_points.csv
│   ├── per_cluster_summary.csv
│   ├── pseudobulk_de.csv
│   ├── pseudobulk_volcano_points.csv
│   ├── sample_counts_by_condition.csv
│   ├── skipped_contrasts.csv
│   └── top_de_genes.csv
└── figures/
    ├── cluster_de_burden.png
    ├── condition_de_barplot.png
    ├── condition_effect_burden_spatial.png
    ├── condition_effect_burden_umap.png
    ├── condition_pvalue_distribution.png
    ├── condition_spatial_context.png
    ├── pseudobulk_volcano.png
    ├── sample_counts_by_condition.png
    └── skipped_contrasts.png
```

## File contents

- `tables/cluster_de_metrics.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/condition_run_summary.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/condition_spatial_points.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/condition_umap_points.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/per_cluster_summary.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/pseudobulk_de.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/pseudobulk_volcano_points.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/sample_counts_by_condition.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/skipped_contrasts.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `tables/top_de_genes.csv` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/cluster_de_burden.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/condition_de_barplot.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/condition_effect_burden_spatial.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/condition_effect_burden_umap.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/condition_pvalue_distribution.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/condition_spatial_context.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/pseudobulk_volcano.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/sample_counts_by_condition.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `figures/skipped_contrasts.png` — written by `spatial_condition.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_condition.py`.
- `manifest.json` — written by `spatial_condition.py`.
- `processed.h5ad` — written by `spatial_condition.py`.
- `r_visualization.sh` — written by `spatial_condition.py`.
- `requirements.txt` — written by `spatial_condition.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_condition.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
