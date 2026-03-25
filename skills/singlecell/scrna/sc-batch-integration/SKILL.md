---
name: sc-batch-integration
description: >-
  Batch integration for multi-sample scRNA-seq using Harmony, scVI, Seurat CCA/RPCA,
  BBKNN, and fastMNN. Remove technical variation while preserving biological differences.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, batch-integration, Harmony, scVI, Seurat, BBKNN]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🔗"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - batch integration
      - batch effect
      - Harmony
      - scVI
      - BBKNN
      - merge samples
---

# 🔗 Single-Cell Batch Integration

Integrate multiple scRNA-seq datasets to remove batch effects while preserving biological variation.

## Why This Exists

- **Without it**: Multi-sample analysis is dominated by technical batch effects
- **With it**: Corrected embedding space where clusters reflect biology, not batches
- **Why OmicsClaw**: Automated integration with method selection and evaluation metrics

## Tool Comparison

| Tool | Speed | Scalability | Best For |
|------|-------|-------------|----------|
| Harmony | Fast | Good | Quick integration, most use cases |
| scVI | Moderate | Excellent | Large datasets, deep learning |
| Seurat CCA/RPCA | Moderate | Good | Conserved biology across batches |
| fastMNN | Fast | Good | MNN-based correction |
| BBKNN | Fast | Good | Lightweight, k-NN correction |

## Workflow

1. **Calculate**: Prepare modalities and normalize batch representations.
2. **Execute**: Run chosen integration mechanism across sample blocks.
3. **Assess**: Quantify batch mixing versus bio-preservation.
4. **Generate**: Save corrected matrices and compute UMAP graph.
5. **Report**: Synthesize report with mixing scoring metadata.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py \
  --input <merged.h5ad> --method harmony --output <dir>
python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py \
  --input <merged.h5ad> --method seurat_rpca --batch-key sample_id --output <dir>
python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py \
  --input <merged.h5ad> --method fastmnn --batch-key sample_id --output <dir>
python omicsclaw.py run sc-batch-integration --demo
```

## Algorithm / Methodology

### Harmony (Python — Scanpy)

**Goal:** Remove batch effects by iteratively correcting PCA embeddings.

```python
import scanpy as sc
import scanpy.external as sce

adata = sc.read_h5ad('merged.h5ad')

# Standard preprocessing
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata, batch_key='batch')
adata = adata[:, adata.var.highly_variable]
sc.pp.scale(adata)
sc.tl.pca(adata)

# Run Harmony
sce.pp.harmony_integrate(adata, key='batch')

# Use corrected embedding
sc.pp.neighbors(adata, use_rep='X_pca_harmony')
sc.tl.umap(adata)
sc.tl.leiden(adata)
```

### Harmony (R — Seurat)

```r
library(Seurat)
library(harmony)

merged <- merge(sample1, y = list(sample2, sample3), add.cell.ids = c('S1', 'S2', 'S3'))
merged <- NormalizeData(merged)
merged <- FindVariableFeatures(merged)
merged <- ScaleData(merged)
merged <- RunPCA(merged)

# Run Harmony on PCA embeddings
merged <- RunHarmony(merged, group.by.vars = 'orig.ident', dims.use = 1:30)

# Use harmony embeddings for downstream
merged <- RunUMAP(merged, reduction = 'harmony', dims = 1:30)
merged <- FindNeighbors(merged, reduction = 'harmony', dims = 1:30)
merged <- FindClusters(merged, resolution = 0.5)
```

### scVI (Python)

**Goal:** Integrate batches using a deep generative model that learns a shared latent space.

```python
import scvi
import scanpy as sc

adata = sc.read_h5ad('merged.h5ad')

scvi.model.SCVI.setup_anndata(adata, batch_key='batch')
model = scvi.model.SCVI(adata, n_latent=30, n_layers=2)
model.train(max_epochs=100, early_stopping=True)

adata.obsm['X_scVI'] = model.get_latent_representation()

