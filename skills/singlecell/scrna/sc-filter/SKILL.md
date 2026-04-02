---
name: sc-filter
description: >-
  Filter cells and genes from single-cell RNA-seq AnnData objects using
  QC-derived thresholds or tissue presets. This wrapper removes low-quality
  cells/genes but does not normalize, cluster, or annotate the dataset.
version: 0.3.0
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
    param_hints:
      threshold_filtering:
        priority: "tissue -> min_genes/max_mt_percent -> min_cells -> count caps"
        params: ["tissue", "min_genes", "max_genes", "min_counts", "max_counts", "max_mt_percent", "min_cells"]
        defaults: {min_genes: 200, max_mt_percent: 20.0, min_cells: 3}
        requires: ["qc_metrics_in_obs_or_count_like_matrix_in_X", "scanpy"]
        tips:
          - "--tissue: Wrapper-level preset that overrides the default QC thresholds with OmicsClaw tissue heuristics."
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
4. **Direct filter summary figures**: before/after comparison and retention summary.
5. **Downstream-ready export**: filtered AnnData, filter-stat table, report, structured result JSON, README, and notebook artifacts.

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
| AnnData | `.h5ad` | yes | current direct input path |
| Demo | `--demo` | yes | bundled fallback |

### Input Expectations

- Accepted input: `.h5ad`
- Expected data state: raw-count-like or QC-annotated AnnData
- Important columns when present: `n_genes_by_counts`, `total_counts`, `pct_counts_mt`
- If QC metrics are missing, the wrapper computes the minimum needed metrics before filtering

## Workflow

1. Load AnnData and inspect available QC columns.
2. Apply optional tissue preset.
3. Filter cells by configured thresholds.
4. Filter genes by `min_cells`.
5. Write `filtered.h5ad`, figures, `tables/filter_stats.csv`, `report.md`, and `result.json`.

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

- `filtered.h5ad`
- `report.md`
- `result.json`
- `figures/`
- `tables/filter_stats.csv`
- `reproducibility/commands.sh`

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/filter_comparison.png`
- `figures/filter_summary.png`

### What Users Should Inspect First

1. `report.md`
2. `figures/filter_comparison.png`
3. `tables/filter_stats.csv`
4. `figures/filter_summary.png`
5. `filtered.h5ad`

## Current Limitations

- This wrapper now writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
- Threshold presets are OmicsClaw wrapper defaults, not upstream standard recommendations for every tissue.
