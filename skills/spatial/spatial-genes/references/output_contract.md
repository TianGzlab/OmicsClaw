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
│   ├── coords.csv
│   ├── counts.csv
│   ├── significant_svgs.csv
│   ├── sparkx_results.csv
│   ├── svg_observation_metrics.csv
│   ├── svg_results.csv
│   ├── svg_run_summary.csv
│   ├── top_svg_scores.csv
│   ├── top_svg_spatial_points.csv
│   └── top_svg_umap_points.csv
└── figures/
    ├── moran_ranking.png
    ├── svg_score_vs_significance.png
    ├── svg_significance_distribution.png
    ├── top_svg_scores.png
    ├── top_svg_spatial.png
    └── top_svg_umap.png
```

## File contents

- `tables/coords.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/counts.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/significant_svgs.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/sparkx_results.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/svg_observation_metrics.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/svg_results.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/svg_run_summary.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/top_svg_scores.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/top_svg_spatial_points.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `tables/top_svg_umap_points.csv` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `figures/moran_ranking.png` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `figures/svg_score_vs_significance.png` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `figures/svg_significance_distribution.png` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `figures/top_svg_scores.png` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `figures/top_svg_spatial.png` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `figures/top_svg_umap.png` — written by `spatial_genes.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_genes.py`.
- `manifest.json` — written by `spatial_genes.py`.
- `processed.h5ad` — written by `spatial_genes.py`.
- `r_visualization.sh` — written by `spatial_genes.py`.
- `requirements.txt` — written by `spatial_genes.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_genes.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
