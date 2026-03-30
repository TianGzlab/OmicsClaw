# Spatial DE R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-de`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing Scanpy ranking or PyDESeq2 inference.

## Input Contract

Run `oc run spatial-de ...` first. The resulting output directory should
contain:

- `figure_data/de_plot_points.csv`
- `figure_data/top_de_hits.csv`
- `figure_data/group_de_metrics.csv`
- `figure_data/de_run_summary.csv`
- `figure_data/manifest.json`

`figure_data/de_spatial_points.csv`, `figure_data/de_umap_points.csv`,
`figure_data/sample_counts_by_group.csv`, and
`figure_data/skipped_sample_groups.csv` are also available for more customized
downstream visualizations.

## Template

`de_publication_template.R` is a minimal `ggplot2` example. It reads the
Python-exported `figure_data/de_plot_points.csv` file and creates a
publication-style faceted volcano figure under `figures/custom/`. It also
creates a companion top-hit barplot from `figure_data/top_de_hits.csv`.

Usage:

```bash
Rscript skills/spatial/spatial-de/r_visualization/de_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or manuscript-specific styling code
as needed.
