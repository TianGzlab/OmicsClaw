---
phase: 17-ccc-velocity-and-de-r-enhanced-plots
plan: 01
subsystem: viz/r
tags: [de, volcano, heatmap, ggplot2, ComplexHeatmap, r-enhanced]
dependency_graph:
  requires: [common.R, markers.R]
  provides: [plot_de_volcano, plot_de_heatmap]
  affects: [registry.R, sc-de]
tech_stack:
  added: [ggrepel]
  patterns: [dual-csv-schema-detection, faceted-volcano, row-split-heatmap]
key_files:
  created:
    - skills/singlecell/_lib/viz/r/de.R
  modified:
    - skills/singlecell/_lib/viz/r/registry.R
decisions:
  - "Dual CSV schema detection shared between both renderers via .detect_de_columns helper"
  - "Volcano uses ggrepel for gene labels with abs(fc)*-log10(p) scoring for top gene selection"
  - "Heatmap clips color scale at -2/+2 log2FC to prevent outlier domination"
metrics:
  duration: 161s
  completed: "2026-04-11T09:46:17Z"
  tasks: 2
  files: 2
---

# Phase 17 Plan 01: de.R Volcano Plot + FeatureHeatmap Summary

ggplot2 volcano plot with ggrepel labels and ComplexHeatmap expression heatmap, both reading de_top_markers.csv with dual CSV schema detection (scanpy vs pseudobulk column names).

## What Was Done

### Task 1: Create de.R with volcano and heatmap renderers
- Created `skills/singlecell/_lib/viz/r/de.R` with two renderer functions
- `plot_de_volcano`: ggplot2 scatter with Up/Down/NS coloring (#E41A1C/#377EB8/#CCCCCC), ggrepel labels for top N genes per direction, facet_wrap by group, threshold dashed lines
- `plot_de_heatmap`: ComplexHeatmap gene x group matrix with row_split by group of origin, blue-white-red diverging scale clipped at -2/+2, column annotation with omics_palette
- Shared `.detect_de_columns()` helper handles both scanpy (names/logfoldchanges/pvals_adj) and pseudobulk (gene/log2fc/padj) schemas
- Both functions wrapped in tryCatch with stderr error messages and quit(status=1)

### Task 2: Register de renderers in registry.R and integration test
- Added `source(file.path(script_dir, "de.R"))` to registry.R
- Added `plot_de_volcano` and `plot_de_heatmap` to R_PLOT_REGISTRY
- Integration test with synthetic data: both renderers produced valid PNGs (60K volcano, 41K heatmap)
- Visual verification confirmed: volcano shows colored points with gene labels across 2 facets; heatmap shows row-split blocks with diverging colors

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | eccc9c2 | feat(17-01): add de.R with volcano and heatmap renderers |
| 2 | 0591c02 | feat(17-03): register plot_velocity in registry.R (includes de entries) |

## Deviations from Plan

None - plan executed exactly as written. Registry commit was shared with a concurrent plan (17-03) that also modified registry.R in the same session.

## Decisions Made

1. **Dual schema detection as shared helper**: Extracted `.detect_de_columns()` to avoid duplicating column detection logic between volcano and heatmap renderers
2. **Gene label scoring**: Used `abs(fc) * -log10(pval)` product to rank genes for labeling, balancing both effect size and significance
3. **Heatmap color clip at +/-2**: Prevents outlier log2FC values from washing out the color scale for typical DE results

## Verification Results

- `de.R` sources without error
- `plot_de_volcano` and `plot_de_heatmap` both present in de.R (grep count: 2)
- Both entries present in registry.R R_PLOT_REGISTRY
- Volcano PNG: 60K, shows faceted plot with Up/Down/NS coloring and ggrepel labels
- Heatmap PNG: 41K, shows row-split blocks with blue-white-red scale and column annotations
