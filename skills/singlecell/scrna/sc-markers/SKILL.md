---
name: sc-markers
description: >-
  Find cluster marker genes from single-cell data using Scanpy-backed Wilcoxon,
  t-test, or logistic-regression ranking.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, markers, differential-expression, annotation]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--groupby"
      - "--method"
      - "--n-genes"
      - "--n-top"
    param_hints:
      wilcoxon:
        priority: "groupby -> n_genes -> n_top"
        params: ["groupby", "n_genes", "n_top"]
        defaults: {groupby: "leiden", n_top: 10}
        requires: ["cluster_labels_in_obs", "scanpy"]
        tips:
          - "--method wilcoxon: Default non-parametric marker ranking path."
      t-test:
        priority: "groupby -> n_genes -> n_top"
        params: ["groupby", "n_genes", "n_top"]
        defaults: {groupby: "leiden", n_top: 10}
        requires: ["cluster_labels_in_obs", "scanpy"]
        tips:
          - "--method t-test: Parametric alternative for well-behaved inputs."
      logreg:
        priority: "groupby -> n_genes -> n_top"
        params: ["groupby", "n_genes", "n_top"]
        defaults: {groupby: "leiden", n_top: 10}
        requires: ["cluster_labels_in_obs", "scanpy"]
        tips:
          - "--method logreg: Classification-style ranking path."
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install: []
    trigger_keywords:
      - marker genes
      - find markers
      - differential expression
      - cluster markers
      - cell type markers
---

# Single-Cell Markers

## Why This Exists

- Without it: users manually inspect cluster genes without a stable statistical contract.
- With it: marker ranking, top tables, and standard plots are generated in one run.
- Why OmicsClaw: the wrapper keeps cluster-level marker discovery separate from broader DE workflows.

## Scope Boundary

Implemented methods:

1. `wilcoxon`
2. `t-test`
3. `logreg`

This skill is cluster-marker focused; for condition-aware DE use `sc-de`.

## Input Contract

- Accepted input: preprocessed `.h5ad`
- Required metadata: a grouping column such as `leiden`

## Workflow Summary

1. Load clustered AnnData.
2. Rank genes for each cluster with the selected method.
3. Export full and top marker tables.
4. Generate heatmap, dotplot, and volcano-style summaries.
5. Save `adata_with_markers.h5ad`, `report.md`, and `result.json`.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-markers/sc_markers.py \
  --input <data.h5ad> --groupby leiden --output <dir>

python skills/singlecell/scrna/sc-markers/sc_markers.py \
  --input <data.h5ad> --groupby leiden --method t-test --output <dir>

python skills/singlecell/scrna/sc-markers/sc_markers.py \
  --input <data.h5ad> --groupby leiden --n-genes 100 --n-top 10 --output <dir>
```

## Output Contract

Successful runs write:

- `adata_with_markers.h5ad`
- `report.md`
- `result.json`
- `figures/markers_heatmap.png`
- `figures/markers_dotplot.png`
- `figures/volcano_plots.png`
- `tables/cluster_markers_all.csv`
- `tables/cluster_markers_top10.csv`

## Current Limitations

- This skill does not yet emit the same README/notebook bundle as `sc-qc` and `sc-preprocessing`.
- Marker ranking is cluster-centric and does not replace replicate-aware DE analysis.
