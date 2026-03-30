# Batch Integration Methods Guide

## Overview

Batch effects are systematic technical differences between samples processed in different experimental runs, using different reagents, or by different operators. These effects can mask biological variation and lead to spurious clustering by batch rather than cell type.

This guide covers when, why, and how to perform batch integration using modern methods: scVI/scANVI, Harmony, and Seurat CCA/RPCA.

---

## The Batch Effect Problem

### What are Batch Effects?

**Technical sources:**
- Different 10X Chromium chip runs
- Different library preparation dates
- Different reagent lots
- Different operators or labs
- Different sequencing runs

**Consequences:**
- Cells cluster by batch, not biology
- Cell types split across batches
- False positive markers (batch-specific genes)
- Cannot compare conditions across batches
- Invalid downstream analyses (DE, trajectory, etc.)

### When to Integrate

**Always integrate for:**
- ✅ Multiple 10X runs or sequencing batches
- ✅ Multi-donor or multi-condition studies
- ✅ Data from different labs or protocols
- ✅ Visible batch clustering in initial UMAP

**May skip for:**
- ❌ Single batch experiments
- ❌ When batch aligns with biology (confounded design)
- ❌ When batch effects are minimal (check first!)

---

## Methods Comparison

### Quick Decision Tree

```
Do you have cell type labels?
├─ YES → scANVI (best) or Harmony (faster)
└─ NO → scVI (best) or Harmony (faster) or Seurat RPCA (R users)

Do you need speed over accuracy?
├─ YES → Harmony
└─ NO → scVI/scANVI

Is your dataset very large (>100k cells)?
├─ YES → Harmony or Seurat RPCA (sketch-based)
└─ NO → scVI/scANVI

Are you in R/Seurat ecosystem?
├─ YES → Seurat CCA/RPCA or Harmony (via SeuratWrappers)
└─ NO → scVI/scANVI or Harmony
```

### Method Comparison Table

| Method | Pros | Cons | Best For |
|--------|------|------|----------|
| **scVI** | State-of-the-art, learns gene-specific batch effects, uncertainty quantification | Requires GPU, ~10-30min runtime, black-box | Most use cases, especially complex batch structures |
| **scANVI** | Semi-supervised, leverages labels, improves rare cell types | Requires partial labels, same cons as scVI | When you have preliminary cell type annotations |
| **Harmony** | Fast (minutes), interpretable, robust | Less powerful than scVI, can over-correct | Large datasets, quick iteration, simple batch structures |
| **Seurat CCA** | Well-established, works in Seurat | Slower than Harmony, requires anchor finding | R users, moderate batch effects |
| **Seurat RPCA** | Faster than CCA, scales well | Requires similar cell compositions | Large Seurat datasets, well-represented cell types |

---

## scVI Integration

### Overview

**scVI** (single-cell Variational Inference) is a deep generative model that learns a low-dimensional representation of gene expression while explicitly modeling batch effects.

**Key Features:**
- Probabilistic framework (uncertainty estimates)
- Gene-specific batch effect correction
- Handles complex batch structures (nested batches)
- Built-in denoising and imputation

**Requirements:**
- Python package: `scvi-tools`
- GPU recommended (10-20x faster)
- ~10-30 minutes per dataset

**Installation:**
```bash
pip install scvi-tools
```

### Basic Usage

```python
import scvi

# Setup AnnData for scVI
scvi.model.SCVI.setup_anndata(
    adata,
    batch_key="batch",
    layer="counts"  # Use raw counts
)

# Train model
model = scvi.model.SCVI(
    adata,
    n_latent=30,      # Latent dimensions (default: 10, recommend 30 for complex data)
    n_layers=2,       # Neural network depth
    n_hidden=128,     # Hidden layer size
    dropout_rate=0.1
)

model.train(
    max_epochs=400,        # Training iterations (default: 400)
    early_stopping=True,   # Stop if no improvement
    use_gpu=True
)

# Get integrated representation
adata.obsm["X_scvi"] = model.get_latent_representation()

# Downstream analysis
sc.pp.neighbors(adata, use_rep="X_scvi")
sc.tl.umap(adata)
```

### Key Parameters

**n_latent**
- Dimensionality of latent space
- Default: 10
- **Recommendation:** 30 for complex datasets, 20 for simple
- Higher values: More capacity but risk overfitting

**n_layers / n_hidden**
- Neural network architecture
- Default: 2 layers, 128 hidden units
- **Recommendation:** Keep defaults unless very large/complex data

**max_epochs**
- Training iterations
- Default: 400
- **Recommendation:** 400-600 for most datasets
- Use `early_stopping=True` to avoid overfitting

