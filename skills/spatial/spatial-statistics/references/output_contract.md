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
│   ├── analysis_results.csv
│   ├── analysis_summary.csv
│   ├── bivariate_moran_summary.csv
│   ├── centrality_scores.csv
│   ├── cluster_summary.csv
│   ├── cooccurrence_curves.csv
│   ├── cooccurrence_pairs.csv
│   ├── neighborhood_counts.csv
│   ├── neighborhood_pairs.csv
│   ├── neighborhood_zscore.csv
│   ├── network_per_cluster.csv
│   ├── network_summary.csv
│   ├── pair_summary.csv
│   ├── per_cluster_metrics.csv
│   ├── ripley_cluster_summary.csv
│   ├── ripley_curves.csv
│   ├── spot_statistics.csv
│   └── top_results.csv
└── figures/
    ├── bivariate_moran_scatter.png
    ├── bivariate_moran_spatial.png
    ├── centrality_scores.png
    ├── centrality_scores_barplot.png
    ├── co_occurrence_curves.png
    ├── co_occurrence_distribution.png
    ├── co_occurrence_top_pairs.png
    ├── geary_pvalue_distribution.png
    ├── geary_ranking.png
    ├── geary_score_vs_significance.png
    ├── moran_pvalue_distribution.png
    ├── moran_ranking.png
    ├── moran_score_vs_significance.png
    ├── neighborhood_enrichment_heatmap.png
    ├── neighborhood_top_pairs.png
    ├── neighborhood_zscore_distribution.png
    ├── network_degree_histogram.png
    ├── network_per_cluster_degree.png
    ├── ripley_cluster_max_stat.png
    ├── ripley_curves.png
    └── ripley_stat_distribution.png
```

## File contents

- `tables/analysis_results.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/analysis_summary.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/bivariate_moran_summary.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/centrality_scores.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/cluster_summary.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/cooccurrence_curves.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/cooccurrence_pairs.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/neighborhood_counts.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/neighborhood_pairs.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/neighborhood_zscore.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/network_per_cluster.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/network_summary.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/pair_summary.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/per_cluster_metrics.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/ripley_cluster_summary.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/ripley_curves.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/spot_statistics.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `tables/top_results.csv` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/bivariate_moran_scatter.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/bivariate_moran_spatial.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/centrality_scores.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/centrality_scores_barplot.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/co_occurrence_curves.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/co_occurrence_distribution.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/co_occurrence_top_pairs.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/geary_pvalue_distribution.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/geary_ranking.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/geary_score_vs_significance.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/moran_pvalue_distribution.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/moran_ranking.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/moran_score_vs_significance.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/neighborhood_enrichment_heatmap.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/neighborhood_top_pairs.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/neighborhood_zscore_distribution.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/network_degree_histogram.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/network_per_cluster_degree.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/ripley_cluster_max_stat.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/ripley_curves.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `figures/ripley_stat_distribution.png` — written by `spatial_statistics.py` (or its imported `_lib/` helpers).
- `commands.sh` — written by `spatial_statistics.py`.
- `manifest.json` — written by `spatial_statistics.py`.
- `processed.h5ad` — written by `spatial_statistics.py`.
- `r_visualization.sh` — written by `spatial_statistics.py`.
- `requirements.txt` — written by `spatial_statistics.py`.
- `report.md` — Markdown summary written by the common report helper.
- `result.json` — standardised result envelope (`summary` + `data` keys).

## Notes

Auto-generated from `spatial_statistics.py` (and the `_lib/` modules it imports) string literals; refine manually with method semantics if needed.
