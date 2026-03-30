# Spatial CNV R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-cnv`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, layout, and publication-facing refinements
  rather than recomputing CNV inference.

## Input Contract

Run `oc run spatial-cnv ...` first. The resulting output directory should
contain:

- `figure_data/cnv_scores.csv`
- `figure_data/cnv_spatial_points.csv`
- `figure_data/cnv_umap_points.csv`
- `figure_data/cnv_run_summary.csv`
- `figure_data/manifest.json`

`figure_data/cnv_bin_summary.csv` is also available for heatmap-adjacent or
track-style custom plotting when inferCNVpy outputs `X_cnv`.

## Template

`cnv_publication_template.R` is a minimal `ggplot2` example. It reads
`figure_data/cnv_spatial_points.csv` and writes a polished CNV score map under
`figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-cnv/r_visualization/cnv_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or manuscript-specific styling code
as needed.
