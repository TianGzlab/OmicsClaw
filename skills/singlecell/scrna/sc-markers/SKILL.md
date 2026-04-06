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

## Core Capabilities

1. **Three marker-ranking modes**: Wilcoxon, t-test, and logistic regression.
2. **Cluster-focused interface**: one `groupby` contract for marker discovery across methods.
3. **Standard direct figure outputs**: heatmap, dotplot, and volcano-style summaries.
4. **Structured table exports**: full marker table plus configurable top-marker table.
5. **Downstream-ready export**: writes `adata_with_markers.h5ad`, report, result JSON, README, and notebook artifacts.

## Scope Boundary

Implemented methods:

1. `wilcoxon`
2. `t-test`
3. `logreg`

This skill is cluster-marker focused; for condition-aware DE use `sc-de`.

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | preferred | most realistic clustered-input path |
| Shared-loader formats | `.h5`, `.loom`, `.csv`, `.tsv`, 10x directory | technically loadable | still need cluster labels to be meaningful |
| Demo | `--demo` | yes | bundled fallback with synthetic clustering |

### Input Expectations

- The current skill expects a clustered or at least group-labeled AnnData object.
- Required metadata: a grouping column such as `leiden`.
- For best behavior, expression should already be normalized and clustering should already be biologically interpretable.

## Workflow

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

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--groupby` | grouping column | core control for marker ranking |
| `--method` | ranking backend | `wilcoxon`, `t-test`, or `logreg` |
| `--n-genes` | maximum genes retained from ranking | affects exported ranking depth |
| `--n-top` | top-hit export size | controls the compact summary table |

## Algorithm / Methodology

Current OmicsClaw `sc-markers` always:

1. validates the grouping column
2. runs Scanpy rank-gene logic with the selected statistical backend
3. exports both full and compact marker summaries
4. renders cluster-focused marker figures

Important implementation notes:

- this skill is for cluster-marker discovery, not replicate-aware condition DE
- the same grouping column drives ranking and figure generation

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

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/markers_heatmap.png`
- `figures/markers_dotplot.png`
- `figures/volcano_plots.png`

### What Users Should Inspect First

1. `report.md`
2. `tables/cluster_markers_top*.csv`
3. `figures/markers_dotplot.png`
4. `figures/markers_heatmap.png`
5. `adata_with_markers.h5ad`

## Current Limitations

- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
- Marker ranking is cluster-centric and does not replace replicate-aware DE analysis.

## Safety And Guardrails

- Confirm that `groupby` truly represents clusters or labels worth ranking before running.
- Marker ranking is not a final annotation by itself and should not be described as formal replicate-aware DE.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-markers-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-markers.md`.
