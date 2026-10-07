## Function outputs

`find_markers` returns a DataFrame and leaves the input AnnData unchanged.
`run_info(table)` reads the record in its attrs, including any fallback to an
unfiltered ranking. Save that record separately before exporting CSV.

## CLI outputs

- `tables/markers_all.csv`: group, names, scores and method-dependent effect,
  p-value and expression-fraction columns. COSG includes `pvals` and `pvals_adj`
  with NaN values because it supplies no p-values.
- `tables/markers_top.csv`: up to `--n-top` rows per group, ordered by adjusted
  p-value then effect, or by score for COSG.
- `tables/cluster_summary.csv`: group, n_markers, top_gene, top_effect,
  median_effect and effect_metric.
- `figure_data/`: copies of those three tables and `manifest.json`.
- `processed.h5ad`: the input expression object with analysis and matrix
  contracts; `rank_genes_groups` and `rank_genes_groups_filtered` are removed.
- `report.md` and `result.json`; the latter includes `data.run_info`.
- `reproducibility/commands.sh` and `reproducibility/requirements.txt`.

The Python gallery can write `figures/markers_heatmap.png`,
`markers_dotplot.png`, `marker_effect_summary.png`, `marker_cluster_summary.png`
and `marker_fraction_scatter.png`. Each plot depends on its required genes,
groups or fraction columns being available.
With `--r-enhanced` and a working R plotting stack, the CLI can also write
`figures/r_enhanced/r_marker_heatmap.png` and `r_feature_violin.png`.
