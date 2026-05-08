---
name: sc-filter
description: >-
  Filter cells and genes from single-cell RNA-seq AnnData objects using
  QC-derived thresholds or tissue presets. This wrapper removes low-quality
  cells/genes but does not normalize, cluster, or annotate the dataset.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, filter, qc, preprocessing]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
    - "--max-counts"
    - "--max-genes"
    - "--max-mt-percent"
    - "--min-cells"
    - "--min-counts"
    - "--min-genes"
    - "--tissue"
    - "--r-enhanced"
    param_hints:
      threshold_filtering:
        priority: "tissue -> min_genes/max_mt_percent -> min_cells -> count caps"
        params: ["tissue", "min_genes", "max_genes", "min_counts", "max_counts", "max_mt_percent",
          "min_cells"]
        defaults: {min_genes: 200, max_mt_percent: 20.0, min_cells: 3}
        requires: ["qc_metrics_in_obs_or_count_like_matrix_in_X", "scanpy"]
        tips:
        - "--tissue: Wrapper-level preset that overrides the default QC thresholds
          with OmicsClaw tissue heuristics."
        - "--min-genes / --max-mt-percent: Main cell-retention controls."
        - "--min-cells: Gene-level retention threshold applied after cell filtering."
    saves_h5ad: true
    requires_preprocessed: false
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install: []
    trigger_keywords:
    - filter cells
    - cell filtering
    - gene filtering
    - remove low quality
    - qc filtering
    - tissue-specific thresholds
    script: sc_filter.py
---

# Single-Cell Filter

## Why This Exists

- Without it: downstream clustering and DE are distorted by low-quality droplets and low-information genes.
- With it: one run applies explicit QC cutoffs and records how many cells/genes were removed.
- Why OmicsClaw: tissue presets and a stable output contract make filtering easier to reproduce.

## Core Capabilities

1. **Threshold-based filtering**: gene-count, count-depth, and mitochondrial cutoffs in one wrapper.
2. **Tissue-aware presets**: wrapper-level heuristics for common tissues.
3. **QC-aware operation**: reuses existing QC metrics or computes the minimum needed metrics first.
4. **Standard gallery contract**: before/after QC comparison and retention summary under `figures/`.
5. **Downstream-ready export**: `processed.h5ad`, filter-stat tables, result JSON, README, and notebook artifacts.

## Scope Boundary

This skill currently exposes one public workflow: `threshold_filtering`.

This skill does:

1. use existing QC metrics or compute the ones needed for thresholding
2. filter cells by genes, counts, and mitochondrial percentage
3. filter genes by minimum detected-cell count
4. export filtered AnnData, figures, tables, and a report

This skill does not:

1. normalize counts
2. run HVG, PCA, UMAP, or clustering
3. remove doublets or ambient RNA

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | preferred input path |
| Demo | `--demo` | yes | bundled fallback |

### Input Expectations

- Accepted input: `.h5ad`
- Expected data state: either count-oriented AnnData or QC-annotated AnnData
- Important columns when present: `n_genes_by_counts`, `total_counts`, `pct_counts_mt`
- If QC metrics are missing but raw counts are still recoverable, the wrapper canonicalizes the object and computes the minimum needed QC metrics automatically
- If the object already has QC metrics, the wrapper reuses them instead of forcing the user back through `sc-qc`

## Workflow

1. Load AnnData and inspect available QC columns plus matrix state.
2. Reuse existing QC metrics when present; otherwise canonicalize count-like input and compute the minimum needed QC metrics.
3. Apply optional tissue preset and resolve effective thresholds.
4. Filter cells by configured thresholds.
5. Filter genes by `min_cells`.
6. Write `processed.h5ad`, figures, figure-data CSVs, summary tables, `report.md`, and `result.json`.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-filter/sc_filter.py \
  --input <data.h5ad> --output <dir>

python skills/singlecell/scrna/sc-filter/sc_filter.py \
  --input <data.h5ad> --tissue pbmc --output <dir>

python skills/singlecell/scrna/sc-filter/sc_filter.py \
  --input <data.h5ad> --min-genes 200 --max-genes 6000 \
  --max-mt-percent 15 --min-cells 3 --output <dir>
