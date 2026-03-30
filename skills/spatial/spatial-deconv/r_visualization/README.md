# Spatial Deconvolution R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-deconv`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing cell type deconvolution.

## Input Contract

Run `oc run spatial-deconv ...` first. The resulting output directory should
contain:

- `figure_data/proportions.csv`
- `figure_data/deconv_spot_metrics.csv`
- `figure_data/mean_proportions.csv`
- `figure_data/dominant_celltype_counts.csv`
- `figure_data/deconv_run_summary.csv`
- `figure_data/manifest.json`

`figure_data/deconv_spatial_points.csv` and `figure_data/deconv_umap_points.csv`
are also exported when the corresponding coordinates are available.

## Template

`deconv_publication_template.R` is a minimal `ggplot2` example. It reads the
Python-exported `figure_data/` tables and creates publication-style figures
under `figures/custom/`:

- dominant cell-type tissue map
- assignment-margin uncertainty histogram
- mean cell-type proportion summary

Usage:

```bash
Rscript skills/spatial/spatial-deconv/r_visualization/deconv_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or manuscript-specific styling code
as needed.
