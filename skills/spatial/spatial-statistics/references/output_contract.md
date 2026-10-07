# Output contract

analyze returns the same AnnData. run_info restores diagnostic scalars and
method-specific DataFrames from a JSON record. results_table returns a copy
of one table. The CLI removes the record before writing processed.h5ad.

All successful CLI runs write report.md, result.json, commands.sh,
requirements.txt, r_visualization.sh and tables/analysis_summary.csv.
figure_data/manifest.json names available gallery data and successful plots.

## Analysis tables

- Neighborhood enrichment: tables/neighborhood_zscore.csv, tables/neighborhood_counts.csv and tables/neighborhood_pairs.csv.
- Ripley: tables/ripley_curves.csv and tables/ripley_cluster_summary.csv.
- Co-occurrence: tables/cooccurrence_curves.csv and tables/cooccurrence_pairs.csv.
- Moran/Geary: tables/moran_results.csv or tables/geary_results.csv.
- Local Moran/Getis-Ord: tables/local_moran_summary.csv and tables/local_moran_spots.csv, or tables/getis_ord_summary.csv and tables/getis_ord_spots.csv.
- Bivariate Moran: tables/bivariate_moran_summary.csv.
- Network topology: tables/network_summary.csv and, when labels exist, tables/network_per_cluster.csv.
- Spatial centrality: tables/centrality_scores.csv (cluster-level).

Empty method tables are omitted. Gallery exports are separate:
figure_data/analysis_summary.csv, and nonempty available tables named
analysis_results.csv, top_results.csv, pair_summary.csv, cluster_summary.csv,
per_cluster_metrics.csv and spot_statistics.csv under figure_data/.

## Figures

Only the selected method's plots are attempted. Each file also requires
its data to exist and rendering to succeed:

- Enrichment: figures/neighborhood_enrichment_heatmap.png, figures/neighborhood_top_pairs.png, figures/neighborhood_zscore_distribution.png.
- Ripley: figures/ripley_curves.png, figures/ripley_cluster_max_stat.png, figures/ripley_stat_distribution.png.
- Co-occurrence: figures/co_occurrence_curves.png, figures/co_occurrence_top_pairs.png, figures/co_occurrence_distribution.png.
- Moran: figures/moran_ranking.png, figures/moran_score_vs_significance.png, figures/moran_pvalue_distribution.png.
- Geary: figures/geary_ranking.png, figures/geary_score_vs_significance.png, figures/geary_pvalue_distribution.png.
- Local Moran: figures/local_moran_spatial.png, figures/local_moran_summary_barplot.png, figures/local_moran_pvalue_distribution.png.
- Getis-Ord: figures/getis_ord_spatial.png, figures/getis_ord_summary_barplot.png, figures/getis_ord_pvalue_distribution.png.
- Bivariate Moran: figures/bivariate_moran_scatter.png and figures/bivariate_moran_spatial.png.
- Network topology: figures/network_degree_histogram.png and figures/network_per_cluster_degree.png.
- Centrality: figures/centrality_scores.png and figures/centrality_scores_barplot.png.

Local analyses add per-gene spot statistic columns. Spatial graphs are retained
in obsp, and Squidpy method outputs remain in their native uns slots.
