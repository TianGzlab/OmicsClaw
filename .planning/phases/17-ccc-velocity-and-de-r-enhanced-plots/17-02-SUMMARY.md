---
phase: 17-ccc-velocity-and-de-r-enhanced-plots
plan: 02
subsystem: viz/r
tags: [r-enhanced, ccc, heatmap, network, ggplot2]
dependency_graph:
  requires: [common.R, registry.R]
  provides: [communication.R, plot_ccc_heatmap, plot_ccc_network]
  affects: [sc-cell-communication]
tech_stack:
  added: [ggnewscale]
  patterns: [ggplot2 geom_curve arc network, geom_tile heatmap, dual-source CSV fallback]
key_files:
  created:
    - skills/singlecell/_lib/viz/r/communication.R
  modified:
    - skills/singlecell/_lib/viz/r/registry.R
decisions:
  - Used ggplot2 geom_curve for arc network instead of circlize (clean PNG export, no fragile dependency)
  - Used ggnewscale::new_scale_color() to allow separate color scales for edges (sender) and nodes (cell type)
  - .load_ccc_data() fallback pattern: sender_receiver_summary.csv primary, top_interactions.csv aggregation fallback
metrics:
  duration: 215s
  completed: "2026-04-11T09:47:13Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 1
---

# Phase 17 Plan 02: CCCHeatmap + CCCNetworkPlot R Enhanced Renderers Summary

ggplot2-native CCC visualization: sender-receiver heatmap/dot matrix + arc network diagram using geom_curve, reading figure_data CSV with dual-source fallback

## Task Results

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create communication.R with CCCHeatmap and CCCNetworkPlot renderers | bd16c02 | communication.R (created) |
| 2 | Register CCC renderers and integration test | 0591c02 (shared with 17-03) | registry.R (modified) |

## What Was Built

### communication.R

- **`.load_ccc_data(data_dir)`**: Internal helper that tries `sender_receiver_summary.csv` first, falls back to `top_interactions.csv` (aggregating by source+target with mean score and count). Coerces score to numeric, fills NA with 0.

- **`plot_ccc_heatmap(data_dir, out_path, params)`**: Builds a ggplot2 heatmap (geom_tile with score labels) or dot matrix (geom_point with size=n_interactions, color=score). Complete sender x receiver grid via expand.grid. Cell types ordered by total outgoing score. Dynamic sizing capped at 14x14 inches. Empty data produces blank plot with "No interactions detected" subtitle.

- **`plot_ccc_network(data_dir, out_path, params)`**: Builds a ggplot2 arc network using geom_curve with directed arrows. Nodes arranged in a circle. Edge width proportional to score, colored by sender cell type. Node size proportional to total (incoming + outgoing) score. Supports `min_score` and `top_n` (default 20) params to control edge count. Uses ggnewscale for dual color scales.

### registry.R Updates

- Added `source(file.path(script_dir, "communication.R"))` in source block
- Added `plot_ccc_heatmap` and `plot_ccc_network` to `R_PLOT_REGISTRY`

## Deviations from Plan

### Registry Commit Shared with 17-03

The registry.R changes for this plan were captured in commit `0591c02` (17-03's registry commit) because both plans ran in parallel Wave 1 and 17-03 committed registry.R after this plan's edits were already in the working tree. Both plans' entries are correctly present. No data loss or duplication.

## Verification Results

- `communication.R` sources without error
- `plot_ccc_heatmap` produces 50KB PNG with tile grid, score labels, gradient color scale
- `plot_ccc_network` produces 232KB PNG with circular node layout, directed curved arcs
- `plot_ccc_heatmap` dot variant also produces valid PNG
- Registry CLI dispatches both renderers correctly (exit 0)
- `grep` confirms both entries in registry.R (lines 69-70)

## Self-Check: PASSED
