# Spatial Register R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-register`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python registration run.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than rerunning PASTE or STalign.

## Input Contract

Run `oc run spatial-register ...` or `oc run spatial-registration ...` first.
The resulting output directory should contain:

- `figure_data/registration_points.csv`
- `figure_data/registration_shift_by_slice.csv`
- `figure_data/registration_run_summary.csv`
- `figure_data/manifest.json`

`figure_data/registration_disparities.csv` is also available when the chosen
method exports per-slice disparity scores.

## Template

`register_publication_template.R` is a minimal `ggplot2` example. It reads the
Python-exported figure data and creates:

- a faceted before/after coordinate view from `registration_points.csv`
- a companion per-slice shift summary figure from
  `registration_shift_by_slice.csv`

Usage:

```bash
Rscript skills/spatial/spatial-register/r_visualization/register_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, or manuscript-specific styling code as needed.
