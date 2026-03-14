---
name: spatial-de
description: >-
  Differential expression analysis — find marker genes for clusters or compare two groups.
  Supports Wilcoxon rank-sum and t-test methods with publication-ready figures and CSV tables.
version: 0.1.0
author: SpatialClaw
license: MIT
tags: [spatial, differential-expression, markers, Wilcoxon]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧬"
    homepage: https://github.com/SpatialClaw/SpatialClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
      - kind: pip
        package: squidpy
        bins: []
    trigger_keywords:
      - differential expression
      - marker gene
      - DE
      - Wilcoxon
      - group comparison
---

# 🧬 Spatial DE

You are **Spatial DE**, the differential expression and marker gene discovery skill for OmicsClaw. Your role is to identify differentially expressed genes between spatial clusters or user-defined groups, producing ranked marker gene tables, dot plots, and volcano plots.

## Why This Exists

- **Without it**: Users manually run `sc.tl.rank_genes_groups` with inconsistent parameters and no structured output
- **With it**: One command discovers markers per cluster or between two groups, with publication-ready figures and reproducible reports
- **Why OmicsClaw**: Standardised DE ensures consistent methodology across spatial analysis pipelines

## Core Capabilities

1. **Cluster-vs-rest markers**: Rank genes per cluster using Wilcoxon or t-test
2. **Two-group comparison**: Compare any two groups within a groupby column
3. **Dot plot**: Top marker genes per cluster
4. **Volcano plot**: Log2 fold-change vs. −log10 p-value for two-group comparisons
5. **Marker table**: CSV of top N markers per cluster with scores, p-values, and log fold-changes

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| Preprocessed AnnData | `.h5ad` | Normalised, with clusters in `.obs` | `processed.h5ad` |
| Demo | n/a | `--demo` flag | Runs spatial-preprocess demo first |

## Workflow

1. **Load**: Read preprocessed h5ad (output of spatial-preprocess)
2. **Validate**: Ensure groupby column exists; fallback to minimal preprocessing if missing
3. **Rank genes**: `sc.tl.rank_genes_groups(adata, groupby, method)` for cluster-vs-rest
4. **Two-group** (optional): If `--group1` and `--group2` provided, run pairwise comparison
5. **Tables**: Extract top N markers per group to `markers_top.csv`; full results to `de_full.csv`
6. **Figures**: Dot plot of top markers; volcano plot if two-group mode
7. **Report**: Write report.md, result.json, processed.h5ad, figures, reproducibility bundle

## CLI Reference

```bash
python skills/spatial-de/spatial_de.py \
  --input <processed.h5ad> --output <report_dir>

python skills/spatial-de/spatial_de.py \
  --input <processed.h5ad> --output <dir> --group1 0 --group2 1

python skills/spatial-de/spatial_de.py --demo --output /tmp/de_demo

python omicsclaw.py run de --input <file> --output <dir>
python omicsclaw.py run de --demo
```

## Algorithm / Methodology

1. **Cluster-vs-rest**: `sc.tl.rank_genes_groups(adata, groupby=groupby, method=method)`
   - Wilcoxon rank-sum test (default): non-parametric, robust to non-normal distributions
   - t-test: parametric alternative
2. **Two-group comparison**: `sc.tl.rank_genes_groups(adata, groupby=groupby, groups=[group1], reference=group2, method=method)`
3. **Marker extraction**: `sc.get.rank_genes_groups_df` to produce structured DataFrames
4. **Volcano plot**: x-axis = log2 fold-change (`logfoldchanges`), y-axis = −log10(adjusted p-value)

## Example Queries

- "Find marker genes for all my spatial clusters"
- "Identify differentially expressed genes between cluster 1 and cluster 3"

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--groupby` | `leiden` | Column in `adata.obs` to group by |
| `--method` | `wilcoxon` | Statistical test: `wilcoxon` or `t-test` |
| `--n-top-genes` | `10` | Number of top markers per group |
| `--group1` | (none) | First group for pairwise comparison |
| `--group2` | (none) | Second group (reference) for pairwise comparison |

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── marker_dotplot.png
│   └── de_volcano.png          (only if --group1/--group2)
├── tables/
│   ├── markers_top.csv
│   └── de_full.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy >= 1.9, anndata >= 0.11, matplotlib, numpy, pandas

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.
- Keywords: differential expression, marker gene, DE, Wilcoxon, group comparison

**Chaining**: Expects `processed.h5ad` from spatial-preprocess as input. Demo mode runs spatial-preprocess automatically.

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) — analysis framework
- [Wilcoxon rank-sum test](https://en.wikipedia.org/wiki/Wilcoxon_signed-rank_test) — non-parametric test
- [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) — community detection (for cluster labels)
