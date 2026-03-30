---
name: sc-preprocessing
description: >-
  Single-cell RNA-seq QC, normalization, HVG selection, PCA, UMAP, and Leiden clustering.
  Supports Scanpy (Python), Seurat LogNormalize (R), and Seurat SCTransform (R) workflows.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, preprocessing, QC, normalization, clustering]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--leiden-resolution"
      - "--max-mt-pct"
      - "--method"
      - "--min-cells"
      - "--min-genes"
      - "--n-neighbors"
      - "--n-pcs"
      - "--n-top-hvg"
    param_hints:
      scanpy:
        priority: "min_genes/max_mt_pct → n_top_hvg → n_pcs"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs", "n_neighbors", "leiden_resolution"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000, n_pcs: 50, n_neighbors: 15, leiden_resolution: 1.0}
        requires: ["count_matrix_in_X"]
        tips:
          - "--method scanpy: Pure Python default path."
          - "--max-mt-pct: Typical PBMC threshold 5-10%, broad tissues often 15-20%."
          - "--n-top-hvg / --n-pcs: Increase for larger, more heterogeneous datasets."
      seurat:
        priority: "min_genes/max_mt_pct → n_top_hvg → n_pcs"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs", "n_neighbors", "leiden_resolution"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000, n_pcs: 50, n_neighbors: 15, leiden_resolution: 1.0}
        requires: ["Rscript", "Seurat", "SingleCellExperiment", "zellkonverter"]
        tips:
          - "--method seurat: Uses the shared R script `omicsclaw/r_scripts/sc_seurat_preprocess.R`."
          - "Best when you want the classic `NormalizeData → FindVariableFeatures → ScaleData` Seurat flow."
          - "Current wrapper expects raw-count-like input and reconstructs a standard AnnData output for downstream OmicsClaw skills."
      sctransform:
        priority: "max_mt_pct → n_top_hvg → n_pcs"
        params: ["min_genes", "min_cells", "max_mt_pct", "n_top_hvg", "n_pcs", "n_neighbors", "leiden_resolution"]
        defaults: {min_genes: 200, min_cells: 3, max_mt_pct: 20.0, n_top_hvg: 2000, n_pcs: 50, n_neighbors: 15, leiden_resolution: 1.0}
        requires: ["Rscript", "Seurat", "SingleCellExperiment", "zellkonverter", "sctransform"]
        tips:
          - "--method sctransform: Seurat SCTransform branch for UMI data."
          - "Use when technical noise or sequencing-depth effects are strong."
          - "This path still emits a standard OmicsClaw AnnData output plus the same report/reproducibility bundle."
    legacy_aliases: [sc-preprocess]
    saves_h5ad: true
    requires_preprocessed: false
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

You are **SC Preprocessing**, the foundation skill for single-cell analysis in OmicsClaw. Your role is to load scRNA-seq count data, perform quality control filtering, normalize expression, compute embeddings, and generate a downstream-ready AnnData object for clustering and later annotation or integration.

## Why This Exists

- **Without it**: Users write 30+ lines of boilerplate Scanpy code per dataset
- **With it**: One command handles QC → normalize → HVG → PCA → UMAP → Leiden
- **Why OmicsClaw**: Standardised preprocessing ensures reproducibility across downstream single-cell skills, with a common output contract across Python and R-backed workflows

## Core Capabilities

1. **QC filtering**: min genes/cells, mitochondrial percentage thresholds
2. **Multiple preprocessing backends**: Scanpy default, Seurat LogNormalize, and Seurat SCTransform
3. **HVG selection**: Seurat-style or SCTransform-driven variable feature detection
4. **Embedding**: PCA → neighbors → UMAP
5. **Clustering**: Graph-based clustering with a unified resolution control
6. **Reusable outputs**: `processed.h5ad`, report, figures, tables, README guide, and notebook in standard `oc run` executions

## Input Formats

| Format | Extension | Required | Example |
|--------|-----------|----------|---------|
| AnnData | `.h5ad` | Raw-count-like matrix in `X` (preferred), or recoverable counts in `layers["counts"]` / `adata.raw` | `raw_sc.h5ad` |
| Demo | n/a | `--demo` flag | Built-in PBMC3k |

> **Current wrapper behavior**: The present CLI/script implementation reads `.h5ad`
> inputs directly. If your starting point is 10x H5 or MTX, convert it to `.h5ad`
> first, then run this skill.

## Post-Preprocess Data Convention

After this skill completes, the processed object typically contains:

```text
adata.X                        # normalized expression used by the selected workflow
adata.layers["counts"]         # preserved raw-count-like matrix
adata.var["highly_variable"]   # HVG mask
adata.obsm["X_pca"]            # PCA embedding
adata.obsm["X_umap"]           # UMAP embedding
adata.obsp["connectivities"]   # neighbor graph
adata.obsp["distances"]        # neighbor distances
adata.obs["leiden"]            # OmicsClaw-compatible cluster labels
adata.obs["seurat_clusters"]   # Seurat cluster labels when an R-backed method is used
```

## Workflow

