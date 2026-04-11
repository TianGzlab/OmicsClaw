---
phase: 17-ccc-velocity-and-de-r-enhanced-plots
plan: 03
subsystem: viz/r
tags: [velocity, ggplot2, grid-overlay, r-enhanced]
dependency_graph:
  requires: [common.R, registry.R]
  provides: [plot_velocity]
  affects: [sc-velocity]
tech_stack:
  added: []
  patterns: [grid-binned magnitude overlay, percentile-clipping, viridis plasma]
key_files:
  created:
    - skills/singlecell/_lib/viz/r/velocity.R
  modified:
    - skills/singlecell/_lib/viz/r/registry.R
decisions:
  - Grid magnitude overlay instead of arrows (velocity_cells.csv lacks UMAP-space direction vectors)
  - Plasma colorscale for velocity magnitude, viridis for latent_time
  - Percentile-clip at 1st/99th to handle outlier bins
metrics:
  duration: 150s
  completed: "2026-04-11T09:46:03Z"
  tasks: 2
  files: 2
---

# Phase 17 Plan 03: VelocityPlot Grid R Enhanced Renderer Summary

Grid-binned velocity magnitude overlay on UMAP scatter using ggplot2 + viridis plasma, with latent_time color_by switching and scatter fallback.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | dd705cb | Create velocity.R with plot_velocity grid magnitude renderer |
| 2 | 0591c02 | Register in registry.R, fix n_bins NULL handling, integration test |

## What Was Built

**velocity.R** (`skills/singlecell/_lib/viz/r/velocity.R`):
- `plot_velocity(data_dir, out_path, params)` reads `velocity_cells.csv`
- **Grid mode** (default): bins cells into NxN grid, computes mean magnitude per bin, draws sized+colored dots over grey cell scatter
- **Scatter fallback**: when UMAP coordinates absent, shows magnitude distribution with loess trend
- `color_by` param switches between velocity_magnitude and latent_time
- `n_bins` param controls grid resolution (default 20)
- Percentile-clips magnitude at 1st/99th to prevent outlier dominance

**registry.R** updated:
- Sources velocity.R in the source block
- Adds `plot_velocity` to `R_PLOT_REGISTRY`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed n_bins NULL handling**
- **Found during:** Task 2 integration test
- **Issue:** `as.integer(params[["n_bins"]])` returns `integer(0)` when param is NULL, causing `is.na()` to fail with "missing value where TRUE/FALSE needed"
- **Fix:** Added NULL check before `as.integer()` conversion with explicit fallback to 20L
- **Files modified:** velocity.R
- **Commit:** 0591c02

## Verification Results

- `Rscript registry.R plot_velocity /tmp/vel_test_data /tmp/vel_grid.png plot_type=grid n_bins=15` -- exit 0, 117K PNG
- `Rscript registry.R plot_velocity /tmp/vel_test_data /tmp/vel_lt.png color_by=latent_time` -- exit 0, 124K PNG
- Grid PNG: grey cell scatter background + plasma-colored binned dots, UMAP axes labeled, "grid summary" subtitle
- Latent time PNG: same layout colored by latent_time with correct legend