```

## Public Parameters

| Flag | Default | Meaning |
|------|---------|---------|
| `--min-genes` | `200` | Minimum detected genes per retained cell |
| `--max-genes` | none | Optional upper gene-count cap |
| `--min-counts` | none | Optional lower UMI-count cap |
| `--max-counts` | none | Optional upper UMI-count cap |
| `--max-mt-percent` | `20.0` | Maximum mitochondrial percentage |
| `--min-cells` | `3` | Minimum number of cells expressing a retained gene |
| `--tissue` | none | OmicsClaw preset thresholds such as `pbmc`, `brain`, or `tumor` |

## Algorithm / Methodology

Current OmicsClaw `threshold_filtering` always:

1. loads the AnnData object
2. checks whether QC metrics already exist
3. resolves optional tissue presets into effective thresholds
4. filters cells by genes, counts, and mitochondrial percentage
5. filters genes by `min_cells`
6. exports filtered data plus summary artifacts

Important implementation note:

- `tissue` is an OmicsClaw wrapper preset, not an upstream Scanpy parameter.

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/`
- `tables/filter_stats.csv`
- `tables/filter_summary.csv`
- `tables/retention_summary.csv`
- `figure_data/`
- `reproducibility/commands.sh`

### Visualization Contract

The current wrapper writes a standard recipe-driven gallery:

- `figures/filter_comparison.png`
- `figures/filter_summary.png`

### What Users Should Inspect First

1. `report.md`
2. `figures/filter_comparison.png`
3. `tables/filter_stats.csv`
4. `figures/filter_summary.png`
5. `processed.h5ad`

## Current Limitations

- The shared runner adds top-level README and notebook-style reproducibility artifacts when notebook export dependencies are available.
- Threshold presets are OmicsClaw wrapper defaults, not upstream standard recommendations for every tissue.

## Safety And Guardrails

- Explain the effective thresholds before running, especially when `--tissue` presets are used.
- Treat tissue presets as wrapper heuristics rather than universal biology rules.
- **Doublet removal is automatic** when `predicted_doublet` or `doublet_score` columns (written by `sc-doublet-detection`) are present in `adata.obs`. Pass `--no-remove-doublets` to disable. Use `--doublet-score-threshold` (default 0.25) to tune the score cutoff when only `doublet_score` is available.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-filter-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-filter.md`.

## Workflow Position

- **Upstream step**: `sc-qc` for QC visualization (recommended), or directly from `sc-count` / `sc-multi-count`
- **Usual next step**: `sc-preprocessing` for normalization, HVG selection, and PCA
- **Optional before preprocessing**: `sc-doublet-detection` or `sc-ambient-removal`

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | path | — | Input AnnData file (`.h5ad`); required unless `--demo` | — |
| `--output` | path | — | Output directory (required) | — |
| `--demo` | flag | `false` | Run with built-in demo data | — |
| `--min-genes` | int | `200` | Minimum detected genes per retained cell | Must be >= 0; must be <= `--max-genes` when both set |
| `--max-genes` | int | none | Maximum detected genes per cell (optional upper cap) | Must be >= 0 |
| `--min-counts` | int | none | Minimum UMI counts per cell (optional lower cap) | Must be >= 0; must be <= `--max-counts` when both set |
| `--max-counts` | int | none | Maximum UMI counts per cell (optional upper cap) | Must be >= 0 |
| `--max-mt-percent` | float | `20.0` | Maximum mitochondrial percentage per cell | Must be in [0, 100] |
| `--min-cells` | int | `3` | Minimum cells expressing a retained gene | Must be >= 0 |
| `--tissue` | enum | none | OmicsClaw tissue preset: `pbmc`, `brain`, `tumor`, `heart`, `kidney`, `liver`, `lung` | — |
| `--no-remove-doublets` | flag | off | Disable automatic doublet removal (doublets are removed by default when `predicted_doublet` / `doublet_score` columns are present) | — |
| `--doublet-score-threshold` | float | `0.25` | Score cutoff when only `doublet_score` is available (requires upstream `sc-doublet-detection`) | Must be in [0, 1] |
| `--r-enhanced` | flag | `false` | Generate R Enhanced figures via ggplot2 renderers | — |

## R Enhanced Plots

| Renderer | Output file | What it shows | R packages |
|----------|-------------|---------------|------------|
| `plot_feature_violin` | `r_feature_violin.png` | Violin plots of QC metrics (genes, counts, MT%) before/after filtering | ggplot2, ggridges, cowplot |
| `plot_cell_barplot` | `r_cell_barplot.png` | Cell count bar chart showing retained vs removed cells | ggplot2, cowplot |
