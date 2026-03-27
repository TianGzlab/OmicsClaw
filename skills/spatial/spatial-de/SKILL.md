---
name: spatial-de
description: >-
  Differential expression analysis — find marker genes for clusters or compare two groups.
  Supports Wilcoxon rank-sum, t-test, and PyDESeq2 methods with publication-ready figures and CSV tables.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [spatial, differential-expression, markers, wilcoxon, t-test, pydeseq2]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--group1"
      - "--group2"
      - "--groupby"
      - "--method"
      - "--n-top-genes"
    legacy_aliases: [de]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧬"
    homepage: https://github.com/TianGzlab/OmicsClaw
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

1. **Cluster-vs-rest markers**: Rank genes per cluster using Wilcoxon, t-test, or PyDESeq2
2. **Two-group comparison**: Compare any two groups within a groupby column
3. **Multiple methods**: Wilcoxon (default, non-parametric), t-test (parametric, fast), PyDESeq2 (pseudobulk, gold standard)
4. **Marker filtering**: Removes non-specific markers using min_in_group_fraction (25%), min_fold_change (1.0), max_out_group_fraction (50%)
5. **Pseudobulk validation**: Validates that conditions have sufficient replicates before running DESeq2
6. **Dot plot**: Top marker genes per cluster
7. **Volcano plot**: Log2 fold-change vs. −log10 p-value for two-group comparisons
8. **Marker table**: CSV of top N markers per cluster with scores, p-values, and log fold-changes

## Input Matrix Convention

| Method | Input Matrix Type | Uses raw counts | Requires normalized / log | Notes |
|--------|----------------|---------------:|------------------------:|-------|
| `wilcoxon` | `AnnData` expression matrix | No | **Yes, requires log expression** | Scanpy `rank_genes_groups` |
| `t-test` | `AnnData` expression matrix | No | **Yes, requires log expression** | Scanpy Welch's t-test |
| `pydeseq2` | sample × gene matrix after pseudobulk | **Yes** | No | Requires non-negative integer counts |

* **`wilcoxon` & `t-test`**: Uses `adata.X`. Expects **logarithmized data** (e.g., `normalize_total` + `log1p`). Do not input raw counts or pseudobulk counts directly.
* **`pydeseq2`**: Uses **pseudobulk raw integer counts**. Extracted from `adata.layers["counts"]` or `adata.raw`, aggregated per sample, and passed to PyDESeq2. Cannot use log-normalized or scaled matrices.

## Marker Filtering

By default, markers are filtered to retain only biologically meaningful genes:

| Filter | Default | Purpose |
|--------|---------|---------|
| `min_in_group_fraction` | 0.25 | Gene must be in >= 25% of cluster cells |
| `min_fold_change` | 1.0 | Natural log fold change >= 1 |
| `max_out_group_fraction` | 0.5 | Gene in < 50% of other clusters |

Filtering removes housekeeping genes and non-specific markers that pass statistical tests but lack biological specificity. Disable with `--no-filter-markers` if needed.

## Pseudobulk DE Requirements

When using `--method pydeseq2`:
- Each condition requires at least 2 pseudobulk replicates for valid dispersion estimation
- Conditions with very few cells (< 20) will produce unreliable results
- The system warns when conditions have insufficient replication

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
# Cluster-vs-rest markers (default: Wilcoxon, uses log-normalized data)
oc run spatial-de \
  --input <processed.h5ad> --output <report_dir>

# Two-group comparison
oc run spatial-de \
  --input <processed.h5ad> --output <dir> \
  --group1 0 --group2 1

# Use t-test method
oc run spatial-de \
  --input <file> --output <dir> --method t-test

# Use PyDESeq2 for pseudobulk DE (requires raw integer counts)
oc run spatial-de \
  --input <file> --output <dir> \
  --method pydeseq2 --group1 0 --group2 1 

# Run the internally generated demo scenario
oc run spatial-de --demo --output /tmp/de_demo

# --- Direct Script Execution (Alternative) ---
python skills/spatial/spatial-de/spatial_de.py --demo --output /tmp/de_demo
python skills/spatial/spatial-de/spatial_de.py --input <processed.h5ad> --output <dir>
```

## Algorithm / Methodology

### Wilcoxon (default)
1. **Cluster-vs-rest**: `sc.tl.rank_genes_groups(adata, groupby=groupby, method='wilcoxon')`
2. **Non-parametric**: Robust to non-normal distributions
3. **Fast**: Suitable for large datasets

### t-test
1. **Parametric**: `sc.tl.rank_genes_groups(adata, groupby=groupby, method='t-test')`
2. **Welch's t-test**: Assumes normality, faster than Wilcoxon
3. **Use case**: Quick exploratory analysis

### PyDESeq2
1. **Pseudobulk**: Aggregates counts per sample/replicate
2. **Negative binomial GLM**: Gold standard for RNA-seq DE
3. **Requires**: Sample-level replicates for proper statistical modeling
4. **Use case**: Publication-quality DE with proper dispersion estimation

### Common steps
1. **Two-group comparison**: `sc.tl.rank_genes_groups(adata, groupby=groupby, groups=[group1], reference=group2, method=method)`
2. **Marker extraction**: `sc.get.rank_genes_groups_df` to produce structured DataFrames
3. **Volcano plot**: x-axis = log2 fold-change (`logfoldchanges`), y-axis = −log10(adjusted p-value)

## Example Queries

- "Find marker genes for all my spatial clusters"
- "Identify differentially expressed genes between cluster 1 and cluster 3"

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--groupby` | `leiden` | Column in `adata.obs` to group by |
| `--method` | `wilcoxon` | Statistical test: `wilcoxon`, `t-test`, or `pydeseq2` |
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
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required**: scanpy >= 1.9, anndata >= 0.11, matplotlib, numpy, pandas

**Optional**:
- `pydeseq2` — PyDESeq2 pseudobulk differential expression

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
