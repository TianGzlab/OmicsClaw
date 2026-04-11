---
phase: 14-shared-embedding-and-marker-plots
plan: "02"
subsystem: singlecell/viz/r
tags: [r-enhanced, complexheatmap, markers, heatmap]
dependency_graph:
  requires: [13-01]
  provides: [plot_marker_heatmap]
  affects: [sc-markers]
tech_stack:
  added: [ComplexHeatmap, circlize, tidyr]
  patterns: [grouped-heatmap, pivot-wider, base-graphics-png]
key_files:
  created:
    - skills/singlecell/_lib/viz/r/markers.R
  modified:
    - skills/singlecell/_lib/viz/r/registry.R
decisions:
  - "ComplexHeatmap uses base R graphics (png/dev.off), not ggplot2 ggsave_standard"
  - "Value column auto-detection: logfoldchanges preferred, scores as fallback"
  - "Blue-white-red diverging color scale matches scop GroupHeatmap convention"
metrics:
  duration: 295s
  completed: "2026-04-11T07:48:17Z"
  tasks: 2
  files: 2
---

# Phase 14 Plan 02: Marker Heatmap R Renderer Summary

ComplexHeatmap grouped marker heatmap renderer reading markers_top.csv with per-cluster column slicing and blue-white-red diverging scale.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create markers.R with ComplexHeatmap grouped marker renderer | 28db8a2 | markers.R |
| 2 | Register plot_marker_heatmap in registry.R and run round-trip | 46bd031 | registry.R |

## What Was Built

**markers.R** (~151 lines) provides `plot_marker_heatmap()`:
- Reads `markers_top.csv` from figure_data directory
- Auto-detects value column (logfoldchanges > scores)
- Validates column presence (T-14-05 mitigation)
- Pivots to gene x cluster matrix via tidyr::pivot_wider
- Limits to top N genes per cluster (n_top param, default 10)
- Renders ComplexHeatmap with:
  - Per-cluster column splitting
  - Gene name row labels (fontsize 8)
  - Blue-white-red diverging color scale (circlize::colorRamp2)
  - Horizontal legend at bottom
- Graceful error handling: tryCatch wrapper exits status 1 on failure

**registry.R** updated:
- Sources markers.R after embedding.R
- Adds `plot_marker_heatmap` to R_PLOT_REGISTRY (4th entry)

## Verification Results

1. Synthetic test (4 clusters x 8 genes): 83,993 bytes PNG -- PASS
2. Missing CSV graceful failure: exit code 1, no PNG -- PASS
3. Registry round-trip via Rscript CLI: 83,993 bytes -- PASS
4. sc-markers demo + call_r_plot Python round-trip: 44,993 bytes PNG in figures/r_enhanced/ -- PASS

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None.
