# Spatial Communication R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-communication`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing communication analysis.

## Input Contract

Run `oc run spatial-communication ...` first. The resulting output directory
should contain:

- `figure_data/lr_interactions.csv`
- `figure_data/top_interactions.csv`
- `figure_data/communication_summary.csv`
- `figure_data/signaling_roles.csv`
- `figure_data/communication_spatial_points.csv`
- `figure_data/manifest.json`

`figure_data/communication_umap_points.csv` is also available when the Python
gallery produced a UMAP view.

## Template

`communication_publication_template.R` is a minimal `ggplot2` example. It reads
the Python-exported `figure_data/communication_spatial_points.csv` file and
creates a publication-style communication hub-score map under
`figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-communication/r_visualization/communication_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or manuscript-specific styling code
as needed.
