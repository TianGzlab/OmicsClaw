# Spatial Enrichment R Visualization Layer

This directory contains optional R-side visualization templates for
`spatial-enrichment`.

Design intent:

- Python standard gallery remains the canonical OmicsClaw output.
- R templates consume `figure_data/` exported by the Python analysis output.
- R scripts should focus on styling, panel composition, and publication-facing
  refinements rather than recomputing ORA, GSEA, or ssGSEA.

## Input Contract

Run `oc run spatial-enrichment ...` first. The resulting output directory
should contain:

- `figure_data/enrichment_results.csv`
- `figure_data/top_enriched_terms.csv`
- `figure_data/enrichment_group_metrics.csv`
- `figure_data/enrichment_term_group_scores.csv`
- `figure_data/enrichment_run_summary.csv`
- `figure_data/manifest.json`

When projected ssGSEA score columns exist, the Python layer also exports:

- `figure_data/enrichment_spatial_points.csv`
- `figure_data/enrichment_umap_points.csv`

## Template

`enrichment_publication_template.R` is a minimal `ggplot2` example. It always
reads `figure_data/top_enriched_terms.csv` to produce a publication-style top
term summary. If projected ssGSEA score columns are available in
`figure_data/enrichment_spatial_points.csv`, it also renders one spatial score
map under `figures/custom/`.

Usage:

```bash
Rscript skills/spatial/spatial-enrichment/r_visualization/enrichment_publication_template.R \
  <analysis_output_dir>
```

The standard OmicsClaw run also writes:

```bash
bash <analysis_output_dir>/reproducibility/r_visualization.sh
```

You are expected to fork or replace this template with more advanced
`ggplot2`, `patchwork`, `ComplexHeatmap`, or manuscript-specific styling code
as needed.