**dropout_rate**
- Regularization parameter
- Default: 0.1
- **Recommendation:** 0.1 for most datasets

### Advanced: Gene Likelihood

```python
# For UMI count data (default, recommended)
model = scvi.model.SCVI(adata, gene_likelihood="nb")  # Negative binomial

# For full-length data (Smart-seq2)
model = scvi.model.SCVI(adata, gene_likelihood="zinb")  # Zero-inflated NB
```

---

## scANVI Integration

### Overview

**scANVI** (single-cell ANnotation using Variational Inference) extends scVI with semi-supervised learning using cell type labels.

**Key Features:**
- Leverages existing cell type annotations
- Improves rare cell type separation
- Transfers labels to unlabeled cells
- Better integration than unsupervised scVI

**When to Use:**
- You have preliminary cell type annotations (even if partial)
- You want to integrate and annotate simultaneously
- You have rare cell types that need preservation

### Basic Usage

```python
import scvi

# Option 1: Train scANVI from scratch
scvi.model.SCANVI.setup_anndata(
    adata,
    batch_key="batch",
    labels_key="cell_type",     # Existing annotations
    unlabeled_category="Unknown"  # Label for unlabeled cells
)

model = scvi.model.SCANVI(
    adata,
    n_latent=30,
    unlabeled_category="Unknown"
)

model.train(max_epochs=400, use_gpu=True)

# Option 2: Initialize from pre-trained scVI (recommended)
# First train scVI as above, then:
scanvi_model = scvi.model.SCANVI.from_scvi_model(
    scvi_model,
    unlabeled_category="Unknown",
    labels_key="cell_type"
)

scanvi_model.train(max_epochs=200, use_gpu=True)

# Get integrated representation
adata.obsm["X_scanvi"] = scanvi_model.get_latent_representation()

# Get predicted labels
adata.obs["scanvi_predictions"] = scanvi_model.predict()
```

### Partial Annotations

```python
# You can have mix of labeled and unlabeled cells
adata.obs["cell_type"] = [
    "T cell", "B cell", "Unknown", "Unknown", "Monocyte", ...
]

# scANVI will learn from labeled cells and predict unlabeled ones
```

---

## Harmony Integration

### Overview

**Harmony** is a fast, interpretative integration method based on iterative clustering and correction.

**Key Features:**
- Very fast (minutes even for large datasets)
- Interpretable (linear correction per cluster)
- Robust to over-correction
- Works with any dimensionality reduction
- No GPU required

**Best For:**
- Large datasets (>100k cells)
- Quick iteration during analysis
- Simple batch structures
- When interpretability is important

**Installation:**
```bash
pip install harmonypy  # Python
```

```r
# R
install.packages("harmony")
```

### Python Usage

```python
import scanpy as sc
import harmonypy as hm

# Run PCA first (Harmony corrects PC space)
sc.tl.pca(adata, n_comps=50)

# Run Harmony
harmony_out = hm.run_harmony(
    adata.obsm['X_pca'],
    adata.obs,
    'batch',
    max_iter_harmony=10,  # Iterations (default: 10)
    theta=2               # Diversity penalty (default: 2)
)

adata.obsm['X_harmony'] = harmony_out.Z_corr.T

# Downstream analysis
sc.pp.neighbors(adata, use_rep='X_harmony')
sc.tl.umap(adata)
```

### R Usage (Seurat)

```r
library(harmony)
library(Seurat)

# Integrate Seurat object
seurat_obj <- RunHarmony(
  seurat_obj,
  group.by.vars = "batch",
  dims.use = 1:30,        # PCs to correct
  theta = 2,              # Diversity penalty
  lambda = 1,             # Ridge regression penalty
  max.iter.harmony = 10
)

# Downstream analysis
seurat_obj <- RunUMAP(seurat_obj, reduction = "harmony", dims = 1:30)
seurat_obj <- FindNeighbors(seurat_obj, reduction = "harmony", dims = 1:30)
```

### Key Parameters

**theta**
- Diversity penalty (how much to mix batches)
- Default: 2
- **Recommendation:**
  - theta = 0: No correction
  - theta = 1: Gentle correction
  - theta = 2: Standard correction (recommended)
  - theta = 4: Aggressive correction
- Start with 2, increase if under-corrected

**lambda**
- Ridge regression penalty
- Default: 1
- **Recommendation:** Keep at 1 unless overfitting issues

**max_iter_harmony**
- Number of iterations
- Default: 10
- **Recommendation:** 10 is usually sufficient

---

## Seurat Integration (CCA/RPCA)

### Overview