1. **Load**: Read scRNA-seq count data from `.h5ad` or demo data.
2. **QC**: Compute cell-level library size, detected genes, and mitochondrial fraction.
3. **Filter**: Remove low-quality cells and rarely detected genes.
4. **Branch by method**:
   - `scanpy`: `normalize_total → log1p → highly_variable_genes → scale`
   - `seurat`: `CreateSeuratObject → NormalizeData → FindVariableFeatures → ScaleData`
   - `sctransform`: `CreateSeuratObject → SCTransform`
5. **Embed and cluster**: Run PCA, build the neighbor graph, compute UMAP, and run clustering using the shared resolution parameter.
6. **Report and export**: Save figures, tables, `processed.h5ad`, `result.json`, and reproducibility artifacts.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input <data.h5ad> --method scanpy --output <dir>
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input <data.h5ad> --method seurat --output <dir>
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input <data.h5ad> --method sctransform --output <dir>
python omicsclaw.py run sc-preprocessing --demo
```

Every successful standard `oc run` execution also writes a top-level `README.md`
and `reproducibility/analysis_notebook.ipynb` so users can inspect the run, trace parameters, and rerun code more easily.

## Algorithm / Methodology

### Common QC and Filtering Contract

All three backends share the same high-level preprocessing contract:

1. **Count-oriented input**: The skill expects raw-count-like expression for best results. For R-backed workflows, OmicsClaw exports count-like data into `X` before calling the shared R script.
2. **Cell filtering**: `min_genes` removes near-empty droplets or cells with very low complexity.
3. **Gene filtering**: `min_cells` removes genes detected in too few cells to be informative.
4. **Mitochondrial QC**: `max_mt_pct` removes stressed or dying cells using `MT-` or `mt-` patterns.
5. **Embedding contract**: Every backend returns PCA, UMAP, neighbor graph, and cluster labels in a standard AnnData structure.

> **Scope boundary**: This skill implements the preprocessing subset of the broader Seurat best-practice workflow in `knowledge_base/scrnaseq-seurat-core-analysis`. Ambient RNA correction, doublet detection, batch integration, annotation, and DE remain separate concerns in OmicsClaw.

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

### Seurat LogNormalize (R)

**Goal:** Mirror the classic Seurat preprocess path described in `knowledge_base/scrnaseq-seurat-core-analysis` while keeping the OmicsClaw output contract consistent.

**Current OmicsClaw implementation**:
- Python writes a temporary `.h5ad` export and calls `omicsclaw/r_scripts/sc_seurat_preprocess.R`.
- The shared R script reads the data with `zellkonverter`, runs Seurat preprocessing, then writes `obs.csv`, `pca.csv`, `umap.csv`, `hvg.csv`, and normalized expression back to disk.
- Python reconstructs a downstream-ready AnnData object, preserving count-like data in `layers["counts"]` and mirroring Seurat clusters into `obs["leiden"]` for downstream compatibility.

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

#### Recommended Seurat Preprocess Flow In OmicsClaw

This skill currently implements the following Seurat preprocess subset from the knowledge base:

1. **Load counts into Seurat**: `CreateSeuratObject(counts=..., min.cells=min_cells, min.features=min_genes)`
2. **Compute mitochondrial percentage**: `PercentageFeatureSet(..., pattern='^MT-' or '^mt-')`
3. **Filter cells**: keep cells passing `nFeature_RNA >= min_genes` and `percent.mt <= max_mt_pct`
4. **Normalize**: `NormalizeData()`
5. **Select HVGs**: `FindVariableFeatures(selection.method='vst', nfeatures=n_top_hvg)`
6. **Scale**: `ScaleData()` on the selected features
7. **Dimensionality reduction**: `RunPCA(npcs=n_pcs)`
8. **Graph building**: `FindNeighbors(dims=1:n_pcs, k.param=n_neighbors)`
9. **Clustering**: `FindClusters(resolution=leiden_resolution)`
10. **Visualization**: `RunUMAP(dims=1:n_pcs)`

**What this intentionally does not include yet**:
- SoupX ambient RNA correction
- MAD-based adaptive QC
- DoubletFinder / scDblFinder
- Multi-batch integration
- Annotation and pseudobulk DE

Those steps belong to the broader Seurat core-analysis knowledge base and separate OmicsClaw skills.

### Seurat SCTransform (R)

**Goal:** Provide the Seurat v5-style SCTransform branch for UMI data when users want model-based normalization instead of classic LogNormalize.

**Why use it**:
- Better control of sequencing-depth effects on many UMI datasets
- Variable feature selection is integrated into the normalization step
- Often a stronger default for heterogeneous scRNA-seq data than simple log-normalization

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

#### Recommended SCTransform Flow In OmicsClaw

1. **Load and QC**: same input loading and mitochondrial filtering as the Seurat LogNormalize branch
2. **Variance-stabilizing normalization**: `SCTransform(variable.features.n=n_top_hvg, vars.to.regress='percent.mt')`
3. **PCA**: `RunPCA(npcs=n_pcs)` on the SCT assay
4. **Neighbors and clusters**: `FindNeighbors(..., k.param=n_neighbors)` and `FindClusters(resolution=leiden_resolution)`
5. **UMAP**: `RunUMAP(...)`
6. **Return to OmicsClaw**: export normalized matrix, embeddings, cluster labels, and HVGs back into a standard AnnData object

> **Current wrapper behavior**: The R backend uses the same shared script `omicsclaw/r_scripts/sc_seurat_preprocess.R`, switching behavior via `workflow = 'sctransform'`.

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
| Backend | Python | R via `sc_seurat_preprocess.R` | R via `sc_seurat_preprocess.R` |
| Output contract | Standard AnnData | Standard AnnData reconstructed from R outputs | Standard AnnData reconstructed from R outputs |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--min-genes` | `200` | Min genes per cell |
| `--min-cells` | `3` | Min cells per gene |
| `--max-mt-pct` | `20.0` | Max mitochondrial % |
| `--method` | `scanpy` | `scanpy`, `seurat`, or `sctransform` |
| `--n-top-hvg` | `2000` | Number of HVGs |
| `--n-pcs` | `50` | PCA components |
| `--n-neighbors` | `15` | Neighbor graph size |
| `--leiden-resolution` | `1.0` | Leiden resolution |

