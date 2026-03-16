---
name: spatial-domains
description: >-
  Identify tissue regions and spatial niches from preprocessed spatial transcriptomics
  data using Leiden, Louvain, SpaGCN, STAGATE, GraphST, or BANKSY.
version: 0.3.0
author: SpatialClaw
license: MIT
tags: [spatial, domains, niche, tissue-region, clustering, leiden, louvain, spagcn, stagate, graphst, banksy]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🗺️"
    homepage: https://github.com/zhou-1314/OmicsClaw
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

1. **Leiden spatial domains**: Fast graph-based clustering with spatial-weighted neighbors (default)
2. **Louvain clustering**: Classic graph-based clustering (requires louvain package)
3. **SpaGCN**: Spatial Graph Convolutional Network integrating histology
4. **STAGATE**: Graph attention auto-encoder (requires PyTorch Geometric)
5. **GraphST**: Self-supervised contrastive learning (requires PyTorch)
6. **BANKSY**: Explicit spatial feature augmentation (interpretable)
7. **Domain visualization**: Spatial scatter plots and UMAP projections colored by domain
8. **Domain summary statistics**: Cell counts and proportions per domain
9. **Spatial refinement**: Optional KNN-based spatial smoothing of domain labels

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (log-norm), `obsm["spatial"]`, `obsm["X_pca"]`, `raw` (counts) | `preprocessed.h5ad` |
| AnnData (raw, demo mode) | `.h5ad` | `X`, `obsm["spatial"]` | `demo_visium.h5ad` |

### Input Preprocessing Notes

Different methods consume the `preprocessed.h5ad` data differently. The skill
automatically selects the correct data layer for each method:

| Method | Used from adata | Internal preprocessing |
|--------|----------------|------------------------|
| **Leiden / Louvain** | `obsp["connectivities"]` (neighbor graph) | None — uses pre-built graph |
| **SpaGCN** | `X` (log-normalized) | Internal PCA on expression matrix |
| **STAGATE** | `X` (log-norm, HVG subset) | Auto-filters to `var["highly_variable"]` before training |
| **GraphST** | `raw.X` (raw counts) | Internal `log1p → normalize → scale → HVG(3000)` |
| **BANKSY** | `X` (log-norm + z-scored) | Auto-applies `sc.pp.scale()` before feature construction |

> **Why raw counts for GraphST?** GraphST's `preprocess()` internally does
> `log1p` + `normalize_total` + `scale` + HVG selection. Passing already
> log-normalized data would cause a double log-transform (`log(log(x+1)+1)`),
> which distorts the expression distribution. The skill automatically restores
> `adata.raw` when available.

## Workflow

1. **Load**: Read preprocessed h5ad; verify spatial coordinates and embeddings exist
2. **Preprocess** (demo mode only): Normalize, log1p, PCA, neighbors if not already done
3. **Domain identification**: Run selected method (Leiden or SpaGCN)
4. **Embed**: Compute UMAP if not present for visualization
5. **Visualize**: Generate spatial domain map and UMAP domain plot
6. **Report**: Write report.md, result.json, processed.h5ad, figures, tables, reproducibility bundle

## CLI Reference

```bash
# Standard usage (Leiden, default)
python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --output <report_dir>

# Specify method and parameters
python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --method leiden --resolution 0.8 --spatial-weight 0.3 --output <dir>

python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --method louvain --resolution 1.0 --output <dir>

python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --method spagcn --n-domains 7 --output <dir>

python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --method stagate --n-domains 7 --rad-cutoff 50.0 --output <dir>

python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --method graphst --n-domains 7 --output <dir>

python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --method banksy --resolution 0.7 --lambda-param 0.2 --output <dir>

# Apply spatial refinement
python skills/spatial-domains/spatial_domains.py \
  --input <preprocessed.h5ad> --method leiden --refine --output <dir>

# Demo mode
python skills/spatial-domains/spatial_domains.py --demo --output /tmp/domains_demo

# Via OmicsClaw runner
python omicsclaw.py run spatial-domain-identification --input <file> --output <dir>
python omicsclaw.py run spatial-domain-identification --demo
```

## Algorithm / Methodology

### Leiden (default)