**Seurat v5** offers two integration methods:
- **CCA** (Canonical Correlation Analysis): Learns shared correlation structure
- **RPCA** (Reciprocal PCA): Faster, requires similar cell compositions

**Best For:**
- R/Seurat users
- Moderate to large datasets
- When you want to stay in Seurat ecosystem

### CCA Integration

```r
library(Seurat)

# Split by batch
seurat_list <- SplitObject(seurat_obj, split.by = "batch")

# Normalize and find variable features per batch
seurat_list <- lapply(seurat_list, function(x) {
  x <- NormalizeData(x)
  x <- FindVariableFeatures(x, nfeatures = 2000)
})

# Find integration anchors
features <- SelectIntegrationFeatures(seurat_list)
anchors <- FindIntegrationAnchors(
  object.list = seurat_list,
  anchor.features = features,
  reduction = "cca",
  dims = 1:30
)

# Integrate
seurat_integrated <- IntegrateData(
  anchorset = anchors,
  dims = 1:30
)

# Downstream analysis
seurat_integrated <- ScaleData(seurat_integrated)
seurat_integrated <- RunPCA(seurat_integrated, npcs = 50)
seurat_integrated <- RunUMAP(seurat_integrated, dims = 1:30)
```

### RPCA Integration

```r
# Same as CCA but with reduction = "rpca"
anchors <- FindIntegrationAnchors(
  object.list = seurat_list,
  anchor.features = features,
  reduction = "rpca",  # Use RPCA instead of CCA
  dims = 1:30
)

seurat_integrated <- IntegrateData(anchors, dims = 1:30)
```

### When to Use RPCA vs CCA

**Use RPCA when:**
- Dataset is large (>100k cells)
- Cell type compositions are similar across batches
- You need faster integration

**Use CCA when:**
- Cell type compositions differ across batches
- You have complex batch structures
- You prioritize accuracy over speed

---

## Integration Quality Metrics

### LISI (Local Inverse Simpson's Index)

**iLISI (integration LISI):**
- Measures batch mixing
- Range: 1 (no mixing) to N_batches (perfect mixing)
- Higher is better
- **Target:** Close to number of batches

**cLISI (cell type LISI):**
- Measures cell type separation
- Range: 1 (perfect separation) to N_celltypes
- Lower is better
- **Target:** Close to 1

```python
# Python - Compute LISI scores
from scripts.integration_diagnostics import compute_lisi_scores

lisi_scores = compute_lisi_scores(
    adata,
    batch_key="batch",
    label_key="cell_type",
    use_rep="X_scvi"  # or "X_harmony", "X_pca"
)

print(f"iLISI (batch mixing): {lisi_scores['ilisi'].mean():.2f}")
print(f"cLISI (cell type separation): {lisi_scores['clisi'].mean():.2f}")
```

```r
# R - Compute LISI scores
source("scripts/integration_diagnostics.R")

lisi_scores <- compute_lisi_scores(
  seurat_obj,
  batch_col = "batch",
  label_col = "cell_type",
  reduction = "harmony"  # or "pca", "integrated"
)

cat(sprintf("iLISI (batch mixing): %.2f\n", mean(lisi_scores$ilisi)))
cat(sprintf("cLISI (cell type separation): %.2f\n", mean(lisi_scores$clisi)))
```

### ASW (Average Silhouette Width)

**Batch ASW:**
- Measures batch mixing in cell type clusters
- Range: -1 to 1
- Lower is better (batches well-mixed)
- **Target:** Close to 0

**Cell type ASW:**
- Measures cell type separation
- Range: -1 to 1
- Higher is better
- **Target:** >0.5

```python
# Python
from scripts.integration_diagnostics import compute_asw_scores

asw_scores = compute_asw_scores(
    adata,
    batch_key="batch",
    label_key="cell_type",
    use_rep="X_scvi"
)

print(f"Batch ASW: {asw_scores['batch_asw']:.3f}")
print(f"Cell type ASW: {asw_scores['celltype_asw']:.3f}")
```

```r
# R
asw_scores <- compute_asw_scores(
  seurat_obj,
  batch_col = "batch",
  label_col = "cell_type",
  reduction = "harmony"
)

cat(sprintf("Batch ASW: %.3f\n", asw_scores$batch_asw))
cat(sprintf("Cell type ASW: %.3f\n", asw_scores$celltype_asw))
```

### Visual Inspection

**Critical checks:**
1. **UMAP by batch:** Batches should overlap, not form separate islands
2. **UMAP by cell type:** Cell types should remain separated
3. **Marker genes:** Cell type markers should remain specific

