# Output contract

Functions return the same AnnData, DataFrames and a Figure without writing
output files. AnnData stores `uns['enrichment_results']` and the executed
method's alias. ssGSEA additionally attaches group-mean score columns to obs.
The transient JSON diagnostic record is removed by the CLI before serialization.

The CLI writes `processed.h5ad`, `report.md`, `result.json`, `reproducibility/commands.sh`,
`reproducibility/requirements.txt` and `reproducibility/r_visualization.sh`.

## Tables

- `tables/enrichment_results.csv`: all tested terms.
- `tables/enrichment_significant.csv`: rows passing the adjusted-p-value threshold;
  empty for descriptive ssGSEA scores.
- `tables/ranked_markers.csv`: input ranks for ORA/GSEA; empty for ssGSEA.
- `tables/top_enriched_terms.csv` and `tables/enrichment_group_metrics.csv`:
  display selections and group summaries.
- `tables/enrichment_run_summary.csv` and `tables/enrichment_term_group_scores.csv`:
  run metadata and the term-by-group score table.
- `tables/enrichment_spatial_points.csv` and `tables/enrichment_umap_points.csv`:
  only when the corresponding coordinates exist.

## Conditional figures

- `figures/enrichment_group_spatial_context.png`: labels and spatial coordinates.
- `figures/enrichment_barplot.png` and `figures/enrichment_dotplot.png`: nonempty results.
- `figures/enrichment_group_top_stat_spatial.png` and
  `figures/enrichment_group_top_stat_umap.png`: group statistics and respective coordinates.
- `figures/enrichment_spatial_scores.png`: ssGSEA columns and spatial coordinates.
- `figures/enrichment_score_violin.png`: ssGSEA columns and labels.
- `figures/top_enriched_terms.png`: nonempty top-term table.
- `figures/enrichment_group_metrics.png`: group metrics.
- `figures/enrichment_pvalue_distribution.png`: at least one adjusted p value.
- `figures/enrichment_score_distribution.png`: nonempty score table.

The gallery writes `figure_data/manifest.json` and per-plot data. Failed plots
are logged. Missing p values stay missing; ssGSEA group scores do not supply
per-spot significance tests.
