# Spatial Genes R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-genes`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing SVG statistics.

## Input Contract

Run `oc run spatial-genes ...` first. The resulting output directory should
contain:

- `figure_data/svg_results.csv`
- `figure_data/top_svg_scores.csv`
- `figure_data/significant_svgs.csv`
- `figure_data/svg_observation_metrics.csv`
- `figure_data/svg_run_summary.csv`
- `figure_data/top_svg_spatial_points.csv`
- `figure_data/top_svg_umap_points.csv` when UMAP is available
- `figure_data/manifest.json`

## Template

`svg_publication_template.R` is a minimal `ggplot2` example. It reads the
Python-exported `figure_data/top_svg_spatial_points.csv` file and creates a
publication-style faceted SVG panel under `figures/custom/`. It also creates a
companion top-score barplot from `figure_data/top_svg_scores.csv` when that
table is available.

Usage:

```bash
Rscript skills/spatial/spatial-genes/r_visualization/svg_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or journal-specific styling code as
needed.