```python
# Python
import scanpy as sc

# Before integration
sc.pl.umap(adata, color=['batch', 'cell_type'], title=['Batch (before)', 'Cell type (before)'])

# After integration
sc.pp.neighbors(adata, use_rep='X_scvi')
sc.tl.umap(adata)
sc.pl.umap(adata, color=['batch', 'cell_type'], title=['Batch (after)', 'Cell type (after)'])

# Check marker genes
sc.pl.umap(adata, color=['CD3D', 'MS4A1', 'LYZ'], cmap='Reds')
```

```r
# R
# Before integration
DimPlot(seurat_obj, reduction = "umap", group.by = "batch")
DimPlot(seurat_obj, reduction = "umap", group.by = "cell_type")

# After integration
DimPlot(seurat_obj, reduction = "umap", group.by = "batch")
DimPlot(seurat_obj, reduction = "umap", group.by = "cell_type")

# Check marker genes
FeaturePlot(seurat_obj, features = c("CD3D", "MS4A1", "LYZ"))
```

---

## Choosing the Right Method

### Decision Criteria

**1. Dataset Size**
- Small (<10k cells): Any method works, prefer scVI for quality
- Medium (10-50k cells): scVI or Harmony
- Large (50-200k cells): Harmony or scANVI
- Very large (>200k cells): Harmony or Seurat RPCA (sketch)

**2. Batch Complexity**
- Simple (2-3 batches): Harmony sufficient
- Complex (many batches, nested structure): scVI/scANVI
- Confounded (batch = biology): Manual correction or skip integration

**3. Available Labels**
- No labels: scVI or Harmony
- Partial labels: scANVI (best choice)
- Full labels: scANVI or Harmony

**4. Computational Resources**
- GPU available: scVI/scANVI
- CPU only: Harmony or Seurat
- Limited time: Harmony

**5. Analysis Ecosystem**
- Python/scanpy: scVI or Harmony
- R/Seurat: Seurat CCA/RPCA or Harmony

### Recommended Workflows

**Standard workflow (Python):**
```python
# 1. Try scVI first (best quality)
model = scvi.model.SCVI(adata, n_latent=30)
model.train(max_epochs=400, use_gpu=True)
adata.obsm["X_scvi"] = model.get_latent_representation()

# 2. If you have labels, use scANVI
scanvi_model = scvi.model.SCANVI.from_scvi_model(model, ...)
scanvi_model.train(max_epochs=200)
adata.obsm["X_scanvi"] = scanvi_model.get_latent_representation()

# 3. Check quality with LISI/ASW
compute_lisi_scores(adata, use_rep="X_scanvi")
```

**Fast workflow (large data):**
```python
# Use Harmony for speed
sc.tl.pca(adata, n_comps=50)
harmony_out = hm.run_harmony(adata.obsm['X_pca'], adata.obs, 'batch')
adata.obsm['X_harmony'] = harmony_out.Z_corr.T
```

**Seurat workflow (R):**
```r
# Use Harmony for simplicity
seurat_obj <- RunHarmony(seurat_obj, group.by.vars = "batch", theta = 2)

# Or use CCA for complex batches
anchors <- FindIntegrationAnchors(seurat_list, reduction = "cca")
seurat_integrated <- IntegrateData(anchors)
```

---

## Common Issues

### Issue 1: Over-Correction

**Symptoms:**
- Biological cell types merge together
- Loss of cell type-specific markers
- Low cLISI or high cell type ASW (bad)

**Solutions:**
- **scVI:** Reduce `n_latent` or `max_epochs`
- **Harmony:** Lower `theta` (try 1 instead of 2)
- **Seurat:** Use fewer dimensions in integration

### Issue 2: Under-Correction

**Symptoms:**
- Cells still cluster by batch
- Batch remains dominant in UMAP
- Low iLISI or high batch ASW (bad)

**Solutions:**
- **scVI:** Increase `n_latent` to 30-40, increase `max_epochs`
- **Harmony:** Increase `theta` (try 3-4)
- **Seurat:** Use more anchor features, increase `k.anchor`

### Issue 3: GPU Out of Memory (scVI)

**Symptoms:**
- CUDA out of memory error

**Solutions:**
- Reduce `n_hidden` (try 64 instead of 128)
- Use `train_size=0.9` (smaller training set)
- Subsample data temporarily
- Use CPU (slower): `use_gpu=False`

### Issue 4: Poor Integration of Rare Cell Types

**Symptoms:**
- Rare populations split by batch
- Over-representation in one batch

**Solutions:**
- **scANVI:** Best option, leverages labels
- **scVI:** Increase `n_latent` to 40-50
- **Harmony:** Increase `theta`
- Consider downsampling abundant cell types

