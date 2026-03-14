---
name: spatial-statistics
description: >-
  Spatial statistics and autocorrelation analysis — Moran's I, Ripley's functions,
  neighborhood enrichment, and co-occurrence analysis for spatial transcriptomics data.
version: 0.1.0
author: SpatialClaw
license: MIT
tags: [spatial, statistics, Moran, Ripley, neighborhood-enrichment]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "📊"
    homepage: https://github.com/SpatialClaw/SpatialClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: squidpy
        bins: []
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - spatial statistics
      - autocorrelation
      - Moran
      - Ripley
      - neighborhood enrichment
      - spatial pattern
      - co-occurrence
      - nhood enrichment
---

# 📊 Spatial Statistics

You are **Spatial Statistics**, the spatial autocorrelation and neighborhood analysis skill for OmicsClaw. Your role is to quantify spatial patterns in tissue sections — measuring cluster co-localisation via neighborhood enrichment, point-pattern regularity via Ripley's functions, and cell-type co-occurrence.

## Why This Exists

- **Without it**: Users manually call squidpy functions with inconsistent parameters and no structured output
- **With it**: One command produces neighborhood enrichment heatmaps, Ripley's curves, and co-occurrence matrices with reproducible reports
- **Why OmicsClaw**: Standardised spatial statistics ensure consistent methodology across spatial analysis pipelines

## Workflow

1. **Calculate**: Map out local point processes from coordinates.
2. **Execute**: Evaluate cross-pair relationships across graph networks.
3. **Assess**: Perform Ripley's K or spatial autocorrelation permutation.
4. **Generate**: Output structured metric arrays or interaction heatmaps.
5. **Report**: Tabulate key statistical significances.

## Core Capabilities

1. **Neighborhood enrichment**: Z-score matrix of cluster co-localisation (squidpy `nhood_enrichment`)
2. **Ripley's L function**: Point-pattern analysis per cluster to detect clustering vs. dispersion
3. **Co-occurrence**: Pairwise cluster co-occurrence ratios across distance intervals
4. **Heatmap figure**: Publication-ready heatmap of the neighborhood enrichment z-score matrix

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| Preprocessed AnnData | `.h5ad` | Normalised, clustered, with spatial coordinates | `processed.h5ad` |
| Demo | n/a | `--demo` flag | Built-in via spatial-preprocess |

## Workflow

1. **Load**: Read preprocessed h5ad (output of spatial-preprocess)
2. **Validate**: Ensure spatial coordinates and cluster column exist; convert cluster key to categorical if needed
3. **Spatial neighbors**: Build spatial connectivity graph via `squidpy.gr.spatial_neighbors`
4. **Analyze**: Run the selected analysis type (neighborhood_enrichment, ripley, or co_occurrence)
5. **Figures**: Heatmap of enrichment z-scores (for neighborhood_enrichment)
6. **Report**: Write report.md, result.json, tables/enrichment_zscore.csv, processed.h5ad, figures, reproducibility bundle

## CLI Reference

```bash
# Neighborhood enrichment (default)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --output <report_dir>

# Ripley's L function
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --output <dir> --analysis-type ripley

# Co-occurrence analysis
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --output <dir> --analysis-type co_occurrence

# Demo mode
python skills/spatial-statistics/spatial_statistics.py --demo --output /tmp/spatial_stats_demo

# Custom cluster key
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --output <dir> --cluster-key cell_type

python omicsclaw.py run stats --input <file> --output <dir>
python omicsclaw.py run stats --demo
```

## Example Queries

- "Calculate Ripley's K for these specific cell types"
- "Compute neighborhood enrichment between annotated clusters"

## Algorithm / Methodology

### Neighborhood Enrichment

`squidpy.gr.nhood_enrichment(adata, cluster_key)` computes z-scores by permutation testing. For each pair of clusters (i, j), it counts how many times a cell of cluster i neighbours a cell of cluster j, compares to a permuted null, and returns a z-score matrix. Positive z-scores indicate enrichment (co-localisation), negative indicate depletion (avoidance).

### Ripley's L Function

`squidpy.gr.ripley(adata, cluster_key, mode="L")` computes Ripley's L statistic per cluster. L(r) > r indicates clustering at distance r; L(r) < r indicates regularity/dispersion. Results include the L statistic curves per cluster across distance bins.

### Co-occurrence

`squidpy.gr.co_occurrence(adata, cluster_key)` measures pairwise cluster co-occurrence across spatial distance intervals, returning occurrence ratios relative to expected counts under spatial randomness.

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--analysis-type` | `neighborhood_enrichment` | Analysis to run: `neighborhood_enrichment`, `ripley`, or `co_occurrence` |
| `--cluster-key` | `leiden` | Column in `adata.obs` containing cluster labels |
| `--feature` | (none) | Gene name for gene-level spatial statistics (future) |

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── nhood_enrichment_heatmap.png   (neighborhood_enrichment only)
├── tables/
│   └── enrichment_zscore.csv          (neighborhood_enrichment only)
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required**: squidpy >= 1.2, scanpy >= 1.9, anndata >= 0.11, matplotlib, numpy, pandas

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.
- Keywords: spatial statistics, autocorrelation, Moran, Ripley, neighborhood enrichment, spatial pattern, co-occurrence

**Chaining**: Expects `processed.h5ad` from spatial-preprocess as input

## Citations

- [Squidpy](https://squidpy.readthedocs.io/) — spatial analysis framework
- [Moran's I](https://en.wikipedia.org/wiki/Moran%27s_I) — spatial autocorrelation
- [Ripley's K/L function](https://en.wikipedia.org/wiki/Spatial_descriptive_statistics#Ripley's_K_and_L_functions) — point-pattern analysis
- [Neighborhood enrichment](https://doi.org/10.1038/s41592-021-01358-2) — squidpy methodology (Palla et al., 2022)
