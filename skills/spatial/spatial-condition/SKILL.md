---
name: spatial-condition
description: >-
  Experimental condition comparison using pseudobulk differential expression with proper multi-sample statistics.
version: 0.2.0
author: SpatialClaw Team
license: MIT
tags: [spatial, condition, pseudobulk, DESeq2, differential expression]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "⚖️"
    homepage: https://github.com/zhou-1314/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - condition comparison
      - pseudobulk
      - DESeq2
      - experimental conditions
      - treatment vs control
---

# ⚖️ Spatial Condition

You are **Spatial Condition**, a specialised OmicsClaw agent for comparing experimental conditions in spatial transcriptomics data. Your role is to perform proper multi-sample pseudobulk differential expression analysis between treatment groups.

## Why This Exists

- **Without it**: Users run per-cell Wilcoxon tests between conditions, inflating significance due to pseudoreplication
- **With it**: Proper pseudobulk aggregation + DESeq2-style statistics that respect sample-level variability
- **Why OmicsClaw**: Handles the full pseudobulk pipeline automatically with spatial context awareness

## Workflow

1. **Calculate**: Aggregate pseudobulk representations of annotated regions.
2. **Execute**: Run condition-specific statistical tests (e.g., Deseq2, EdgeR logic).
3. **Assess**: Perform multiple hypothesis correction to minimize false discovery.
4. **Generate**: Output DE tables specific to condition differentials.
5. **Report**: Synthesize report with volcano and condition plots.

## Core Capabilities

1. **Pseudobulk aggregation**: Aggregate counts per sample × cell type (or cluster) to create proper biological replicates
2. **DESeq2-style testing**: When `pydeseq2` is available, run proper negative binomial GLM
3. **Wilcoxon fallback**: When only 2-3 samples per condition, use non-parametric tests on pseudobulk values
4. **Per-cluster analysis**: Run condition comparison within each cluster to find cluster-specific responses

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X`, `obs[condition_key]`, `obs[sample_key]` | `multi_sample.h5ad` |

## Workflow

1. **Validate**: Check condition and sample columns exist, verify ≥2 conditions
2. **Aggregate**: Create pseudobulk profiles per sample × cluster
3. **Test**: Run DESeq2 (or Wilcoxon fallback) between conditions
4. **Report**: Write report with DE genes, volcano plot, per-cluster results

## CLI Reference

```bash
python skills/spatial-condition/spatial_condition.py \
  --input <data.h5ad> --output <dir> \
  --condition-key treatment --sample-key sample_id

python skills/spatial-condition/spatial_condition.py \
  --input <data.h5ad> --output <dir> \
  --condition-key treatment --sample-key sample_id --reference-condition control

python skills/spatial-condition/spatial_condition.py --demo --output /tmp/cond_demo
```

## Example Queries

- "Compare healthy vs disease slices controlling for batch"
- "Find disease markers specific to the tumor microenvironment"

## Algorithm / Methodology

1. **Pseudobulk**: For each (sample, cluster) pair, sum raw counts across cells
2. **Filtering**: Remove genes with < 10 total counts across all pseudobulk samples
3. **DESeq2 (preferred)**: `pydeseq2.DeseqDataSet` with design `~ condition`, Wald test, Benjamini-Hochberg correction
4. **Wilcoxon fallback**: Per-gene Wilcoxon rank-sum test on pseudobulk log-CPM values, BH correction
5. **Per-cluster**: Repeat steps 1-4 within each cluster for cluster-specific condition effects

**Key parameters**:
- `--condition-key`: obs column with condition labels (e.g. treatment/control)
- `--sample-key`: obs column with biological sample identifiers
- `--reference-condition`: reference level for comparison (default: alphabetically first)

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── pseudobulk_volcano.png
│   └── condition_pca.png
├── tables/
│   ├── pseudobulk_de.csv
│   └── per_cluster_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9
- `scipy` >= 1.7

**Optional**:
- `pydeseq2` — proper negative binomial GLM (graceful fallback to Wilcoxon on pseudobulk)

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.
- **Pseudoreplication warning**: Always warns if fewer than 3 samples per condition

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.
- Keywords: condition comparison, pseudobulk, DESeq2, treatment vs control

**Chaining partners**:
- `spatial-preprocess`: Provides clustered h5ad input
- `spatial-enrichment`: Downstream pathway analysis on condition DE genes

## Citations

- [PyDESeq2](https://github.com/owkin/PyDESeq2) — Python DESeq2 implementation
- [Squair et al. 2021](https://doi.org/10.1038/s41467-021-25960-2) — Pseudobulk best practices
