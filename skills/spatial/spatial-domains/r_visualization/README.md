# Spatial Domains R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-domains`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing domain labels.

## Input Contract

Run `oc run spatial-domains ...` first. The resulting output directory should
contain:

- `figure_data/domain_spatial_points.csv`
- `figure_data/domain_umap_points.csv` when UMAP is available
- `figure_data/domain_counts.csv`
- `figure_data/domain_neighbor_mixing.csv`
- `figure_data/manifest.json`

## Template

`domains_publication_template.R` is a minimal `ggplot2` example. It reads the
Python-exported `figure_data/domain_spatial_points.csv` file and creates a
publication-style spatial domain panel under `figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-domains/r_visualization/domains_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or domain-specific styling code as
needed.
