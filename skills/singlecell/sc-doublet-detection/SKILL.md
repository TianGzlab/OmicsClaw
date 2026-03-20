---
name: sc-doublet-detection
description: >-
  Doublet detection and removal using Scrublet (Python), DoubletFinder (R),
  and scDblFinder (R). Essential QC step before clustering.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, doublet, Scrublet, DoubletFinder, scDblFinder, QC]
metadata:
  omicsclaw:
    domain: singlecell
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "👥"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scrublet
        bins: []
    trigger_keywords:
      - doublet detection
      - doublet removal
      - Scrublet
      - DoubletFinder
      - scDblFinder
---

# 👥 Single-Cell Doublet Detection

Detect and remove doublets (multiple cells captured in one droplet) from scRNA-seq data. Essential QC step before clustering.

## Why This Exists

- **Without it**: Doublets create artificial intermediate cell populations in clustering
- **With it**: Automated detection with configurable thresholds and method comparison
- **Why OmicsClaw**: Multiple methods with automatic expected rate calculation

## Core Capabilities

1. **Scrublet** (Python): Simulation-based scoring via synthetic doublet comparison
2. **DoubletFinder** (R): pANN-based classification with parameter sweep optimization
3. **scDblFinder** (R, recommended): Fast gradient-boosted classifier, highest accuracy

## Workflow

1. **Calculate Metrics**: Compute underlying simulation graphs of multiplets.
2. **Score**: Attribute probabilistic doublet value to all single droplets.
3. **Threshold**: Execute distribution breakpoint testing.
4. **Filter**: Clear invalid multi-cells from AnnData.
5. **Report**: Detail retained singles versus computed doublets.

## CLI Reference

```bash
python skills/singlecell/sc-doublet-detection/sc_doublet.py \
  --input <data.h5ad> --output <dir>
python skills/singlecell/sc-doublet-detection/sc_doublet.py \
  --input <data.h5ad> --method scdblfinder --output <dir>
python omicsclaw.py run sc-doublet-detection --demo
```

## Algorithm / Methodology

### Scrublet (Python)

**Goal:** Detect and score doublets using simulated doublet profiles.

```python
import scrublet as scr
import scanpy as sc
import numpy as np

adata = sc.read_10x_mtx('filtered_feature_bc_matrix/')

scrub = scr.Scrublet(adata.X, expected_doublet_rate=0.06)
doublet_scores, predicted_doublets = scrub.scrub_doublets(
    min_counts=2, min_cells=3,
    min_gene_variability_pctl=85, n_prin_comps=30
)

adata.obs['doublet_score'] = doublet_scores
adata.obs['predicted_doublet'] = predicted_doublets

print(f'Detected {predicted_doublets.sum()} doublets ({100*predicted_doublets.mean():.1f}%)')
```

#### Visualize and Filter

```python
# Score histogram
scrub.plot_histogram()

# UMAP with doublet scores
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.highly_variable_genes(adata)
sc.pp.pca(adata)
sc.pp.neighbors(adata)
sc.tl.umap(adata)
sc.pl.umap(adata, color=['doublet_score', 'predicted_doublet'], save='_doublets.pdf')

# Filter doublets
adata_filtered = adata[~adata.obs['predicted_doublet']].copy()
print(f'Kept {adata_filtered.n_obs} cells after doublet removal')
```

#### Manual Threshold

```python
threshold = 0.25
predicted_doublets = doublet_scores > threshold
adata.obs['predicted_doublet'] = predicted_doublets
```

### DoubletFinder (R)

**Goal:** Detect doublets using pANN-based classification with optimal pK parameter.

```r
library(Seurat)
library(DoubletFinder)

seurat_obj <- NormalizeData(seurat_obj)
seurat_obj <- FindVariableFeatures(seurat_obj)
seurat_obj <- ScaleData(seurat_obj)
seurat_obj <- RunPCA(seurat_obj)
seurat_obj <- RunUMAP(seurat_obj, dims = 1:20)
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:20)
seurat_obj <- FindClusters(seurat_obj, resolution = 0.5)

# Parameter sweep for optimal pK
sweep.res <- paramSweep(seurat_obj, PCs = 1:20, sct = FALSE)
sweep.stats <- summarizeSweep(sweep.res, GT = FALSE)
bcmvn <- find.pK(sweep.stats)
optimal_pk <- as.numeric(as.character(bcmvn$pK[which.max(bcmvn$BCmetric)]))

# Run DoubletFinder
nExp_poi <- round(0.06 * nrow(seurat_obj@meta.data))
seurat_obj <- doubletFinder(seurat_obj, PCs = 1:20, pN = 0.25, pK = optimal_pk,
                             nExp = nExp_poi, reuse.pANN = FALSE, sct = FALSE)

# Filter doublets
df_col <- grep('DF.classifications', colnames(seurat_obj@meta.data), value = TRUE)
seurat_obj <- subset(seurat_obj, cells = colnames(seurat_obj)[seurat_obj@meta.data[[df_col]] == 'Singlet'])
```

### scDblFinder (R — Recommended)

**Goal:** Detect doublets using fast gradient-boosted classifier.

```r
library(scDblFinder)
library(SingleCellExperiment)

sce <- as.SingleCellExperiment(seurat_obj)
sce <- scDblFinder(sce)

table(sce$scDblFinder.class)

# Transfer results back to Seurat
seurat_obj$scDblFinder_class <- sce$scDblFinder.class
seurat_obj$scDblFinder_score <- sce$scDblFinder.score
seurat_obj <- subset(seurat_obj, subset = scDblFinder_class == 'singlet')
```

#### Multi-Sample Processing

```r
sce <- scDblFinder(sce, samples = 'sample_id')
```

## Expected Doublet Rates

| Cells Loaded | Expected Rate |
|--------------|---------------|
| 1,000 | ~0.8% |
| 2,000 | ~1.6% |
| 5,000 | ~4.0% |
| 10,000 | ~8.0% |
| 15,000 | ~12% |

Formula: `rate ≈ cells_loaded / 1000 * 0.008`

## Method Comparison

| Method | Speed | Accuracy | Language |
|--------|-------|----------|----------|
| Scrublet | Fast | Good | Python |
| DoubletFinder | Slow | Good | R |
| scDblFinder | Fast | Excellent | R |

## Heterotypic vs Homotypic Doublets

- **Heterotypic**: Two different cell types — easier to detect (intermediate expression)
- **Homotypic**: Same cell type — harder to detect (may have higher total counts)

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `scrublet` | scrublet, doubletfinder, scdblfinder |
| `--expected-doublet-rate` | `0.06` | Expected doublet rate |
| `--threshold` | `auto` | Doublet score threshold |

## Example Queries

- "Perform doublet detection with scDblFinder"
- "Filter multiplets from this H5AD via Scrublet"

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

## Dependencies

**Required**: scanpy, numpy
**Optional**: scrublet, `rpy2` + `anndata2ri` + R packages `DoubletFinder`, `scDblFinder`, `Seurat`, and `SingleCellExperiment`

## Citations

- [Scrublet](https://doi.org/10.1016/j.cels.2018.11.005) — Wolock et al., Cell Systems 2019
- [DoubletFinder](https://doi.org/10.1016/j.cels.2019.03.003) — McGinnis et al., Cell Systems 2019
- [scDblFinder](https://doi.org/10.12688/f1000research.73600.2) — Germain et al., F1000Research 2022

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `sc-preprocess` — QC after doublet removal
- `sc-integrate` — Integration after cleaning
