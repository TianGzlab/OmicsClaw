## Function outputs

`filter_cells` returns a new AnnData; the table functions return DataFrames,
and `filter_figure` returns a matplotlib Figure. Files are written by the step.

## CLI outputs

The CLI writes:

- `processed.h5ad`: retained cells and genes, counts layer and raw snapshot
  when counts are available, and input/matrix contracts.
- `report.md` and `result.json`: retention summary, effective thresholds and
  input preparation. `summary.filter_stats.outliers_flagged` counts existing
  outlier flags; those flags alone do not remove cells.
- `tables/filter_stats.csv`: metric/value rows for threshold failures and flags.
- `tables/filter_summary.csv`: metric/value rows for retention and effective thresholds.
- `tables/retention_summary.csv`: Cells/Genes rows with before/after counts.
- `figure_data/filter_summary.csv`, `filter_stats.csv`, `retention_summary.csv`,
  `filter_state.csv`, `filter_reasons.csv`, and `manifest.json`.
- `figure_data/gene_expression.csv` when numeric QC metrics are available;
  its columns are `cell_id`, `gene` (a QC metric name) and `expression`.
- `reproducibility/commands.sh` and `reproducibility/requirements.txt`.

The gallery renders `figures/filter_comparison.png`, `filter_summary.png`,
`filter_thresholds.png`, `filter_state_scatter.png`, and
`filter_reason_summary.png` when their required metrics and data are present.
The figure-data manifest records each plot's status.
With `--r-enhanced` and a working R plotting stack, the CLI can also write
`figures/r_enhanced/r_feature_violin.png`.
