---
name: sc-markers
description: >-
  Find marker genes for cell clusters using Wilcoxon, t-test, or logistic
  regression. Essential for cell type annotation.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [singlecell, markers, differential expression, annotation]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🎯"
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

# 🎯 Single-Cell Marker Genes

Identify marker genes that distinguish cell clusters.

## Why This Exists

- **Without it**: Manual inspection of cluster-specific genes
- **With it**: Automated marker identification with statistical testing
- **Why OmicsClaw**: Multiple methods with comprehensive visualizations

## Core Capabilities

1. **Wilcoxon test**: Non-parametric rank-sum test (default)
2. **t-test**: Parametric differential expression
3. **Logistic regression**: Classification-based markers
4. **Visualization**: Heatmaps, dot plots, volcano plots

## Workflow

1. **Load clustered data**: Input should have cluster assignments
2. **Find markers**: Run statistical test per cluster
3. **Filter results**: By fold change, p-value, expression fraction
4. **Visualize**: Generate summary figures and tables

## CLI Reference

```bash
# Basic usage
python skills/singlecell/scrna/sc-markers/sc_markers.py --input <data.h5ad> --output <dir> --groupby leiden

# With specific method
python skills/singlecell/scrna/sc-markers/sc_markers.py --input <data.h5ad> --output <dir> \
  --groupby leiden --method t-test

# Limit number of genes
python skills/singlecell/scrna/sc-markers/sc_markers.py --input <data.h5ad> --output <dir> \
  --groupby leiden --n-genes 100

# Demo mode
python omicsclaw.py run sc-markers --demo
```

## Methods

### Wilcoxon (Default)
- Non-parametric Mann-Whitney U test
- Robust to outliers
- Best for most use cases

### t-test
- Parametric test
- Assumes normal distribution
- More sensitive to fold changes

### Logistic Regression
- Multiclass classification
- Good for overlapping populations
- Computationally intensive

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--groupby` | leiden | Column with cluster assignments |
| `--method` | wilcoxon | wilcoxon, t-test, logreg |
| `--n-genes` | None | Genes per cluster (None = all) |
| `--n-top` | 10 | Top markers for visualization |

## Example Queries

- "Find marker genes for my clusters"
- "Identify differentially expressed genes by cluster"
- "What markers define each cell type?"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── adata_with_markers.h5ad
├── figures/
│   ├── markers_heatmap.png
│   ├── markers_dotplot.png
│   └── volcano_plots.png
├── tables/
│   ├── cluster_markers_all.csv
│   └── cluster_markers_top10.csv
└── reproducibility/
    ├── commands.sh
    └── environment.yml
```

## Marker Table Columns

| Column | Description |
|--------|-------------|
| group | Cluster ID |
| names | Gene name |
| scores | Test statistic score |
| pvals | Raw p-value |
| pvals_adj | Adjusted p-value (FDR) |
| logfoldchanges | Log2 fold change |

## Interpretation

- **LogFC > 1**: Gene upregulated in this cluster
- **pvals_adj < 0.05**: Statistically significant
- **scores**: Higher = more cluster-specific

## Dependencies

**Required**: scanpy, numpy, pandas, seaborn

## Integration with Orchestrator

**Trigger conditions**:
- Query mentions "marker genes", "find markers", "differential expression"
- Query asks about cluster-specific genes

**Chaining partners**:
- `sc-preprocessing` — Requires clustered data
- `sc-cell-annotation` — Use markers for annotation
