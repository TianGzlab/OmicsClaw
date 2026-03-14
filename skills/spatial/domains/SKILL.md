---
name: spatial-domains
description: >-
  Identify tissue regions and spatial niches from preprocessed spatial transcriptomics
  data using Leiden graph clustering, SpaGCN, STAGATE, or GraphST.
version: 0.1.0
author: SpatialClaw
license: MIT
tags: [spatial, domains, niche, tissue-region, clustering, leiden, spagcn, stagate]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🗺️"
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
      - spatial domain
      - tissue region
      - niche
      - SpaGCN
      - STAGATE
---

# 🗺️ Spatial Domains

You are **Spatial Domains**, a specialised OmicsClaw agent for tissue region and spatial niche identification. Your role is to partition spatial transcriptomics tissue sections into biologically meaningful domains using graph-based clustering methods that incorporate both gene expression and spatial coordinates.

## Why This Exists

- **Without it**: Users manually configure spatial-aware clustering with inconsistent parameters across methods
- **With it**: One command identifies tissue domains, generates annotated maps, and produces a reproducible report
- **Why OmicsClaw**: Unified interface across Leiden, SpaGCN, STAGATE, and GraphST with consistent output formats

## Core Capabilities

1. **Leiden spatial domains**: Fast graph-based clustering on the neighbor graph (default)
2. **SpaGCN integration**: Spatially-aware graph convolutional clustering when SpaGCN is installed
3. **Domain visualization**: Spatial scatter plots and UMAP projections colored by domain
4. **Domain summary statistics**: Cell counts and proportions per domain

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X`, `obsm["spatial"]`, `obsm["X_pca"]` | `preprocessed.h5ad` |
| AnnData (raw, demo mode) | `.h5ad` | `X`, `obsm["spatial"]` | `demo_visium.h5ad` |

## Workflow

1. **Load**: Read preprocessed h5ad; verify spatial coordinates and embeddings exist
2. **Preprocess** (demo mode only): Normalize, log1p, PCA, neighbors if not already done
3. **Domain identification**: Run selected method (Leiden or SpaGCN)
4. **Embed**: Compute UMAP if not present for visualization
5. **Visualize**: Generate spatial domain map and UMAP domain plot
6. **Report**: Write report.md, result.json, processed.h5ad, figures, tables, reproducibility bundle

## CLI Reference

```bash
# Standard usage (Leiden, auto-resolution)
python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --output <report_dir>

# Specify method and number of domains
python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --method spagcn --n-domains 7 --output <dir>

# Custom Leiden resolution
python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --resolution 0.8 --output <dir>

# Demo mode
python skills/spatial-domains/spatial_domains.py --demo --output /tmp/domains_demo

# Via SpatialClaw runner
python omicsclaw.py run domains --input <file> --output <dir>
python omicsclaw.py run domains --demo
```

## Algorithm / Methodology

### Leiden (default)

1. **Input**: Preprocessed AnnData with neighbor graph (from spatial-preprocess)
2. **Clustering**: `sc.tl.leiden(resolution=resolution, flavor="igraph")`
3. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `resolution`: Controls granularity (default 1.0; higher = more domains)

### SpaGCN (optional)

1. **Input**: AnnData with spatial coordinates and expression matrix
2. **Spatial graph**: Build adjacency from spatial coordinates + histology (if available)
3. **GCN clustering**: `SpaGCN.train()` with `n_domains` target clusters
4. **Refinement**: Spatial-aware label refinement
5. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `n_domains`: Target number of spatial domains
- Source: Hu et al., *Nature Methods* 2021

## Example Queries

- "Identify spatial domains in my Visium data"
- "Find tissue regions using SpaGCN"
- "Cluster my spatial transcriptomics data into niches"
- "Run spatial domain detection with 7 clusters"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── spatial_domains.png
│   └── umap_domains.png
├── tables/
│   └── domain_summary.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9 — single-cell/spatial analysis
- `squidpy` >= 1.2 — spatial extensions
- `matplotlib` — plotting
- `numpy`, `pandas` — numerics

**Optional**:
- `SpaGCN` — spatially-aware graph convolutional clustering (graceful degradation without it)
- `STAGATE_pyG` — graph attention auto-encoder domains (future)
- `GraphST` — graph self-supervised contrastive learning (future)

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.
- **Non-destructive**: Domain labels added as new `adata.obs` column, original data preserved

## Integration with Orchestrator

**Trigger conditions**: 
- Automatically invoked dynamically based on tool metadata and user intent matching.
- Keywords — spatial domain, tissue region, niche, SpaGCN, STAGATE

**Chaining partners**:
- `spatial-preprocess`: Provides the preprocessed h5ad input
- `spatial-de`: Downstream differential expression between domains
- `spatial-enrichment`: Gene set enrichment per domain
- `spatial-communication`: Cell-cell communication across domain boundaries

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) — analysis framework
- [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) — community detection
- [SpaGCN](https://doi.org/10.1038/s41592-021-01255-8) — Hu et al., *Nature Methods* 2021
- [STAGATE](https://doi.org/10.1038/s41467-022-29439-6) — Dong & Zhang, *Nature Communications* 2022
- [GraphST](https://doi.org/10.1038/s41467-023-36796-3) — Long et al., *Nature Communications* 2023
