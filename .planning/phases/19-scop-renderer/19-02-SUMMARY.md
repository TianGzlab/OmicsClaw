---
phase: 19-scop-renderer
plan: 02
subsystem: r-enhanced-viz
tags: [r-enhanced, ccc, correlation, cytotrace, ggplot2]
dependency_graph:
  requires: []
  provides: [plot_ccc_stat_bar, plot_ccc_stat_violin, plot_ccc_stat_scatter, plot_feature_cor, plot_cytotrace_boxplot]
  affects: [registry.R, sc-cell-communication, sc-cytotrace]
tech_stack:
  added: []
  patterns: [ccc-stat-bar, ccc-stat-violin, ccc-stat-scatter, feature-correlation, cytotrace-boxplot]
key_files:
  created:
    - skills/singlecell/_lib/viz/r/correlation.R
    - skills/singlecell/_lib/viz/r/cytotrace.R
  modified:
    - skills/singlecell/_lib/viz/r/communication.R
decisions:
  - "Used scop CytoTRACEPlot potency color scale (#D70440 Totipotent to #806D9E Differentiated) for consistency"
  - "plot_ccc_stat_scatter falls back to aggregating sender_receiver_summary.csv when group_role_summary.csv is absent"
  - "plot_feature_cor uses base reshape() for pivot to avoid extra dependency on tidyr"
metrics:
  duration: 275s
  completed: "2026-04-12T08:20:11Z"
  tasks: 2
  files: 3
---

# Phase 19 Plan 02: CCC Stat + Correlation + CytoTRACE Renderers Summary

5 new R Enhanced renderers: 3 CCC statistical plots in communication.R, feature correlation scatter in correlation.R, CytoTRACE boxplot in cytotrace.R

## Task Summary

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Add 3 CCC stat renderers | b283c5c | communication.R: +plot_ccc_stat_bar, +plot_ccc_stat_violin, +plot_ccc_stat_scatter |
| 2 | Create correlation.R and cytotrace.R | 2234e16 | New files: correlation.R (plot_feature_cor), cytotrace.R (plot_cytotrace_boxplot) |

## Renderer Details

### plot_ccc_stat_bar (communication.R)
- Horizontal bar chart of top interactions or pathways
- Auto-detects pathway vs pair grouping from CSV columns
- Falls back from pathway_summary.csv to top_interactions.csv
- Dynamic height based on bar count

### plot_ccc_stat_violin (communication.R)
- Violin + jitter of interaction score distributions
- Faceted by source or target cell type (configurable)
- Skips faceting when only 1 unique source/target

### plot_ccc_stat_scatter (communication.R)
- Outgoing vs incoming signaling strength per cell type
- Quadrant lines at median values
- Falls back to computing from sender_receiver_summary.csv if group_role_summary.csv missing

### plot_feature_cor (correlation.R)
- 2-gene scatter plot with linear regression line
- Pearson or Spearman correlation + p-value annotation
- Long-to-wide pivot via base reshape()
- Edge cases: <2 genes, >2 genes (uses first 2)

### plot_cytotrace_boxplot (cytotrace.R)
- Boxplot ordered by median CytoTRACE score (most stem-like first)
- Potency-aware coloring using scop's 6-level scale when cytotrace_potency column present
- Falls back to blue-red gradient on median score
- Jitter added only for <5000 cells
- Dynamic height: max(4, n_types * 0.5 + 1.5)

## Deviations from Plan

None - plan executed exactly as written.

## Self-Check: PASSED
