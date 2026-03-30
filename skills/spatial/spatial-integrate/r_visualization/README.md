# Spatial Integrate R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-integrate`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing integration results.

## Input Contract

Run `oc run spatial-integrate ...` first. The resulting output directory should
contain:

- `figure_data/umap_before_points.csv`
- `figure_data/umap_after_points.csv`
- `figure_data/batch_sizes.csv`
- `figure_data/integration_metrics.csv`
- `figure_data/manifest.json`

## Template

`integration_publication_template.R` is a minimal `ggplot2` example. It reads
the Python-exported `figure_data/umap_after_points.csv` file and creates a
publication-style batch-colored UMAP under `figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-integrate/r_visualization/integration_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or publication-specific styling code
as needed.
