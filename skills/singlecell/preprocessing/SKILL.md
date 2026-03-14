---
name: sc-preprocess
description: >-
  Single-cell RNA-seq QC, normalization, HVG selection, PCA, UMAP, and Leiden clustering.
  Supports both Scanpy (Python) and Seurat (R) workflows.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, preprocessing, QC, normalization, clustering]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧫"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - single cell preprocess
      - scRNA preprocessing
      - QC filter normalize
      - clustering UMAP PCA
---

# 🧫 Single-Cell Preprocessing

You are **SC Preprocessing**, the foundation skill for single-cell analysis in OmicsClaw. Your role is to load scRNA-seq data, perform quality control filtering, normalization, and clustering.

## Why This Exists

- **Without it**: Users write 30+ lines of boilerplate Scanpy code per dataset
- **With it**: One command handles QC → normalize → HVG → PCA → UMAP → Leiden
- **Why OmicsClaw**: Standardised preprocessing ensures reproducibility across downstream single-cell skills

## Core Capabilities

1. **QC filtering**: min genes/cells, mitochondrial percentage thresholds
2. **Normalization**: Library-size normalization + log1p (or SCTransform in R)
3. **HVG selection**: Seurat-flavored highly variable gene detection
4. **Embedding**: PCA → neighbors → UMAP
5. **Clustering**: Leiden community detection
6. **Confounder regression**: Optional regress-out of technical variation

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| AnnData | `.h5ad` | Count matrix in X | `raw_sc.h5ad` |
| 10x H5 | `.h5` | Filtered feature matrix | `filtered_feature_bc_matrix.h5` |
| 10x MTX | directory | `matrix.mtx.gz` + barcodes + features | `filtered_feature_bc_matrix/` |
| Demo | n/a | `--demo` flag | Built-in PBMC3k |

## Workflow

1. **Calculate Metrics**: Compute per-cell UMI counts, features, and mitochondrial percentage.
2. **Filter**: Remove low-quality cells and uninformative genes.
3. **Normalize**: Library size normalization and log-transformation.
4. **Embed & Cluster**: Compute PCA, neighborhood graph, UMAP, and Leiden communities.
5. **Report**: Produce `report.md` detailing cell drop-out rates and visualization plots.

## CLI Reference

```bash
python skills/singlecell/preprocessing/sc_preprocess.py \
  --input <data.h5ad> --output <dir>
python skills/singlecell/preprocessing/sc_preprocess.py --demo --output /tmp/demo
python omicsclaw.py run sc-preprocess --demo
```

## Algorithm / Methodology

### Scanpy (Python)

**Goal:** Preprocess scRNA-seq data through QC filtering, normalization, and feature selection using Scanpy.

**Approach:** Calculate per-cell quality metrics, filter low-quality cells/genes, normalize library sizes, identify highly variable genes, and scale for downstream analysis.

#### Calculate QC Metrics

```python
import scanpy as sc
import numpy as np

# Calculate mitochondrial gene percentage
adata.var['mt'] = adata.var_names.str.startswith('MT-')
sc.pp.calculate_qc_metrics(adata, qc_vars=['mt'], percent_top=None, log1p=False, inplace=True)

# Key metrics added to adata.obs:
# - n_genes_by_counts: genes detected per cell
# - total_counts: total UMI counts per cell
# - pct_counts_mt: percentage mitochondrial
```

#### Visualize QC Metrics

```python
import matplotlib.pyplot as plt

sc.pl.violin(adata, ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'], jitter=0.4, multi_panel=True)
sc.pl.scatter(adata, x='total_counts', y='pct_counts_mt')
sc.pl.scatter(adata, x='total_counts', y='n_genes_by_counts')
```

#### Filter Cells and Genes

```python
# Filter cells by QC metrics
sc.pp.filter_cells(adata, min_genes=200)
sc.pp.filter_cells(adata, max_genes=5000)

# Filter by mitochondrial percentage
adata = adata[adata.obs['pct_counts_mt'] < 20, :].copy()

# Filter genes
sc.pp.filter_genes(adata, min_cells=3)

print(f'After filtering: {adata.n_obs} cells, {adata.n_vars} genes')
```

#### Normalization

```python
# Store raw counts before normalization
adata.raw = adata.copy()
adata.layers['counts'] = adata.X.copy()

# Library size normalization (normalize to 10,000 counts per cell)
sc.pp.normalize_total(adata, target_sum=1e4)

# Log transform
sc.pp.log1p(adata)
```

#### Highly Variable Genes

```python
# Identify highly variable genes (default: top 2000)
sc.pp.highly_variable_genes(adata, n_top_genes=2000, flavor='seurat_v3', layer='counts')

# Visualize
sc.pl.highly_variable_genes(adata)

# Check results
print(f'Highly variable genes: {adata.var.highly_variable.sum()}')
```

#### Scaling and Embedding

```python
# Subset to HVGs
adata = adata[:, adata.var.highly_variable].copy()

# Scale to unit variance and zero mean
sc.pp.scale(adata, max_value=10)

# PCA, neighbors, UMAP, clustering
sc.tl.pca(adata, n_comps=50)
sc.pp.neighbors(adata)
sc.tl.umap(adata)
sc.tl.leiden(adata, resolution=1.0)
```

#### Regress Out Confounders (Optional)

