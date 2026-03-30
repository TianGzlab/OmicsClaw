# Spatial Condition R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-condition`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing pseudobulk differential expression.

## Input Contract

Run `oc run spatial-condition ...` first. The resulting output directory should
contain:

- `figure_data/pseudobulk_volcano_points.csv`
- `figure_data/cluster_de_metrics.csv`
- `figure_data/condition_run_summary.csv`
- `figure_data/manifest.json`

`figure_data/condition_spatial_points.csv` and
`figure_data/condition_umap_points.csv` are also available when the Python
gallery exported those views.

## Template

`condition_publication_template.R` is a minimal `ggplot2` example. It reads the
Python-exported `figure_data/pseudobulk_volcano_points.csv` file and creates a
publication-style faceted volcano figure under `figures/custom/`. When
`figure_data/cluster_de_metrics.csv` is present, it also writes a companion
cluster-burden barplot.

Usage:

```bash
Rscript skills/spatial/spatial-condition/r_visualization/condition_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or manuscript-specific styling code
as needed.