sc.pp.neighbors(adata, use_rep='X_scVI')
sc.tl.umap(adata)
sc.tl.leiden(adata)
```

#### scANVI (with Cell Type Labels)

```python
scvi.model.SCANVI.setup_anndata(adata, batch_key='batch', labels_key='cell_type',
                                 unlabeled_category='Unknown')
model = scvi.model.SCANVI(adata, n_latent=30)
model.train(max_epochs=100)

adata.obs['predicted_type'] = model.predict()
```

### Seurat CCA Integration (R)

```r
library(Seurat)

obj_list <- SplitObject(merged, split.by = 'batch')
obj_list <- lapply(obj_list, function(x) {
    x <- NormalizeData(x)
    x <- FindVariableFeatures(x, nfeatures = 2000)
    return(x)
})

anchors <- FindIntegrationAnchors(object.list = obj_list, dims = 1:30)
integrated <- IntegrateData(anchorset = anchors, dims = 1:30)

DefaultAssay(integrated) <- 'integrated'
integrated <- ScaleData(integrated)
integrated <- RunPCA(integrated)
integrated <- RunUMAP(integrated, dims = 1:30)
```

#### Seurat RPCA (Faster for Large Datasets)

```r
anchors <- FindIntegrationAnchors(object.list = obj_list, dims = 1:30, reduction = 'rpca')
integrated <- IntegrateData(anchorset = anchors, dims = 1:30)
```

### Evaluate Integration

#### Mixing Metrics (R)

```r
library(lisi)
lisi_scores <- compute_lisi(Embeddings(merged, 'harmony'),
                            merged@meta.data, c('batch', 'cell_type'))
mean(lisi_scores$batch)      # Want high (batches mixed)
mean(lisi_scores$cell_type)  # Want low (types preserved)
```

#### Silhouette Score (Python)

```python
from sklearn.metrics import silhouette_score

batch_sil = silhouette_score(adata.obsm['X_scVI'], adata.obs['batch'])      # Want low
celltype_sil = silhouette_score(adata.obsm['X_scVI'], adata.obs['cell_type'])  # Want high
```

## When to Use Each Method

| Scenario | Recommended |
|----------|-------------|
| Quick integration, most cases | Harmony |
| Large datasets (>500k cells) | scVI or Harmony |
| Strong batch effects | scVI |
| Reference mapping | Seurat anchors or scANVI |
| Preserving rare populations | fastMNN |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `harmony` | `harmony`, `scvi`, `scanvi`, `bbknn`, `scanorama`, `fastmnn`, `seurat_cca`, `seurat_rpca` |
| `--batch-key` | `batch` | Column with batch labels |
| `--n-epochs` | none | Training epochs for `scvi`/`scanvi` |
| `--no-gpu` | false | Disable GPU for deep learning methods |

## Example Queries

- "Run Harmony integration on my cell clusters"
- "Use scVI to eliminate technical batch effects"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   └── summary_plot.png
├── tables/
│   └── metrics.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Version Compatibility

Reference examples tested with: scanpy 1.10+, scvi-tools 1.1+, anndata 0.10+

## Dependencies

**Required**: scanpy >= 1.9, anndata
**Optional**: scvi-tools, harmonypy, bbknn, scanorama, `rpy2` + `anndata2ri` + R packages `Seurat`, `batchelor`, and `harmony`

## Runtime Notes

- `fastmnn`, `seurat_cca`, and `seurat_rpca` are implemented through the shared R bridge.
- `harmony` in this skill uses the Python `harmony-pytorch` path by default; the README installer also includes the R `harmony` package for Seurat workflows.

## Citations

- [Harmony](https://doi.org/10.1038/s41592-019-0619-0) — Korsunsky et al., Nature Methods 2019
- [scVI](https://doi.org/10.1038/s41592-018-0229-2) — Lopez et al., Nature Methods 2018
- [Seurat v3](https://doi.org/10.1016/j.cell.2019.05.031) — Stuart et al., Cell 2019
- [BBKNN](https://doi.org/10.1093/bioinformatics/btz625) — Polanski et al., Bioinformatics 2020

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `sc-preprocess` — QC before integration
- `sc-annotate` — Annotation after integration
- `sc-doublet` — Doublet removal before integration
