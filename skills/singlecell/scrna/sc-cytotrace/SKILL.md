---
name: sc-cytotrace
description: >-
  Predict cell differentiation potency from scRNA-seq data using gene expression
  complexity as a proxy for stemness.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, cytotrace, potency, differentiation, stemness]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
    - "--method"
    - "--n-neighbors"
    - "--r-enhanced"
    param_hints:
      cytotrace_simple:
        priority: "n_neighbors"
        params: ["n_neighbors"]
        defaults: {n_neighbors: 30}
        requires: ["normalized_expression_or_counts"]
        tips:
        - "`cytotrace_simple` uses gene detection count as a potency proxy. No external
          models needed."
    saves_h5ad: true
    requires_preprocessed: true
    legacy_aliases: []
    script: sc_cytotrace.py
---

# Single-Cell CytoTRACE Potency Prediction

## Why This Exists

- Without it: no quick way to estimate which cells are more stem-like vs differentiated.
- With it: a potency score and categorical label for every cell, useful for developmental studies,
  cancer stem cell analysis, and trajectory interpretation.
- Why OmicsClaw: standardized output contract, gallery, and report following the same conventions
  as all other scRNA skills.

## Core Capabilities

1. **cytotrace_simple**: lightweight potency prediction using gene expression complexity
   (number of detected genes per cell) as a proxy for stemness, with KNN smoothing.

## Data / State Requirements

- **Input**: normalized expression or raw counts in `X`
- **Upstream**: `sc-preprocessing` (recommended) or `sc-clustering`
- **Neighbor graph**: built automatically if missing; reused if present
- **UMAP**: computed automatically for visualization if missing

## Method Description

### cytotrace_simple

The `cytotrace_simple` method is inspired by CytoTRACE (Gulati et al., Science 2020),
which showed that gene expression complexity (number of detected genes) correlates with
developmental potential.

Steps:
1. **Gene count**: count genes detected per cell (expression > 0)
2. **Rank normalization**: rank-normalize to [0, 1]
3. **KNN smoothing**: smooth scores using the cell-cell neighbor graph
4. **Potency binning**: assign cells to 6 potency categories

| Category | Score Range | Biological Meaning |
|----------|------------|-------------------|
| Differentiated | 0.00 - 0.17 | Terminally differentiated |
| Unipotent | 0.17 - 0.33 | Can produce one cell type |
| Oligopotent | 0.33 - 0.50 | Can produce few cell types |
| Multipotent | 0.50 - 0.67 | Can produce many cell types |
| Pluripotent | 0.67 - 0.83 | Can produce most cell types |
| Totipotent | 0.83 - 1.00 | Can produce all cell types |

## CLI Reference

```bash
# Basic usage
python skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py \
  --input <preprocessed.h5ad> --output <dir>

# With custom neighbors
python skills/singlecell/scrna/sc-cytotrace/sc_cytotrace.py \
  --input <preprocessed.h5ad> --output <dir> --n-neighbors 50

# Demo mode
python omicsclaw.py run sc-cytotrace --demo --output /tmp/cytotrace_demo
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | analysis method | `cytotrace_simple` (default, only option currently) |
| `--n-neighbors` | KNN smoothing neighbors | default 30; higher = smoother scores |

## Output Contract

Successful runs write:

- `processed.h5ad` -- with `obs['cytotrace_score']`, `obs['cytotrace_potency']`, `obs['cytotrace_gene_count']`
- `figures/potency_umap.png` -- UMAP colored by score and potency category
- `figures/score_distribution.png` -- score histogram
- `figures/potency_composition.png` -- potency category bar chart
- `tables/cytotrace_scores.csv` -- per-cell scores
- `report.md`
- `result.json`
- `reproducibility/commands.sh`

## Downstream Link

- After potency prediction, consider:
  - `sc-pseudotime` -- for trajectory / lineage analysis
  - `sc-de --groupby cytotrace_potency` -- for differential expression between potency levels
  - Overlay potency scores on spatial data if available

## Current Limitations

- `cytotrace_simple` is a heuristic based on gene complexity; it does not use pretrained
  deep learning models like CytoTRACE 2.
- The method assumes that gene detection count correlates with developmental potential,
  which holds for most but not all biological systems.
- Very small datasets (<50 cells) may produce unreliable scores.

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | — | Input `.h5ad` file | required unless `--demo` |
| `--output` | str | — | Output directory | required |
| `--demo` | flag | off | Run with bundled demo data | — |
| `--method` | str | `cytotrace_simple` | Potency method (only `cytotrace_simple` currently) | fixed choice |
| `--n-neighbors` | int | 30 | KNN neighbors for score smoothing | — |
| `--r-enhanced` | flag | off | Also render R Enhanced ggplot2 figures | — |

## R Enhanced Plots

Activated by `--r-enhanced`. Files written to `figures/r_enhanced/`.

| Renderer | Output file | figure_data CSV | Plot description | Required R packages |
|----------|-------------|-----------------|------------------|---------------------|
| `plot_embedding_discrete` | `r_embedding_discrete.png` | `cytotrace_embedding.csv` | UMAP/embedding colored by cell type labels | ggplot2 |
| `plot_embedding_feature` | `r_embedding_feature.png` | `cytotrace_embedding.csv` | UMAP/embedding colored by CytoTRACE score | ggplot2 |

Note: The plan listed 1 R renderer (`plot_feature_boxplot`) for sc-cytotrace, but the actual `R_ENHANCED_PLOTS` dict contains `plot_embedding_discrete` and `plot_embedding_feature`. The cytotrace boxplot renderer (`plot_cytotrace_boxplot`) is registered in the R registry but not wired into the skill's `R_ENHANCED_PLOTS` dict.

## Workflow Position

**Upstream:** sc-clustering or sc-cell-annotation
**Downstream:** Terminal analysis. Consider: sc-pseudotime, sc-velocity
