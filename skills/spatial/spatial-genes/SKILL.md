---
name: spatial-genes
description: >-
  Find genes with spatially variable expression patterns using Moran's I,
  SpatialDE, SPARK-X, or FlashS. Identifies genes whose expression is non-randomly
  distributed across tissue coordinates.
version: 0.2.0
author: SpatialClaw
license: MIT
tags: [spatial, SVG, spatially-variable-genes, morans, spatialde, sparkx, flashs]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--fdr-threshold"
      - "--method"
      - "--n-top-genes"
    legacy_aliases: [genes]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧭"
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
2. **SpatialDE**: Gaussian process regression via SpatialDE2 (identifies spatial patterns)
3. **SPARK-X**: Non-parametric kernel test via SPARK-X in R (requires R installation)
4. **FlashS**: Randomized kernel approximation (Python native, fast on large datasets)
5. **Top SVG visualization**: 2×2 spatial scatter grid of the top 4 spatially variable genes
6. **Ranked table**: CSV of all tested genes sorted by spatial variability with statistics

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X` (normalised), `layers["counts"]` (raw), `obsm["spatial"]` | `processed.h5ad` |
| Demo | n/a | `--demo` flag | Runs spatial-preprocess demo first |

### Input Matrix Convention

Different SVG methods have different statistical assumptions. The skill automatically selects the correct input matrix per method:

| Method | Input Matrix | Rationale |
|--------|-------------|-----------|
| `morans` | `adata.X` (log-normalized) | Squidpy `spatial_autocorr` computes autocorrelation on continuous expression values; not a count-distribution model |
| `spatialde` | `adata.layers["counts"]` (raw) | NaiveDE.stabilize() applies its own variance-stabilizing transform; feeding already-normalized data breaks assumptions |
| `sparkx` | `adata.layers["counts"]` (raw) | SPARK-X directly inputs the raw count matrix for kernel-based testing |
| `flashs` | `adata.layers["counts"]` (raw) | FlashS exploits sparsity and count structure (binary presence + rank + count) |

**Data layout requirement**: Preprocessing must store raw counts before normalization:

```python
adata.layers["counts"] = adata.X.copy()   # before normalize_total + log1p
adata.X = lognorm_expr                     # after normalize_total + log1p
```

If `layers["counts"]` is missing, the skill will fall back to `adata.raw` (if available) or `adata.X` with a warning.

## Workflow

1. **Load**: Read preprocessed h5ad; verify spatial coordinates exist
2. **Spatial neighbors**: Build spatial connectivity graph via `squidpy.gr.spatial_neighbors()`
3. **Spatial autocorrelation**: Compute Moran's I for all genes via `squidpy.gr.spatial_autocorr(mode="moran")`
4. **Filter & rank**: Filter by FDR-corrected p-value < threshold, sort by I statistic, take top N
5. **Visualize**: 2×2 scatter plot of top 4 SVGs on spatial coordinates
6. **Report**: Write report.md, result.json, tables/svg_results.csv, processed.h5ad, figures, reproducibility bundle

## CLI Reference

```bash
# Standard usage (Moran's I, default)
python skills/spatial/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --output <report_dir>

# Custom parameters
python skills/spatial/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --method morans --n-top-genes 30 --fdr-threshold 0.01 --output <dir>

# SpatialDE method
python skills/spatial/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --method spatialde --output <dir>

# SPARK-X method (requires R + SPARK package)
python skills/spatial/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --method sparkx --output <dir>

# FlashS method (fast on large data)
python skills/spatial/spatial-genes/spatial_genes.py \
  --input <processed.h5ad> --method flashs --output <dir>

# Demo mode
python skills/spatial/spatial-genes/spatial_genes.py --demo --output /tmp/svg_demo

# Via CLI (using 'oc' short alias or 'python omicsclaw.py run')
oc run spatial-svg-detection --input <file> --output <dir>
oc run spatial-svg-detection --demo
```

## Example Queries

- "Find spatially variable genes in my data using Moran's I"
- "Use SpatialDE to detect genes with spatial patterns"

## Algorithm / Methodology

### Moran's I (default)

1. **Input**: `adata.X` (log-normalized expression)
2. **Spatial graph**: `squidpy.gr.spatial_neighbors(n_neighs=6, coord_type="generic")` builds a k-NN spatial graph from `obsm["spatial"]`
3. **Autocorrelation**: `squidpy.gr.spatial_autocorr(adata, mode="moran", n_perms=100, n_jobs=1)` computes Moran's I for every gene
4. **Moran's I range**: -1 (perfect dispersion) to +1 (perfect clustering); 0 = random
5. **Filtering**: Retain genes with `moranI > 0` and `pval_norm < fdr_threshold`
6. **Ranking**: Sort by descending Moran's I statistic

**Key parameters**:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `morans` | `morans`, `spatialde`, `sparkx`, or `flashs` |
| `--n-top-genes` | `20` | Number of top SVGs to report |
| `--fdr-threshold` | `0.05` | FDR-corrected p-value cutoff |
| `--n-neighs` | `6` | Number of spatial neighbors for graph |
| `--n-perms` | `100` | Number of permutations for p-value |

### SpatialDE

1. **Input**: `adata.layers["counts"]` (raw counts)
2. **Dependency**: Requires `SpatialDE` + `NaiveDE` packages
3. **Preprocessing**: NaiveDE.stabilize() applies variance-stabilizing transform on raw counts, then regresses out total counts
4. **Test**: Gaussian process regression comparing spatially-aware vs spatially-unaware models
5. **Output**: Genes ranked by likelihood ratio test

### SPARK-X

1. **Input**: `adata.layers["counts"]` (raw counts)
2. **Dependency**: Requires R + SPARK R package
3. **Test**: Non-parametric kernel-based test directly on count matrix
4. **Advantage**: Robust to non-linear spatial patterns

### FlashS

1. **Input**: `adata.layers["counts"]` (raw counts)
2. **Dependency**: Python native (no R required)
3. **Method**: Randomized kernel approximation exploiting sparsity and count structure
4. **Advantage**: Fast on large datasets (>10k spots)

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
    ├── requirements.txt
    └── checksums.sha256
```

## Dependencies

**Required (Python)**:
- `scanpy` >= 1.9 — single-cell/spatial analysis
- `squidpy` >= 1.2 — spatial autocorrelation and neighbor graphs
- `matplotlib` — plotting
- `numpy`, `pandas` — numerics

**Optional (Python)**:
- `SpatialDE` & `NaiveDE` — Gaussian process-based SVG detection
- `flashs` — FlashS randomized kernel approximation

**Optional (R Environment / Subprocess)**:
- R system installation
- `SPARK` (R package) — SPARK-X kernel test

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
- [FlashS](https://github.com/cafferychen777/FlashS) — frequency-domain kernel testing for SVGs
- [Moran's I](https://en.wikipedia.org/wiki/Moran%27s_I) — spatial autocorrelation statistic
