---
name: spatial-statistics
description: >-
  Comprehensive spatial statistics toolkit — cluster-level (neighborhood enrichment, Ripley, co-occurrence),
  gene-level (Moran's I, Geary's C, local Moran, Getis-Ord), and network-level analysis.
version: 0.2.0
author: SpatialClaw
license: MIT
tags: [spatial, statistics, moran, geary, ripley, neighborhood-enrichment, getis-ord]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "📊"
    homepage: https://github.com/TianGzlab/OmicsClaw
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

**Cluster-level** (require --cluster-key):
1. **Neighborhood enrichment**: Pairwise cluster co-localisation z-scores
2. **Ripley's L function**: Point-pattern analysis per cluster
3. **Co-occurrence**: Pairwise co-occurrence across distances

**Gene-level** (require --genes or --n-top-genes):
4. **Moran's I**: Global spatial autocorrelation per gene
5. **Geary's C**: Global spatial autocorrelation (alternative to Moran)
6. **Local Moran's I (LISA)**: Spatial hotspots per gene
7. **Getis-Ord Gi***: Local hot/cold spot detection
8. **Bivariate Moran**: Spatial cross-correlation between two genes

**Network-level**:
9. **Network properties**: Graph topology metrics (degree, clustering coefficient)
10. **Spatial centrality**: Betweenness/closeness centrality per cluster

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
# Neighborhood enrichment (default, cluster-level)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --output <report_dir>

# Ripley's L function (cluster-level)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type ripley --output <dir>

# Co-occurrence analysis (cluster-level)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type co_occurrence --output <dir>

# Moran's I (gene-level)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type moran --genes "EPCAM,VIM,CD3D" --output <dir>

# Geary's C (gene-level)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type geary --n-top-genes 50 --output <dir>

# Local Moran's I / LISA (gene-level hotspots)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type local_moran --genes "EPCAM" --output <dir>

# Getis-Ord Gi* (gene-level hot/cold spots)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type getis_ord --genes "CD3D,CD8A" --output <dir>

# Bivariate Moran (gene cross-correlation)
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type bivariate_moran --genes "EPCAM,VIM" --output <dir>

# Network properties
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type network_properties --output <dir>

# Spatial centrality
python skills/spatial-statistics/spatial_statistics.py \
  --input <processed.h5ad> --analysis-type spatial_centrality --cluster-key leiden --output <dir>

# Demo mode
python skills/spatial-statistics/spatial_statistics.py --demo --output /tmp/spatial_stats_demo

# Via OmicsClaw runner
python omicsclaw.py run spatial-statistics --input <file> --output <dir>
python omicsclaw.py run spatial-statistics --demo
```

## Example Queries

- "Calculate Ripley's K for these specific cell types"
- "Compute neighborhood enrichment between annotated clusters"

## Algorithm / Methodology

### Cluster-level analyses

**Neighborhood Enrichment**: `squidpy.gr.nhood_enrichment(adata, cluster_key)` computes z-scores by permutation testing. Positive z-scores indicate enrichment (co-localisation), negative indicate depletion.

**Ripley's L Function**: `squidpy.gr.ripley(adata, cluster_key, mode="L")` computes Ripley's L statistic per cluster. L(r) > r indicates clustering at distance r; L(r) < r indicates regularity/dispersion.

**Co-occurrence**: `squidpy.gr.co_occurrence(adata, cluster_key)` measures pairwise cluster co-occurrence across spatial distance intervals.

### Gene-level analyses

**Moran's I**: Global spatial autocorrelation. Range: −1 (dispersion) to +1 (clustering); 0 = random.

**Geary's C**: Alternative autocorrelation measure. Range: 0 (clustering) to 2 (dispersion); 1 = random.

**Local Moran's I (LISA)**: Identifies spatial hotspots (high-high) and coldspots (low-low) for individual genes.

**Getis-Ord Gi***: Local hot/cold spot statistic. Positive Gi* = hotspot, negative = coldspot.

**Bivariate Moran**: Spatial cross-correlation between two genes.

### Network-level analyses

**Network properties**: Degree distribution, clustering coefficient, path length from spatial graph.

**Spatial centrality**: Betweenness and closeness centrality per cluster.

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--analysis-type` | `neighborhood_enrichment` | Analysis type (see list above) |
| `--cluster-key` | `leiden` | Column in `adata.obs` for cluster-level analyses |
| `--genes` | (none) | Comma-separated gene names for gene-level analyses |
| `--n-top-genes` | (none) | Number of top variable genes for gene-level analyses |

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
