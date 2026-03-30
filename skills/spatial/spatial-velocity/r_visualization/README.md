# Spatial Velocity R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-velocity`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, layout, annotation, and publication-facing
  refinement rather than recomputing RNA velocity, pseudotime, or latent time.

## Input Contract

Run `oc run spatial-velocity ...` first. The resulting output directory should
contain:

- `figure_data/velocity_summary.csv`
- `figure_data/velocity_cell_metrics.csv`
- `figure_data/velocity_gene_summary.csv`
- `figure_data/velocity_gene_hits.csv`
- `figure_data/velocity_cluster_summary.csv`
- `figure_data/velocity_top_cells.csv`
- `figure_data/velocity_top_genes.csv`
- `figure_data/velocity_run_summary.csv`
- `figure_data/manifest.json`

When coordinates are available, the Python layer also exports:

- `figure_data/velocity_spatial_points.csv`
- `figure_data/velocity_umap_points.csv`

## Template

`velocity_publication_template.R` is a minimal `ggplot2` example. It always
reads `figure_data/velocity_top_genes.csv` to produce a publication-style top
gene bar plot. If `figure_data/velocity_spatial_points.csv` exists, it also
renders a spatial metric map under `figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-velocity/r_visualization/velocity_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or journal-specific styling code as
needed.
