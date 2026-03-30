---
name: spatial-statistics
description: >-
  Comprehensive spatial statistics toolkit — cluster-level (neighborhood enrichment, Ripley, co-occurrence),
  gene-level (Moran's I, Geary's C, local Moran, Getis-Ord), and network-level analysis.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [spatial, statistics, moran, geary, ripley, neighborhood-enrichment, getis-ord]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--analysis-type"
      - "--cluster-key"
      - "--genes"
      - "--n-top-genes"
    legacy_aliases: [statistics]
    saves_h5ad: true
    requires_preprocessed: true
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
- **Why OmicsClaw**: Standardised spatial statistics ensure consistent methodology, structured outputs, and wrapper-generated guides for downstream interpretation

## Workflow

1. **Load**: Read the preprocessed AnnData and confirm spatial coordinates are available.
2. **Validate**: Check the requested analysis type and any required cluster or gene arguments.
3. **Build neighbors**: Create or reuse the spatial graph needed for graph-based statistics.
4. **Analyze**: Run the selected cluster-level, gene-level, or network-level statistic.
5. **Report and export**: Write `report.md`, `result.json`, `processed.h5ad`, analysis-specific figures/tables, and the reproducibility bundle.

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

### Unified Data Convention

After `spatial-preprocess`, the AnnData holds:

```
adata.X                              # normalized/log expression (gene-level analyses read this)
adata.obsm["spatial"]                # x,y coordinates
adata.obs["leiden"]                  # cluster / cell-type labels (cluster_key)
adata.obsp["spatial_connectivities"] # spatial graph (auto-built if missing)
```

### Method-Specific Input Requirements

The 10 analyses fall into three categories based on input:

| Category | Analysis | Primary inputs consumed |
|----------|----------|------------------------|
| **Cluster-level** | Neighborhood enrichment | cluster labels + spatial graph |
| | Ripley's L | cluster labels + spatial coordinates |
| | Co-occurrence | cluster labels + spatial coordinates |
| **Gene-level** | Moran's I | gene expression matrix (`adata.X`) + spatial graph |
| | Geary's C | gene expression matrix (`adata.X`) + spatial graph |
| | Local Moran's I (LISA) | single-gene expression vector + spatial weights |
| | Getis-Ord Gi* | single-gene expression vector + spatial weights |
| | Bivariate Moran | two gene-expression vectors + spatial weights |
| **Network-level** | Network properties | spatial graph (+ optional cluster labels for per-cluster summary) |
| | Spatial centrality | spatial graph + cluster labels |

> **Cluster-level**: Consume **cluster labels + coordinates/graph**.
> No expression matrix is read — these are purely spatial pattern analyses
> on categorical labels.
>
> **Gene-level**: Consume **expression + spatial weights**.  Moran's I and
> Geary's C use the full expression matrix via ``sq.gr.spatial_autocorr``;
> local analyses (LISA, Getis-Ord, Bivariate Moran) extract single-gene
> vectors from ``adata.X`` and pair them with PySAL spatial weight objects.
>
> **Network-level**: Consume **spatial graph** only.  Spatial centrality
> additionally requires cluster labels for per-cluster aggregation.

## CLI Reference

