# Spatial Raw Processing R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-raw-processing`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the raw-processing run.
- R scripts should focus on styling and panel composition rather than rerunning
  `st_pipeline` or recomputing the raw AnnData conversion.

## Input Contract

Run `oc run spatial-raw-processing ...` first. The output directory should
contain at least:

- `figure_data/raw_processing_run_summary.csv`
- `figure_data/stage_summary.csv`
- `figure_data/raw_spot_qc.csv`
- `figure_data/raw_top_genes.csv`
- `figure_data/manifest.json`

Optional files include:

- `figure_data/raw_processing_spatial_points.csv`
- `figure_data/saturation_curve.csv`

## Template

`raw_processing_publication_template.R` is a minimal `ggplot2` example. It
creates publication-style derivatives from the exported figure data and writes
those figures under `figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-raw-processing/r_visualization/raw_processing_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with manuscript-specific
styling as needed.
