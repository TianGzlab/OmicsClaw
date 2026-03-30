# Spatial Statistics R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-statistics`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing Squidpy or PySAL statistics.

## Input Contract

Run `oc run spatial-statistics ...` first. The resulting output directory should
contain:

- `figure_data/analysis_summary.csv`
- `figure_data/top_results.csv` when a top-table view exists
- `figure_data/analysis_results.csv` when the analysis exports a main result table
- `figure_data/spot_statistics.csv` for local spot-level methods
- `figure_data/manifest.json`

## Template

`stats_publication_template.R` is a minimal `ggplot2` example. It reads the
Python-exported `figure_data/top_results.csv` file when available and creates a
publication-style barplot under `figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-statistics/r_visualization/stats_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, or journal-specific styling code as needed.
