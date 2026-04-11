---
phase: 16-trajectory-and-enrichment-r-enhanced-plots
plan: 02
subsystem: viz/r
tags: [enrichment, gsea, ggplot2, r-enhanced]
dependency_graph:
  requires: [common.R, registry.R]
  provides: [enrichment.R, plot_enrichment_bar, plot_gsea_mountain, plot_gsea_nes_heatmap]
  affects: [sc-enrichment]
tech_stack:
  added: [patchwork (optional)]
  patterns: [tryCatch error handling, %||% null coalescing, base R pivot for heatmap]
key_files:
  created:
    - skills/singlecell/_lib/viz/r/enrichment.R
  modified:
    - skills/singlecell/_lib/viz/r/registry.R
decisions:
  - "patchwork is optional for mountain plot -- falls back to single running-score panel"
  - "NES heatmap uses base R pivot (no tidyr/reshape2 dependency)"
  - "gsea_running_scores.csv absence is non-fatal (quit(0)) since ORA methods don't produce it"
metrics:
  duration: 219s
  completed: "2026-04-11T09:41:10Z"
  tasks: 2
  files: 2
---

# Phase 16 Plan 02: Enrichment R Enhanced Plots Summary

Three ggplot2 renderers for sc-enrichment figure_data: EnrichmentPlot bar (-log10 padj, NES-colored), GSEAPlot 3-panel mountain (patchwork with fallback), and NES comparison heatmap (diverging gradient2 tile).

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create enrichment.R with bar, mountain, NES heatmap renderers | 8abf667 | enrichment.R (new) |
| 2 | Register enrichment renderers in registry.R and smoke-test | 960f81b | registry.R (modified) |

## Key Implementation Details

### plot_enrichment_bar (SK-03)
- Reads `top_terms.csv`, filters by group, ranks by `-log10(pvalue_adj)`
- Bar fill: NES diverging gradient (blue-white-red) when available, viridis plasma otherwise
- Dashed significance line at p=0.05
- Term names truncated at 50 chars

### plot_gsea_mountain (SK-04)
- Reads `gsea_running_scores.csv` (non-fatal if absent -- ORA methods)
- 3-panel patchwork layout: running score + hit barcode + ranked metric
- Falls back to single running-score panel if patchwork not installed
- ES peak marked with red point

### plot_gsea_nes_heatmap (SK-05)
- Reads `enrichment_results.csv`, filters to significant terms (padj < 0.05)
- Top 25 terms by max(abs(NES)), base R pivot to term x group matrix
- ggplot2 geom_tile with gradient2 diverging scale, NES text overlay
- Mitigates T-16b-01 (DoS on large results) via top_n cap

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

- enrichment.R sources without error
- All three renderers produce PNGs from synthetic data
- Registry lists 9 renderers: plot_test_scatter, plot_embedding_discrete, plot_embedding_feature, plot_marker_heatmap, plot_pseudotime_lineage, plot_pseudotime_dynamic, plot_enrichment_bar, plot_gsea_mountain, plot_gsea_nes_heatmap
- Graceful failure: `plot_enrichment_bar /nonexistent/path` prints "ERROR: top_terms.csv not found" and exits 1

## Self-Check: PASSED

- [x] enrichment.R exists at skills/singlecell/_lib/viz/r/enrichment.R
- [x] Commit 8abf667 exists in git log
- [x] Commit 960f81b exists in git log
- [x] registry.R contains all 3 enrichment entries
- [x] No library(scop) in enrichment.R
- [x] No ggnewscale dependency
