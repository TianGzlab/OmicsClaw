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
│   ├── enrichment_group_metrics.csv
│   ├── enrichment_results.csv
│   ├── enrichment_run_summary.csv
│   ├── enrichment_significant.csv
│   ├── enrichment_spatial_points.csv
│   ├── enrichment_term_group_scores.csv
│   ├── enrichment_umap_points.csv
│   ├── ranked_markers.csv
│   └── top_enriched_terms.csv
└── figures/
    ├── enrichment_barplot.png
    ├── enrichment_dotplot.png
    ├── enrichment_group_metrics.png
    ├── enrichment_group_spatial_context.png
    ├── enrichment_group_top_stat_spatial.png
    ├── enrichment_group_top_stat_umap.png
    ├── enrichment_pvalue_distribution.png
    ├── enrichment_score_distribution.png
    ├── enrichment_score_violin.png
    ├── enrichment_spatial_scores.png
    └── top_enriched_terms.png
```

## File contents

- `tables/enrichment_group_metrics.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_results.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_run_summary.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_significant.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_spatial_points.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_term_group_scores.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `tables/enrichment_umap_points.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `tables/ranked_markers.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `tables/top_enriched_terms.csv` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_barplot.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_dotplot.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_group_metrics.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_group_spatial_context.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_group_top_stat_spatial.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_group_top_stat_umap.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_pvalue_distribution.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_score_distribution.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_score_violin.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/enrichment_spatial_scores.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `figures/top_enriched_terms.png` — written by `spatial_enrichment.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_enrichment.py`.
- `manifest.json` — written by `spatial_enrichment.py`.
- `processed.h5ad` — written by `spatial_enrichment.py`.
- `r_visualization.sh` — written by `spatial_enrichment.py`.
- `requirements.txt` — written by `spatial_enrichment.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_enrichment.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
