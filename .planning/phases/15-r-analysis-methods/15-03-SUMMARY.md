---
phase: 15-r-analysis-methods
plan: 03
subsystem: singlecell-enrichment
tags: [GSVA, R-bridge, sc-enrichment, pathway-scoring, BiocParallel]

requires:
  - phase: 14-shared-embedding-marker-plots
    provides: R bridge infrastructure (RScriptRunner, r_scripts pattern)
provides:
  - gsva_r method in sc-enrichment via GSVA R bridge (group-level pathway scores)
  - sc_gsva_r.R CLI script for standalone GSVA execution
  - Heatmap visualization of pathway activity scores across cell groups
affects: [sc-enrichment, 15-04]

tech-stack:
  added: [GSVA 2.0.7, magick 2.9.1 (GSVA dependency)]
  patterns: [gsvaParam/ssgseaParam/zscoreParam API (GSVA 2.0), SerialParam OOM prevention, dedicated early-exit dispatch path]

key-files:
  created:
    - omicsclaw/r_scripts/sc_gsva_r.R
  modified:
    - skills/singlecell/scrna/sc-enrichment/sc_enrichment.py
    - skills/singlecell/scrna/sc-enrichment/SKILL.md

key-decisions:
  - "GSVA 2.0.7 uses gsvaParam() (lowercase) not GSVAParam(); BPPARAM on gsva() call not constructor"
  - "gsva_r gets dedicated early-exit path in main() — bypasses gene set resolution entirely (R handles gene sets)"
  - "magick R package required LIBRARY_PATH=/usr/lib/x86_64-linux-gnu for conda linker to find system ImageMagick"
  - "SerialParam() passed to gsva() call to prevent OOM from parallel BiocParallel workers"

metrics:
  duration: 1593s
  completed: 2026-04-11
  tasks: 2
  files: 3
---

# Phase 15 Plan 03: gsva_r Method for sc-enrichment Summary

GSVA group-level pathway activity scoring via R bridge with SerialParam OOM prevention and seaborn heatmap visualization

## What Was Done

### Task 1: Install GSVA and write sc_gsva_r.R
- Installed GSVA 2.0.7 via BiocManager (also resolved magick 2.9.1 dependency requiring LIBRARY_PATH for conda linker)
- Discovered GSVA 2.0.7 API change: `gsvaParam()` (lowercase), `BPPARAM` goes on `gsva()` call not constructor
- Created `omicsclaw/r_scripts/sc_gsva_r.R` (229 lines):
  - CLI: `Rscript sc_gsva_r.R <group_expr_csv> <output_dir> [species] [db] [gsva_method] [group_by]`
  - Supports gsva, ssgsea, zscore methods via `gsvaParam/ssgseaParam/zscoreParam`
  - Builds GO_BP/KEGG gene sets from org.Hs.eg.db/org.Mm.eg.db
  - Demo fallback with synthetic gene sets when annotation DB unavailable
  - Long-format CSV output: pathway, group, gsva_score
  - Always uses `SerialParam()` to prevent OOM

### Task 2: Add gsva_r dispatch to sc_enrichment.py and test demo
- Added `gsva_r` to METHOD_REGISTRY
- Added `_export_group_expr_for_gsva()`: averages expression per group, exports CSV
- Added `_run_gsva_r()`: R bridge dispatch via RScriptRunner with 1800s timeout
- Added `_plot_gsva_heatmap()`: seaborn heatmap of top 30 pathways (variance-sorted), diverging RdBu_r colormap, placeholder on empty
- Added gsva_r dedicated early-exit path in `main()` (bypasses gene set resolution)
- Fixed `_write_report()` and `_write_reproducibility()` to handle gsva_r params (no gsea keys)
- Updated SKILL.md: added gsva_r to Methods table, CLI examples, and method choices

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] GSVA API changed in 2.0.7**
- **Found during:** Task 1 Step A
- **Issue:** Plan referenced `GSVAParam()` (uppercase G, S, V, A) from GSVA >= 1.50. GSVA 2.0.7 exports `gsvaParam()` (lowercase g). Also, `BPPARAM` is not a constructor param — it goes on the `gsva()` call.
- **Fix:** Updated R script to use `gsvaParam(exprData, geneSets)` and `gsva(param, BPPARAM=SerialParam())`
- **Files modified:** omicsclaw/r_scripts/sc_gsva_r.R
- **Commit:** 7b08711

**2. [Rule 3 - Blocking] magick R package linker failure**
- **Found during:** Task 1 Step A
- **Issue:** magick R package (GSVA dependency via SpatialExperiment) failed to compile — conda linker couldn't find system ImageMagick libs
- **Fix:** Set `LIBRARY_PATH=/usr/lib/x86_64-linux-gnu` to let conda linker find system libMagickWand/libMagickCore
- **Files modified:** None (environment fix)
- **Commit:** 7b08711

**3. [Rule 1 - Bug] _write_report and _write_reproducibility crash on gsva_r**
- **Found during:** Task 2 demo test
- **Issue:** Both functions had if/else on method==ora vs everything else, and the else branch hardcoded gsea param keys
- **Fix:** Added `elif params["method"] == "gsva_r"` branch to both functions
- **Files modified:** skills/singlecell/scrna/sc-enrichment/sc_enrichment.py
- **Commit:** 9159f7e

## Verification Results

| Check | Result |
|-------|--------|
| GSVA version >= 1.50 | PASS (2.0.7) |
| `--demo --method gsva_r` exits 0 | PASS |
| result.json has method=gsva_r, r_success=true | PASS |
| figures/gsva_r_heatmap.png non-empty | PASS (79KB) |
| adata.uns['gsva_r_scores'] populated | PASS (80 entries) |
| ORA regression test | PASS |

## Self-Check: PASSED

- All 3 files exist (sc_gsva_r.R 229 lines, sc_enrichment.py, SKILL.md)
- Both commits found: 7b08711, 9159f7e
- Demo output verified: result.json, heatmap PNG, adata.uns populated
