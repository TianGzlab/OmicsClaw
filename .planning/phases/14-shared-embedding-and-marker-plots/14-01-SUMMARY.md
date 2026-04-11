---
phase: 14-shared-embedding-and-marker-plots
plan: 01
subsystem: viz/r
tags: [r-enhanced, embedding, scatter, ggplot2]
dependency_graph:
  requires: [13-01 common.R, 13-01 registry.R]
  provides: [plot_embedding_discrete, plot_embedding_feature]
  affects: [sc-cell-annotation, any skill exporting annotation_embedding_points.csv]
tech_stack:
  added: []
  patterns: [CSV-driven R renderer, centroid label overlay, viridis continuous gradient]
key_files:
  created:
    - skills/singlecell/_lib/viz/r/embedding.R
  modified:
    - skills/singlecell/_lib/viz/r/registry.R
decisions:
  - "Used omics_palette() for discrete colors (Set2 for <= 8 groups, hue_pal for more)"
  - "Used viridis magma option for continuous feature overlay (high contrast on white background)"
  - "Centroid labels use geom_text with check_overlap=TRUE (simpler than geom_label_repel, no ggrepel dependency)"
metrics:
  duration: 354s
  completed: "2026-04-11T07:49:20Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 1
---

# Phase 14 Plan 01: Shared Embedding and Marker Plots Summary

CSV-driven CellDimPlot and FeatureDimPlot equivalents in embedding.R, reading annotation_embedding_points.csv and producing publication-quality scatter PNGs via ggplot2 with omics_palette discrete colors and viridis magma continuous gradient.

## Tasks Completed

### Task 1: Create embedding.R with discrete and continuous scatter renderers

Created `skills/singlecell/_lib/viz/r/embedding.R` (127 lines) with two functions:

- **plot_embedding_discrete**: Reads annotation_embedding_points.csv, determines color column (default `cell_type`), converts to factor, applies `omics_palette()`, computes per-group centroids for bold text labels, uses `geom_point(size=0.6, alpha=0.7)` for dense cell clouds, compact legend with `guide_legend(override.aes)`.

- **plot_embedding_feature**: Reads annotation_embedding_points.csv, determines feature column (default `annotation_score`), converts to numeric with NA warning, applies `scale_color_viridis_c(option="magma")` with grey NA value.

Both wrapped in `tryCatch` with `quit(status=1)` error handlers matching common.R pattern.

Verified with synthetic 200-cell CSV: discrete PNG 74,991 bytes, feature PNG 74,606 bytes.

**Commit:** `2e92a90`

### Task 2: Register embedding renderers in registry.R and run sc-cell-annotation round-trip

Registry.R already contained the embedding.R source line and both registry entries (committed as part of prior 14-02 work at `46bd031`). No additional registry.R edit was needed.

Ran sc-cell-annotation demo (`--demo --output /tmp/sc_annotation_r_test`), which produced `annotation_embedding_points.csv` with columns: `cell_id, dim1, dim2, cell_type, louvain, annotation_score`.

Round-trip via conda Rscript against real data:
- `r_embedding_discrete.png`: 268,966 bytes (6 cell types with colored scatter and centroid labels)
- `r_embedding_feature.png`: 273,678 bytes (annotation_score viridis magma overlay)

Bad renderer name test: `bad_name` returns exit code 1 with informative error listing available renderers.

**Commit:** No new commit needed (registry.R already up to date from 46bd031)

## Deviations from Plan

### Pre-existing Environment Issue (Not Fixed -- Out of Scope)

**Issue:** `call_r_plot()` Python wrapper uses system Rscript (`/usr/bin/Rscript`) instead of conda env Rscript because `CONDA_PREFIX` points to base conda, not the `omicsclaw` env. System R lacks `viridis` package.

**Impact:** R Enhanced plots fail when invoked via `call_r_plot()` without activating the omicsclaw conda env. This is a pre-existing issue affecting ALL R Enhanced renderers (including Phase 13's `plot_test_scatter`), not specific to this plan.

**Workaround:** Direct invocation with `/data/liying_environ/anaconda3_liying/envs/omicsclaw/bin/Rscript` works correctly. The `omicsclaw.py` launcher activates the conda env properly, so production use is unaffected.

**Disposition:** Logged as deferred item. The RScriptRunner's `_preferred_rscript_executable()` needs the omicsclaw env to be activated, which is the responsibility of the launcher (`omicsclaw.py`), not individual renderers.

## Verification Results

| Check | Result |
|-------|--------|
| embedding.R exists with both functions | PASS |
| registry.R sources embedding.R | PASS |
| registry.R lists both renderers in R_PLOT_REGISTRY | PASS |
| Synthetic CSV round-trip: discrete PNG > 5 KB | PASS (74,991 bytes) |
| Synthetic CSV round-trip: feature PNG > 5 KB | PASS (74,606 bytes) |
| Real data round-trip: discrete PNG > 5 KB | PASS (268,966 bytes) |
| Real data round-trip: feature PNG > 5 KB | PASS (273,678 bytes) |
| Bad renderer name returns exit code 1 | PASS |

## Known Stubs

None -- both renderers are fully functional with real data.

## Self-Check: PASSED