```python
# Regress out unwanted variation (e.g., cell cycle, mitochondrial)
sc.pp.regress_out(adata, ['total_counts', 'pct_counts_mt'])
```

#### Complete Pipeline

```python
import scanpy as sc

adata = sc.read_10x_mtx('filtered_feature_bc_matrix/')

# QC
adata.var['mt'] = adata.var_names.str.startswith('MT-')
sc.pp.calculate_qc_metrics(adata, qc_vars=['mt'], inplace=True)

# Filter
sc.pp.filter_cells(adata, min_genes=200)
sc.pp.filter_genes(adata, min_cells=3)
adata = adata[adata.obs['pct_counts_mt'] < 20, :].copy()

# Store raw
adata.raw = adata.copy()

# Normalize
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

# HVGs
sc.pp.highly_variable_genes(adata, n_top_genes=2000)

# Scale
adata = adata[:, adata.var.highly_variable].copy()
sc.pp.scale(adata, max_value=10)
```

### Seurat (R)

**Goal:** Preprocess scRNA-seq data through QC filtering, normalization, and feature selection using Seurat.

#### Standard Log Normalization Pipeline

```r
library(Seurat)

counts <- Read10X(data.dir = 'filtered_feature_bc_matrix/')
seurat_obj <- CreateSeuratObject(counts = counts, min.cells = 3, min.features = 200)

# QC
seurat_obj[['percent.mt']] <- PercentageFeatureSet(seurat_obj, pattern = '^MT-')

# Filter
seurat_obj <- subset(seurat_obj,
    subset = nFeature_RNA > 200 & nFeature_RNA < 5000 & percent.mt < 20)

# Normalize
seurat_obj <- NormalizeData(seurat_obj)

# HVGs
seurat_obj <- FindVariableFeatures(seurat_obj, nfeatures = 2000)

# Scale
seurat_obj <- ScaleData(seurat_obj)
```

#### SCTransform Pipeline (Recommended)

```r
library(Seurat)

counts <- Read10X(data.dir = 'filtered_feature_bc_matrix/')
seurat_obj <- CreateSeuratObject(counts = counts, min.cells = 3, min.features = 200)

# QC
seurat_obj[['percent.mt']] <- PercentageFeatureSet(seurat_obj, pattern = '^MT-')

# Filter
seurat_obj <- subset(seurat_obj,
    subset = nFeature_RNA > 200 & nFeature_RNA < 5000 & percent.mt < 20)

# SCTransform (does normalization, HVG, and scaling)
seurat_obj <- SCTransform(seurat_obj, vars.to.regress = 'percent.mt', verbose = FALSE)
```

## QC Thresholds Reference

| Metric | Typical Range | Notes |
|--------|---------------|-------|
| min_genes | 200-500 | Remove empty droplets |
| max_genes | 2500-5000 | Remove doublets |
| max_mt | 5-20% | Remove dying cells (tissue-dependent) |
| min_cells | 3-10 | Remove rarely detected genes |

## Method Comparison

| Step | Scanpy | Seurat (Standard) | Seurat (SCTransform) |
|------|--------|-------------------|---------------------|
| Normalize | `normalize_total` + `log1p` | `NormalizeData` | `SCTransform` |
| HVGs | `highly_variable_genes` | `FindVariableFeatures` | (included) |
| Scale | `scale` | `ScaleData` | (included) |
| Regress | `regress_out` | `ScaleData(vars.to.regress)` | `SCTransform(vars.to.regress)` |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--min-genes` | `200` | Min genes per cell |
| `--min-cells` | `3` | Min cells per gene |
| `--max-mt-pct` | `20.0` | Max mitochondrial % |
| `--n-top-hvg` | `2000` | Number of HVGs |
| `--n-pcs` | `50` | PCA components |
| `--leiden-resolution` | `1.0` | Leiden resolution |

## Example Queries

- "Run single cell preprocessing on this 10x h5 data"
- "Perform QC and clustering: filter out cells with >20% mito"
- "Normalize and cluster this PBMC count matrix using Scanpy"

## Output Structure

```
output_dir/
├── report.md
├── processed.h5ad
├── result.json
├── figures/
│   ├── qc_violin.png
│   ├── hvg_plot.png
│   ├── umap_clusters.png
│   └── umap_genes.png
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Version Compatibility

Reference examples tested with: scanpy 1.10+, numpy 1.26+, matplotlib 3.8+

## Dependencies

**Required**: scanpy >= 1.9, anndata >= 0.11, numpy, pandas, matplotlib

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) — Wolf et al., Genome Biology 2018
- [Seurat](https://satijalab.org/seurat/) — Hao et al., Cell 2021
- [SCTransform](https://doi.org/10.1186/s13059-019-1874-1) — Hafemeister & Satija, Genome Biology 2019
- [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) — Traag et al., 2019

## Safety

- **Local-first**: Strict offline processing without transmitting sample profiles.
- **Disclaimer**: Reproducible OmicsClaw reports clearly state parameter origins.
- **Audit trail**: Logging traces down to seed integers used in embedding.

## Integration with Orchestrator

**Trigger conditions**:
- "preprocess", "QA/QC", "Scanpy pipeline", "filter normalize"

**Chaining partners**:
- `sc-doublet` — Doublet detection before preprocessing
- `sc-annotate` — Cell type annotation after clustering
- `sc-integrate` — Batch integration for multi-sample data
