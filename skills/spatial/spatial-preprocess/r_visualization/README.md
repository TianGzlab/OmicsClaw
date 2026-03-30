# Spatial Preprocess R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-preprocess`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python preprocessing run.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing QC, PCA, UMAP, or clustering.

## Input Contract

Run `oc run spatial-preprocess ...` or `oc run spatial-preprocessing ...`
first. The resulting output directory should contain:

- `figure_data/preprocess_spatial_points.csv` when spatial coordinates exist
- `figure_data/preprocess_umap_points.csv`
- `figure_data/cluster_summary.csv`
- `figure_data/qc_metric_distributions.csv`
- `figure_data/preprocess_run_summary.csv`
- `figure_data/manifest.json`

`figure_data/pca_variance_ratio.csv` and
`figure_data/multi_resolution_summary.csv` are also available for more
customized downstream visualizations.

## Template

`preprocess_publication_template.R` is a minimal `ggplot2` example. It reads
the Python-exported preprocessing figure data and creates:

- a publication-style spatial cluster map under `figures/custom/`
- a companion QC distribution figure from `qc_metric_distributions.csv`

Usage:

```bash
Rscript skills/spatial/spatial-preprocess/r_visualization/preprocess_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, or manuscript-specific styling code as needed.
