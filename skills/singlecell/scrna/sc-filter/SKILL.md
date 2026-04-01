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

## Input Contract

- Accepted input: `.h5ad`
- Expected data state: raw-count-like or QC-annotated AnnData
- Important columns when present: `n_genes_by_counts`, `total_counts`, `pct_counts_mt`
- If QC metrics are missing, the wrapper computes the minimum needed metrics before filtering

## Workflow Summary

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

## Output Contract

Successful runs write:

- `filtered.h5ad`
- `report.md`
- `result.json`
- `figures/`
- `tables/filter_stats.csv`
- `reproducibility/commands.sh`

## Current Limitations

- This wrapper now writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
- Threshold presets are OmicsClaw wrapper defaults, not upstream standard recommendations for every tissue.
