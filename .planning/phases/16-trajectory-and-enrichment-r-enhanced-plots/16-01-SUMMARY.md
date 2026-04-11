---
phase: 16-trajectory-and-enrichment-r-enhanced-plots
plan: 01
subsystem: viz/r pseudotime renderers
tags: [r-enhanced, pseudotime, lineage-plot, dynamic-plot, ggplot2]
dependency_graph:
  requires: [common.R, registry.R]
  provides: [pseudotime.R, plot_pseudotime_lineage, plot_pseudotime_dynamic, gene_expression.csv]
  affects: [sc-pseudotime, registry.R]
tech_stack:
  added: []
  patterns: [loess-smoothed-trajectory, stat_smooth-CI-ribbon, facet_wrap-per-gene]
key_files:
  created:
    - skills/singlecell/_lib/viz/r/pseudotime.R
  modified:
    - skills/singlecell/_lib/viz/r/registry.R
    - skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py
decisions:
  - Loess fallback used when no slingshot_curves.csv present (vs requiring explicit curves)
  - Synthetic expression fallback in DynamicPlot when gene_expression.csv absent (demo/testing)
  - gene_expression.csv written as long-format (cell_id, gene, expression) for R merge simplicity
metrics:
  duration: 223s
  completed: "2026-04-11T09:41:00Z"
  tasks_completed: 3
  tasks_total: 3
  files_created: 1
  files_modified: 2
requirements_completed: [SK-06, SK-07]
---

# Phase 16 Plan 01: pseudotime.R LineagePlot + DynamicPlot R Enhanced Renderers Summary

**One-liner:** Two R ggplot2 renderers for pseudotime visualization -- loess-smoothed trajectory scatter (LineagePlot) and gene expression trend ribbons with CI (DynamicPlot, no Python equivalent) -- plus gene_expression.csv export hook in sc_pseudotime.py.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create pseudotime.R with LineagePlot and DynamicPlot renderers | 4d1af1b | skills/singlecell/_lib/viz/r/pseudotime.R |
| 2 | Register pseudotime renderers in registry.R and smoke-test | 960f81b | skills/singlecell/_lib/viz/r/registry.R |
| 3 | Add gene_expression.csv hook in sc_pseudotime.py | ba84d5c | skills/singlecell/scrna/sc-pseudotime/sc_pseudotime.py |

## What Was Built

### plot_pseudotime_lineage (SK-06)
- Reads `pseudotime_points.csv` from figure_data/
- Scatter plot colored by pseudotime using viridis plasma palette
- Trajectory overlay: explicit slingshot curves if `slingshot_curves.csv` exists, otherwise loess-smoothed fallback
- Loess capped at 5000 cells for performance (T-16a-02 mitigation)
- Output via `ggsave_standard()` with `theme_omics()`

### plot_pseudotime_dynamic (SK-07)
- No Python equivalent -- key differentiator for R Enhanced gallery
- Reads `pseudotime_points.csv` + `trajectory_genes.csv`, selects top N genes by absolute correlation
- Merges with per-cell expression from `gene_expression.csv` (or synthetic fallback)
- stat_smooth loess with CI ribbons, faceted per gene
- Loess capped at 5000 cells per gene for performance

### gene_expression.csv export
- Added to `sc_pseudotime.py` main execution block (after `_write_figure_data()`)
- Schema: cell_id (string), gene (string), expression (float)
- Top 10 trajectory genes from `working.X` (normalized expression matrix)
- Wrapped in try/except -- never crashes the skill on failure

## Deviations from Plan

None -- plan executed exactly as written.

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|------------|
| T-16a-02 | Loess capped at 5000 cells in both renderers via `sample()` before fitting |

## Known Stubs

None.

## Self-Check: PASSED
