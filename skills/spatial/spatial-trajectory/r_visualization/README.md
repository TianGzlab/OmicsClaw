# Spatial Trajectory R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-trajectory`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing DPT, CellRank, or Palantir.

## Input Contract

Run `oc run spatial-trajectory ...` first. The resulting output directory
should contain:

- `figure_data/trajectory_summary.csv`
- `figure_data/trajectory_cluster_summary.csv`
- `figure_data/trajectory_genes.csv`
- `figure_data/trajectory_run_summary.csv`
- `figure_data/manifest.json`

For standard plotting layers, the Python export also provides:

- `figure_data/trajectory_umap_points.csv`
- `figure_data/trajectory_spatial_points.csv`
- `figure_data/trajectory_diffmap_points.csv`

When fate probabilities are available, the Python layer also exports:

- `figure_data/trajectory_fate_probabilities.csv`

## Template

`trajectory_publication_template.R` is a minimal `ggplot2` example. It reads
the Python-exported `figure_data/trajectory_umap_points.csv` file when
available, falls back to `trajectory_spatial_points.csv` otherwise, and creates
a publication-style pseudotime map under `figures/custom/`. If the
`traj_fate_max_prob` column is present, it also renders a fate-confidence map.

Usage:

```bash
Rscript skills/spatial/spatial-trajectory/r_visualization/trajectory_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or manuscript-specific styling code
as needed.
