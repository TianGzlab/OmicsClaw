---
name: sc-multiome
description: >-
  Multi-omics integration for single-cell data (CITE-seq, 10X Multiome, SHARE-seq).
  Weighted Nearest Neighbor (WNN) analysis, MOFA+, and muon/MuData workflows.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, multiome, CITE-seq, WNN, MOFA, multi-modal]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧩"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - multiome
      - CITE-seq
      - multi-modal
      - WNN
      - MOFA
      - RNA ATAC
---

# 🧩 Single-Cell Multi-Omics Integration

Jointly analyze multiple modalities (RNA + protein, RNA + ATAC) measured in the same cells.

## Common Modalities

| Technology | Modalities | Package |
|------------|------------|---------|
| CITE-seq | RNA + surface proteins (ADT) | Seurat |
| 10X Multiome | RNA + ATAC | Seurat, Signac, ArchR |
| SHARE-seq | RNA + ATAC | Seurat, Signac |
| Spatial (Visium) | RNA + spatial | Seurat, Squidpy |

## Workflow

1. **Calculate**: Reassemble isolated modalities to identical identifiers.
2. **Normalize**: Compute scale and metric dimensions natively for both arms.
3. **Execute**: Fuse structures via multi-modal matrices (WNN/MOFA).
4. **Visualise**: Render combined UMAP architecture layouts.
5. **Report**: Tabulate alignment consistency metrics.

## CLI Reference

```bash
python skills/singlecell/multiome/sc_multiome.py \
  --input <data.h5ad> --output <dir>
python omicsclaw.py run sc-multiome --demo
```

## Algorithm / Methodology

### CITE-seq Analysis (Seurat R)

#### Load Data

```r
library(Seurat)

data <- Read10X('filtered_feature_bc_matrix/')
rna_counts <- data$`Gene Expression`
adt_counts <- data$`Antibody Capture`

obj <- CreateSeuratObject(counts = rna_counts, assay = 'RNA')
obj[['ADT']] <- CreateAssayObject(counts = adt_counts)
```

#### QC and Normalization

```r
obj <- PercentageFeatureSet(obj, pattern = '^MT-', col.name = 'percent.mt')
obj <- subset(obj, nFeature_RNA > 200 & percent.mt < 20)

# Normalize RNA
obj <- NormalizeData(obj, assay = 'RNA')
obj <- FindVariableFeatures(obj, assay = 'RNA')
obj <- ScaleData(obj, assay = 'RNA')

# Normalize ADT (CLR normalization)
obj <- NormalizeData(obj, assay = 'ADT', normalization.method = 'CLR', margin = 2)
obj <- ScaleData(obj, assay = 'ADT')
```

#### Weighted Nearest Neighbor (WNN) Clustering

**Goal:** Jointly cluster cells using both modalities, weighting each per cell.

```r
# PCA for each modality
obj <- RunPCA(obj, assay = 'RNA', reduction.name = 'pca')
obj <- RunPCA(obj, assay = 'ADT', reduction.name = 'apca',
              features = rownames(obj[['ADT']]))

# WNN graph combining both modalities
obj <- FindMultiModalNeighbors(obj,
    reduction.list = list('pca', 'apca'),
    dims.list = list(1:30, 1:18))

# Cluster on WNN graph
obj <- FindClusters(obj, graph.name = 'wsnn', resolution = 0.5)

# UMAP on WNN
obj <- RunUMAP(obj, nn.name = 'weighted.nn', reduction.name = 'wnn.umap')
```

#### Visualize

```r
DimPlot(obj, reduction = 'wnn.umap', label = TRUE)

FeaturePlot(obj, features = c('adt_CD3', 'adt_CD19', 'adt_CD14'),
            reduction = 'wnn.umap')

# Compare modality weights
VlnPlot(obj, features = 'RNA.weight', group.by = 'seurat_clusters')
```

### 10X Multiome (RNA + ATAC, Seurat + Signac)

