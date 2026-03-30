# Spatial Annotate R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-annotate`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on visual styling, panel composition, and
  publication-facing refinements rather than recomputing scientific results.

## Input Contract

Run `oc run spatial-annotate ...` first. The resulting output directory should
contain:

- `figure_data/annotation_spatial_points.csv`
- `figure_data/annotation_umap_points.csv` when UMAP is available
- `figure_data/annotation_cell_type_counts.csv`
- `figure_data/annotation_probabilities.csv` for probabilistic methods
- `figure_data/manifest.json`

## Template

`annotation_publication_template.R` is a minimal example using `ggplot2`. It
reads the Python-exported `figure_data/annotation_spatial_points.csv` and
creates a publication-style annotation map under `figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-annotate/r_visualization/annotation_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or domain-specific styling code as
needed.