## Runtime Notes

- `--method scanpy` is the default Python workflow.
- `--method seurat` runs the Seurat LogNormalize path via the shared R script `omicsclaw/r_scripts/sc_seurat_preprocess.R`.
- `--method sctransform` runs the Seurat SCTransform path via the same shared R script with a different workflow flag.
- R-backed modes require `Rscript` plus `Seurat`, `SingleCellExperiment`, and `zellkonverter`. `sctransform` additionally requires the R package `sctransform`.
- If an input already contains normalized `X`, the R-backed methods still work best when OmicsClaw can recover raw-count-like data from `layers["counts"]` or `adata.raw`.
- Standard `oc run` outputs include `README.md` and `reproducibility/analysis_notebook.ipynb`; direct script execution does not add those wrappers automatically.

## Example Queries

- "Run single cell preprocessing on this h5ad count matrix"
- "Perform QC and clustering: filter out cells with >20% mito"
- "Normalize and cluster this PBMC count matrix using Scanpy"

## Output Structure

```text
output_dir/
├── README.md                     # standard `oc run` wrapper only
├── report.md
├── processed.h5ad
├── result.json
├── figures/
│   ├── qc_violin.png
│   ├── hvg_plot.png             # optional, mainly Scanpy path
│   ├── pca_variance.png         # optional when PCA variance metadata is available
│   └── umap_clusters.png
├── tables/
│   └── cluster_summary.csv
└── reproducibility/
    ├── analysis_notebook.ipynb  # standard `oc run` wrapper only
    └── commands.sh
```

### Output Files Explained

- `README.md`: Human-friendly entry point for standard `oc run` outputs.
- `report.md`: Narrative summary of method, QC, HVGs, and clusters.
- `result.json`: Machine-readable summary and parameter record.
- `processed.h5ad`: Downstream-ready AnnData for annotation, integration, and marker analysis.
- `figures/qc_violin.png`: QC metric overview when QC columns are available.
- `figures/pca_variance.png`: PCA variance summary when available.
- `figures/umap_clusters.png`: UMAP colored by cluster labels.
- `tables/cluster_summary.csv`: Cluster sizes and proportions.
- `reproducibility/analysis_notebook.ipynb`: Auto-generated notebook in standard `oc run` outputs.
- `reproducibility/commands.sh`: Minimal rerun command.

## Version Compatibility

Reference examples tested with: scanpy 1.10+, numpy 1.26+, matplotlib 3.8+

## Dependencies

**Required Python stack**: scanpy >= 1.9, anndata >= 0.11, numpy, pandas, matplotlib

**R stack for Seurat-backed methods**:
- `Seurat`
- `SingleCellExperiment`
- `zellkonverter`
- `sctransform` for `--method sctransform`

## Citations

- [Scanpy](https://scanpy.readthedocs.io/) — Wolf et al., Genome Biology 2018
- [Seurat](https://satijalab.org/seurat/) — Hao et al., Cell 2021
- [SCTransform](https://doi.org/10.1186/s13059-019-1874-1) — Hafemeister & Satija, Genome Biology 2019
- [Leiden algorithm](https://www.nature.com/articles/s41598-019-41695-z) — Traag et al., 2019

## Safety

- **Local-first**: Strict offline processing without transmitting sample profiles.
- **Disclaimer**: Reproducible OmicsClaw reports clearly state parameter origins.
- **Audit trail**: Logging traces down to seed integers used in embedding.
- **Transparent behavior**: The documented Seurat flows reflect the current shared R-script implementation, not an idealized future workflow beyond what the wrapper executes today.

## Integration with Orchestrator

**Trigger conditions**:
- "preprocess", "QA/QC", "Scanpy pipeline", "Seurat preprocess", "filter normalize"

**Chaining partners**:
- `sc-doublet` — Doublet detection before preprocessing
- `sc-annotate` — Cell type annotation after clustering
- `sc-integrate` — Batch integration for multi-sample data
