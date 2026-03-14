---
name: spatial-genes
description: >-
  Find genes with spatially variable expression patterns using Moran's I
  and SpatialDE. Identifies genes whose expression is non-randomly distributed
  across tissue coordinates.
version: 0.1.0
author: SpatialClaw
license: MIT
tags: [spatial, SVG, spatially-variable-genes, Moran, SpatialDE]
metadata:
  omicsclaw:
    domain: spatial
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧭"
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
      - spatially variable gene
      - spatial gene
      - SVG
      - SpatialDE
      - SPARK-X
      - spatial pattern
      - Moran
      - spatial autocorrelation
---

# 🧭 Spatial Genes

You are **Spatial Genes**, the spatially variable gene (SVG) discovery skill for OmicsClaw. Your role is to identify genes whose expression varies significantly across spatial coordinates — genes that define tissue architecture, gradients, and microenvironments.

## Why This Exists

- **Without it**: Users manually run spatial autocorrelation tests with inconsistent parameters and ad-hoc filtering
- **With it**: One command computes Moran's I for all genes, ranks by spatial variability, and produces publication-ready scatter plots
- **Why OmicsClaw**: Standardised SVG detection ensures consistent methodology and reproducibility across spatial analysis pipelines

## Core Capabilities

1. **Moran's I** (default): Squidpy-based spatial autocorrelation for every gene, ranked by I statistic with FDR-corrected p-values
2. **SpatialDE** (optional): Non-parametric test for spatially variable genes using Gaussian process regression
3. **Top SVG visualization**: 2×2 spatial scatter grid of the top 4 spatially variable genes
4. **Ranked table**: CSV of all tested genes sorted by spatial variability with statistics

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (normalised), `obsm["spatial"]` | `processed.h5ad` |
| Demo | n/a | `--demo` flag | Runs spatial-preprocess demo first |

## Workflow

1. **Load**: Read preprocessed h5ad; verify spatial coordinates exist
2. **Spatial neighbors**: Build spatial connectivity graph via `squidpy.gr.spatial_neighbors()`
3. **Spatial autocorrelation**: Compute Moran's I for all genes via `squidpy.gr.spatial_autocorr(mode="moran")`
4. **Filter & rank**: Filter by FDR-corrected p-value < threshold, sort by I statistic, take top N
5. **Visualize**: 2×2 scatter plot of top 4 SVGs on spatial coordinates
6. **Report**: Write report.md, result.json, tables/svg_results.csv, processed.h5ad, figures, reproducibility bundle

## CLI Reference

```bash
# Standard usage (Moran's I)
python skills/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --output <report_dir>

# Custom parameters
python skills/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --method morans --n-top-genes 30 --fdr-threshold 0.01 --output <dir>

# SpatialDE method (requires SpatialDE package)
python skills/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --method spatialde --output <dir>

# Demo mode
python skills/spatial-genes/spatial_genes.py --demo --output /tmp/svg_demo

# Via SpatialClaw runner
python omicsclaw.py run genes --input <file> --output <dir>
python omicsclaw.py run genes --demo
```

## Example Queries

- "Find spatially variable genes in my data using Moran's I"
- "Use SpatialDE to detect genes with spatial patterns"

## Algorithm / Methodology

### Moran's I (default)

1. **Spatial graph**: `squidpy.gr.spatial_neighbors(n_neighs=6, coord_type="generic")` builds a k-NN spatial graph from `obsm["spatial"]`
2. **Autocorrelation**: `squidpy.gr.spatial_autocorr(adata, mode="moran", n_perms=100, n_jobs=1)` computes Moran's I for every gene
3. **Moran's I range**: −1 (perfect dispersion) to +1 (perfect clustering); 0 = random
4. **Filtering**: Retain genes with `moranI > 0` and `pval_norm < fdr_threshold`
5. **Ranking**: Sort by descending Moran's I statistic

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `morans` | `morans` or `spatialde` |
| `--n-top-genes` | `20` | Number of top SVGs to report |
| `--fdr-threshold` | `0.05` | FDR-corrected p-value cutoff |

### SpatialDE (optional)

1. **Dependency**: Requires `SpatialDE` package (`pip install SpatialDE`)
2. **Test**: Gaussian process regression comparing spatially-aware vs spatially-unaware models
3. **Status**: Stub with dependency check — full implementation in future version

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── top_svg.png
├── tables/
│   └── svg_results.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9 — single-cell/spatial analysis
- `squidpy` >= 1.2 — spatial autocorrelation and neighbor graphs
- `matplotlib` — plotting
- `numpy`, `pandas` — numerics

**Optional**:
- `SpatialDE` — Gaussian process-based SVG detection (graceful degradation without it)

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.
- **Non-destructive**: SVG results stored in `adata.uns`, original data preserved

## Integration with Orchestrator

**Trigger conditions**: 
- Automatically invoked dynamically based on tool metadata and user intent matching.
- Keywords — spatially variable gene, spatial gene, SVG, SpatialDE, SPARK-X, spatial pattern, Moran

**Chaining partners**:
- `spatial-preprocess`: Provides the preprocessed h5ad input
- `spatial-domains`: SVGs often overlap with domain-defining genes
- `spatial-de`: Compare SVGs with cluster-based DE results

## Citations

- [Squidpy](https://squidpy.readthedocs.io/) — spatial autocorrelation (Moran's I)
- [SpatialDE](https://doi.org/10.1038/nmeth.4636) — Svensson et al., *Nature Methods* 2018
- [SPARK-X](https://doi.org/10.1186/s13059-021-02404-0) — Zhu et al., *Genome Biology* 2021
- [Moran's I](https://en.wikipedia.org/wiki/Moran%27s_I) — spatial autocorrelation statistic