```r
library(Seurat)
library(Signac)

# Load data
rna_counts <- Read10X_h5('filtered_feature_bc_matrix.h5')$`Gene Expression`
atac_counts <- Read10X_h5('filtered_feature_bc_matrix.h5')$Peaks
fragments <- CreateFragmentObject('atac_fragments.tsv.gz')

obj <- CreateSeuratObject(counts = rna_counts, assay = 'RNA')
obj[['ATAC']] <- CreateChromatinAssay(counts = atac_counts, fragments = fragments,
                                       genome = 'hg38', min.cells = 5)

# ATAC processing
obj <- NucleosomeSignal(obj)
obj <- TSSEnrichment(obj)
obj <- RunTFIDF(obj, assay = 'ATAC')
obj <- FindTopFeatures(obj, assay = 'ATAC', min.cutoff = 'q0')
obj <- RunSVD(obj, assay = 'ATAC')

# RNA processing
DefaultAssay(obj) <- 'RNA'
obj <- NormalizeData(obj) %>% FindVariableFeatures() %>% ScaleData() %>% RunPCA()

# WNN integration
obj <- FindMultiModalNeighbors(obj, reduction.list = list('pca', 'lsi'),
                                dims.list = list(1:30, 2:30))
obj <- RunUMAP(obj, nn.name = 'weighted.nn', reduction.name = 'wnn.umap')
obj <- FindClusters(obj, graph.name = 'wsnn')
```

### MuData / muon (Python)

```python
import scanpy as sc
import muon as mu
from muon import prot as pt

mdata = mu.read_10x_h5('filtered_feature_bc_matrix.h5')

rna = mdata.mod['rna']
prot = mdata.mod['prot']

# Process RNA
sc.pp.filter_cells(rna, min_genes=200)
sc.pp.normalize_total(rna, target_sum=1e4)
sc.pp.log1p(rna)
sc.pp.highly_variable_genes(rna)
sc.tl.pca(rna)

# Process protein (CLR normalization)
pt.pp.clr(prot)

# Multi-omics factor analysis
mu.tl.mofa(mdata, n_factors=20)

# Joint UMAP
mu.tl.umap(mdata)
mu.pl.umap(mdata, color=['rna:leiden', 'prot:CD3'])
```

### Multi-Modal Marker Discovery

```r
DefaultAssay(obj) <- 'RNA'
rna_markers <- FindAllMarkers(obj, only.pos = TRUE)

DefaultAssay(obj) <- 'ADT'
adt_markers <- FindAllMarkers(obj, only.pos = TRUE)

all_markers <- rbind(
    transform(rna_markers, modality = 'RNA'),
    transform(adt_markers, modality = 'ADT')
)
```

### Modality Weight Inspection

```r
weights <- obj@reductions$wnn@misc$weights
aggregate(weights, by = list(obj$seurat_clusters), mean)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `wnn` | wnn, mofa, standard |
| `--modalities` | `rna,adt` | Comma-separated modalities |
| `--n-factors` | `20` | Number of factors (MOFA) |

## Example Queries

- "Run multimodal WNN integration across my protein and transcript data"
- "Use MOFA to derive multi-omic factors"

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

Reference examples tested with: scanpy 1.10+, muon 0.1+, numpy 1.26+

## Dependencies

**Required**: scanpy, numpy
**Optional**: muon, Seurat (R), Signac (R), ArchR (R)

## Citations

- [WNN](https://doi.org/10.1016/j.cell.2021.04.048) — Hao et al., Cell 2021
- [MOFA+](https://doi.org/10.15252/msb.20209325) — Argelaguet et al., Molecular Systems Biology 2020
- [muon](https://doi.org/10.1186/s13059-021-02577-8) — Bredikhin et al., Genome Biology 2022
- [CITE-seq](https://doi.org/10.1038/nmeth.4380) — Stoeckius et al., Nature Methods 2017

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `sc-preprocess` — Data loading and QC
- `sc-integrate` — Batch integration (single modality)
- `sc-annotate` — Cell type annotation post WNN