1. **Input**: Preprocessed AnnData with neighbor graph (uses `adata.obsp["connectivities"]`)
2. **Spatial weighting**: Combines expression-based and spatial neighbor graphs with configurable weight
3. **Clustering**: `sc.tl.leiden(resolution=resolution, flavor="igraph")`
4. **Labels**: Stored in `adata.obs["spatial_domain"]`
5. **Data layer used**: Neighbor graph only — does not touch `adata.X`

**Key parameters**:
- `resolution`: Controls granularity (default 1.0; higher = more domains)
- `spatial_weight`: Weight of spatial graph (0.0-1.0, default 0.3)
- `n_neighbors`: Number of neighbors for graph construction (default 15)

### Louvain

1. **Input**: Preprocessed AnnData with neighbor graph (uses `adata.obsp["connectivities"]`)
2. **Clustering**: `sc.tl.louvain(resolution=resolution)`
3. **Labels**: Stored in `adata.obs["spatial_domain"]`
4. **Requires**: `pip install louvain`
5. **Data layer used**: Neighbor graph only — does not touch `adata.X`

**Key parameters**:
- `resolution`: Controls granularity (default 1.0)

### SpaGCN

1. **Input**: AnnData with spatial coordinates and log-normalized expression matrix
2. **Data layer used**: `adata.X` (log-normalized full gene matrix) — SpaGCN performs internal PCA
3. **Spatial graph**: Build adjacency from spatial coordinates
4. **GCN clustering**: `SpaGCN.train()` with `n_domains` target clusters
5. **Refinement**: Built-in spatial-aware label refinement
6. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `n_domains`: Target number of spatial domains
- Source: Hu et al., *Nature Methods* 2021

### STAGATE

1. **Input**: AnnData with spatial coordinates (auto-subsets to HVGs)
2. **HVG filtering**: If `adata.var["highly_variable"]` exists, only HVGs are used for the autoencoder (reduces noise, improves convergence speed)
3. **Spatial network**: Build graph with radius cutoff
4. **Graph attention**: Train attention auto-encoder on PyTorch (HVG subset)
5. **Clustering**: Gaussian Mixture Model on learned embeddings
6. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `n_domains`: Target number of domains
- `rad_cutoff`: Radius for spatial network (default 50.0)
- Source: Dong & Zhang, *Nature Communications* 2022

### GraphST

1. **Input**: AnnData with spatial coordinates (**raw counts** from `adata.raw`)
2. **Raw count restoration**: Automatically restores `adata.raw.X` to avoid double log-transform (GraphST internally does `log1p → normalize → scale → HVG(3000)`)
3. **Preprocessing**: `GraphST.preprocess()` + `GraphST.construct_interaction()`
4. **Contrastive learning**: Self-supervised graph neural network
5. **Embedding**: PCA on learned representations
6. **Clustering**: Gaussian Mixture Model
7. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `n_domains`: Target number of domains
- Source: Long et al., *Nature Communications* 2023
- ⚠️ Requires `adata.raw` to contain raw counts; if absent, falls back to `adata.X` with a warning

### BANKSY

1. **Input**: AnnData with spatial coordinates
2. **Z-score scaling**: Auto-applies `sc.pp.scale(max_value=10)` on working copy to prevent high-expression genes from dominating neighbourhood features
3. **Feature augmentation**: Neighborhood-averaged expression + azimuthal Gabor filters
4. **PCA**: Dimensionality reduction on augmented features
5. **Clustering**: Leiden on BANKSY-augmented space
6. **Labels**: Stored in `adata.obs["spatial_domain"]`

**Key parameters**:
- `lambda_param`: Spatial regularization (default 0.2)
- `resolution`: Leiden resolution (default 0.7)
- `num_neighbours`: Neighbors for feature construction (default 15)

### Spatial Refinement (optional)

1. **KNN smoothing**: For each spot, find k nearest spatial neighbors
2. **Majority vote**: Relabel if >threshold fraction of neighbors disagree
3. **Conservative**: Only changes labels with strong spatial disagreement

**Key parameters**:
- `threshold`: Disagreement threshold (default 0.5)
- `k`: Number of spatial neighbors (default 10)

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
- `SpaGCN` — spatially-aware graph convolutional clustering
- `STAGATE_pyG` — graph attention auto-encoder domains (requires PyTorch)
- `GraphST` — graph self-supervised contrastive learning (requires PyTorch)
- `banksy` — spatial feature augmentation
- `louvain` — Louvain clustering algorithm

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