```bash
# Neighborhood enrichment (default, cluster-level)
oc run spatial-statistics --input <processed.h5ad> --output <report_dir>

# Ripley's L function (cluster-level)
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type ripley --output <dir>

# Co-occurrence analysis (cluster-level)
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type co_occurrence --output <dir>

# Moran's I (gene-level)
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type moran --genes "EPCAM,VIM,CD3D" --output <dir>

# Geary's C (gene-level)
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type geary --n-top-genes 50 --output <dir>

# Local Moran's I / LISA (gene-level hotspots)
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type local_moran --genes "EPCAM" --output <dir>

# Getis-Ord Gi* (gene-level hot/cold spots)
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type getis_ord --genes "CD3D,CD8A" --output <dir>

# Bivariate Moran (gene cross-correlation)
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type bivariate_moran --genes "EPCAM,VIM" --output <dir>

# Network properties
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type network_properties --output <dir>

# Spatial centrality
oc run spatial-statistics \
  --input <processed.h5ad> --analysis-type spatial_centrality --cluster-key leiden --output <dir>

# Demo mode
oc run spatial-statistics --demo --output /tmp/spatial_stats_demo

# Note: 'oc run' is an alias for 'python omicsclaw.py run'
python omicsclaw.py run spatial-statistics --demo
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun.

## Example Queries

- "Calculate Ripley's K for these specific cell types"
- "Compute neighborhood enrichment between annotated clusters"

## Algorithm / Methodology

### Cluster-level analyses (cluster labels + coordinates/graph)

**Neighborhood Enrichment** — Input: cluster labels + spatial graph
- `squidpy.gr.nhood_enrichment(adata, cluster_key)` computes z-scores by permutation testing
- Positive z-scores indicate enrichment (co-localisation), negative indicate depletion
- Does not read expression matrix

**Ripley's L Function** — Input: cluster labels + spatial coordinates
- `squidpy.gr.ripley(adata, cluster_key, mode="L")` computes Ripley's L per cluster
- L(r) > r indicates clustering at distance r; L(r) < r indicates regularity/dispersion
- Pure point-pattern analysis on coordinates

**Co-occurrence** — Input: cluster labels + spatial coordinates
- `squidpy.gr.co_occurrence(adata, cluster_key)` measures pairwise co-occurrence across distance intervals
- Does not read expression matrix

### Gene-level analyses (expression + spatial weights)

**Moran's I** — Input: gene expression matrix (`adata.X`) + spatial graph
- Global spatial autocorrelation via `sq.gr.spatial_autocorr(mode="moran")`
- Range: -1 (dispersion) to +1 (clustering); 0 = random
- Reads from `adata.X` (typically log-normalized)

**Geary's C** — Input: gene expression matrix (`adata.X`) + spatial graph
- Alternative autocorrelation via `sq.gr.spatial_autocorr(mode="geary")`
- Range: 0 (clustering) to 2 (dispersion); 1 = random

**Local Moran's I (LISA)** — Input: single-gene expression vector + spatial weights
- PySAL `Moran_Local(y, w)` — per-gene, per-spot local autocorrelation
- Identifies spatial hotspots (high-high) and coldspots (low-low)

**Getis-Ord Gi*** — Input: single-gene expression vector + spatial weights
- Local hot/cold spot z-statistic per spot per gene
- Positive Gi* = hotspot, negative = coldspot

**Bivariate Moran** — Input: two gene-expression vectors + spatial weights
- Spatial cross-correlation I_BV between gene pair (x, y)
- Uses PySAL-style computation: `I_BV = (x_z^T W y_z) / sum(W)`

### Network-level analyses (spatial graph)

**Network properties** — Input: spatial graph (+ optional cluster labels)
- Degree distribution, clustering coefficient, graph density from spatial adjacency
- Optionally summarises per cluster

**Spatial centrality** — Input: spatial graph + cluster labels
- `squidpy.gr.centrality_scores(adata, cluster_key)` computes betweenness, closeness, degree centrality per cluster

## Interpretation Guide

### Neighborhood Enrichment Z-scores

| Z-score range | Interpretation |
|---|---|
| z > 2 | Clusters are **significantly co-localized** (neighbors more than expected by chance) |
| -2 < z < 2 | No significant spatial association |
| z < -2 | Clusters are **significantly segregated** (avoid each other spatially) |
| Diagonal values | Cluster self-cohesion (how tightly a cluster's cells are grouped) |

### Moran's I Values

| Moran's I | Interpretation |
|---|---|
| > 0.3 | Strong positive spatial autocorrelation (gene expression is spatially clustered) |
| 0.1 to 0.3 | Moderate spatial clustering |
| -0.1 to 0.1 | Weak or random spatial distribution |
| -0.3 to -0.1 | Moderate spatial dispersion |
| < -0.3 | Strong negative autocorrelation (expression is highly dispersed) |

### Geary's C Values

| Geary's C | Interpretation |
|---|---|
| < 0.5 | Strong positive autocorrelation (spatially clustered) |
| 0.5 to 0.8 | Moderate positive autocorrelation |
| 0.8 to 1.2 | Random spatial distribution |
| 1.2 to 1.5 | Moderate negative autocorrelation (dispersed) |
| > 1.5 | Strong negative autocorrelation |

**Moran's I vs Geary's C**: Moran's I is more sensitive to global patterns; Geary's C is more sensitive to local differences. Use both when spatial patterns are ambiguous.

### Spatial Graph Construction

The system automatically detects the spatial data layout:
- **Visium (grid)**: Uses ``coord_type='grid'``, ``n_neighs=6`` (hexagonal pattern), supports ``n_rings`` for extended neighborhoods
- **Non-Visium (generic)**: Uses ``coord_type='generic'``, ``n_neighs`` as specified
- **Custom**: Users can pre-build the spatial graph before running analyses

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--analysis-type` | `neighborhood_enrichment` | Analysis type (see list above) |
| `--cluster-key` | `leiden` | Column in `adata.obs` for cluster-level analyses |
| `--genes` | (none) | Comma-separated gene names for gene-level analyses |
| `--n-top-genes` | (none) | Number of top variable genes for gene-level analyses |

## Output Structure

```text
output_dir/
├── README.md
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── *.png                          # analysis-type-specific outputs
├── tables/
│   └── *.csv                          # analysis-type-specific outputs
└── reproducibility/
    ├── analysis_notebook.ipynb
    └── commands.sh
```

`README.md` and `reproducibility/analysis_notebook.ipynb` are generated by the
standard OmicsClaw wrapper. Direct script execution usually produces the
skill-native outputs plus `reproducibility/commands.sh`.

## Dependencies

**Required**: squidpy >= 1.2, scanpy >= 1.9, anndata >= 0.11, matplotlib, numpy, pandas, scipy

**Optional** (for local spatial statistics):
- `esda` + `libpysal` — Local Moran's I (LISA), Getis-Ord Gi*, Bivariate Moran
- `networkx` — Network properties analysis

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Reports follow the standard OmicsClaw reporting and disclaimer convention.
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