### Issue 5: Batch-Specific Cell Types

**Problem:** One cell type only present in one batch

**Solutions:**
- Do NOT integrate if batch = biology
- Exclude that cell type from integration
- Use conditional integration (integrate rest, add back)

---

## Best Practices

### 1. Always Check Before Integration

```r
# Initial clustering without integration
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30)
seurat_obj <- FindClusters(seurat_obj)
seurat_obj <- RunUMAP(seurat_obj, dims = 1:30)
DimPlot(seurat_obj, group.by = "batch")
```

**If batches already overlap well → skip integration!**

### 2. Compare Multiple Methods

```r
# Try both Harmony and Seurat CCA
# Compare LISI/ASW scores
# Choose method with best balance
```

### 3. Validate with Marker Genes

```r
# Check cell type markers remain specific after integration
marker_genes <- c("CD3D", "MS4A1", "LYZ", "NKG7", "FCGR3A")
FeaturePlot(seurat_obj, features = marker_genes)
```

### 4. Use Corrected Data Appropriately

**For clustering/UMAP:**
- ✅ Use integrated representation (harmony, integrated assay)

**For differential expression:**
- ❌ Do NOT use integrated counts
- ✅ Use original RNA assay counts
- ✅ Include batch as covariate in model

**For visualization:**
- ✅ Use integrated UMAP coordinates
- ✅ Use original RNA assay for gene expression overlay

### 5. Document Your Integration

```r
# Record integration parameters
seurat_obj@misc$integration <- list(
  method = "Harmony",
  batch_col = "batch",
  theta = 2,
  ilisi_score = 2.3,
  clisi_score = 1.1
)
```

---

## Method-Specific Tips

### scVI/scANVI Tips

- Always use raw counts (layer="counts")
- GPU training is 10-20x faster
- Early stopping prevents overfitting
- Save models for reproducibility: `model.save("scvi_model/")`
- Use `model.history` to check training convergence

### Harmony Tips

- Run on PCA space, not raw data
- theta=2 is good default, adjust if needed
- Very robust, hard to over-correct
- Can run iteratively (increase max_iter if under-corrected)
- Works with any PCA (Seurat, scanpy, etc.)

### Seurat CCA/RPCA Tips

- Normalize each batch separately first
- Use 2000-3000 variable features
- RPCA faster but requires similar compositions
- Can integrate >2 datasets simultaneously
- Set `reference` parameter if one batch is high-quality

---

## Key References

1. **scVI/scANVI:**
   - Lopez R, et al. Deep generative modeling for single-cell transcriptomics. *Nat Methods*. 2018;15(12):1053-1058.
   - Xu C, et al. Probabilistic harmonization and annotation of single-cell transcriptomics data with deep generative models. *Mol Syst Biol*. 2021;17(1):e9620.
   - https://scvi-tools.org/

2. **Harmony:**
   - Korsunsky I, et al. Fast, sensitive and accurate integration of single-cell data with Harmony. *Nat Methods*. 2019;16(12):1289-1296.
   - https://github.com/immunogenomics/harmony

3. **Seurat Integration:**
   - Hao Y, et al. Integrated analysis of multimodal single-cell data. *Cell*. 2021;184(13):3573-3587.e29.
   - Stuart T, et al. Comprehensive Integration of Single-Cell Data. *Cell*. 2019;177(7):1888-1902.e21.
   - https://satijalab.org/seurat/

4. **Integration Benchmarking:**
   - Luecken MD, et al. Benchmarking atlas-level data integration in single-cell genomics. *Nat Methods*. 2022;19(1):41-50.
   - Tran HTN, et al. A benchmark of batch-effect correction methods for single-cell RNA sequencing data. *Genome Biol*. 2020;21(1):12.

5. **LISI Metric:**
   - Korsunsky I, et al. Fast, sensitive and accurate integration of single-cell data with Harmony. *Nat Methods*. 2019 (includes LISI description).

---

## Summary

**Recommended approach for most users:**

1. **Start with Harmony** (R, simple) or **scVI** (Python, best quality)
2. **Check integration quality** with LISI and visual inspection
3. **Validate biology** is preserved (marker genes, cell types)
4. **Use scANVI** if you have labels to improve rare cells
5. **Document parameters** and quality metrics

**Quick selection guide:**
- **Best quality:** scVI/scANVI
- **Best speed:** Harmony
- **Best for R users:** Harmony or Seurat CCA/RPCA
- **Best for labels:** scANVI
- **Best for large data:** Harmony or Seurat RPCA

Following these guidelines ensures proper batch correction while preserving biological signal in your single-cell RNA-seq data.
