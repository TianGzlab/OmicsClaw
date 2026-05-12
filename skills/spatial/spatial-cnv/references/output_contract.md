## Output Structure

```
output_directory/
├── report.md
├── result.json
├── commands.sh
├── manifest.json
├── numbat_input.h5ad
├── processed.h5ad
├── r_visualization.sh
├── tables/
│   ├── allele_counts.csv
│   ├── cnv_bin_summary.csv
│   ├── cnv_group_sizes.csv
│   ├── cnv_run_summary.csv
│   ├── cnv_scores.csv
│   ├── cnv_spatial_points.csv
│   ├── cnv_umap_points.csv
│   ├── numbat_calls.csv
│   ├── numbat_clone_post.csv
│   └── numbat_results.csv
└── figures/
    ├── cnv_bin_summary.png
    ├── cnv_group_sizes.png
    ├── cnv_groups_umap.png
    ├── cnv_heatmap.png
    ├── cnv_score_distribution.png
    ├── cnv_spatial.png
    ├── cnv_umap.png
    ├── cnv_uncertainty_distribution.png
    └── cnv_uncertainty_spatial.png
```

## File contents

- `tables/allele_counts.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/cnv_bin_summary.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/cnv_group_sizes.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/cnv_run_summary.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/cnv_scores.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/cnv_spatial_points.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/cnv_umap_points.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/numbat_calls.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/numbat_clone_post.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `tables/numbat_results.csv` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_bin_summary.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_group_sizes.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_groups_umap.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_heatmap.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_score_distribution.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_spatial.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_umap.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_uncertainty_distribution.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `figures/cnv_uncertainty_spatial.png` — written by `spatial_cnv.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_cnv.py`.
- `manifest.json` — written by `spatial_cnv.py`.
- `numbat_input.h5ad` — written by `spatial_cnv.py`.
- `processed.h5ad` — written by `spatial_cnv.py`.
- `r_visualization.sh` — written by `spatial_cnv.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_cnv.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
