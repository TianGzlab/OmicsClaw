# Seurat Best Practices Guide

This document provides detailed best practices for scRNA-seq analysis with Seurat, based on official documentation and community standards.

---

## Table of Contents

1. [Normalization Method Selection](#normalization-method-selection)
2. [QC Threshold Guidelines](#qc-threshold-guidelines)
3. [Dimensionality Selection](#dimensionality-selection)
4. [Clustering Resolution](#clustering-resolution)
5. [Common Issues and Solutions](#common-issues-and-solutions)
6. [Performance Optimization](#performance-optimization)

---

## Normalization Method Selection

### When to Use SCTransform

**Use SCTransform when:**
- You have UMI-based data (10X Chromium, Drop-seq, inDrop)
- Dataset has >1,000 cells
- You want better handling of technical variation
- You need robust performance across diverse datasets

**Advantages:**
- Better variance stabilization
- Handles sequencing depth variation more effectively
- Reduces batch effects
- Finds variable features automatically

**Limitations:**
- Slower than LogNormalize
- Can fail on very small datasets (<500 cells)
- May struggle with extreme heterogeneity

### When to Use LogNormalize

**Use LogNormalize when:**
- Non-UMI data (Smart-seq2, full-length protocols)
- Very small datasets (<500 cells)
- You need faster processing
- SCTransform fails or produces artifacts
- You want explicit control over each step

**Advantages:**
- Faster computation
- More interpretable
- Works reliably on small datasets
- Transparent workflow

**Workflow:**
```r
seurat_obj <- NormalizeData(seurat_obj)
seurat_obj <- FindVariableFeatures(seurat_obj, nfeatures = 2000)
seurat_obj <- ScaleData(seurat_obj, vars.to.regress = c("percent.mt"))
```

---

## QC Threshold Guidelines

### General Principles

Quality control thresholds should be:
1. **Data-driven**: Based on your specific dataset's distributions
2. **Conservative initially**: Can always relax if needed
3. **Tissue-specific**: Different tissues have different expected ranges

### Recommended Thresholds by Tissue

| Tissue Type | Min Features | Max Features | Max % MT | Rationale |
|-------------|--------------|--------------|----------|-----------|
| **PBMC** | 200 | 2,500 | 5% | Standard immune cells |
| **Brain** | 200 | 6,000 | 10% | Neurons express many genes |
| **Tumor** | 200 | 5,000 | 20% | Hypoxia and dying cells common |
| **Kidney** | 200 | 4,000 | 15% | Metabolically active |
| **Liver** | 200 | 4,000 | 15% | High metabolic activity |
| **Heart** | 200 | 4,000 | 15% | Cardiomyocytes have high MT |
| **Muscle** | 200 | 4,000 | 15% | Mitochondria-rich tissue |
| **Embryonic** | 200 | 5,000 | 10% | Dividing cells |

### How to Set Thresholds

**Step 1:** Plot QC distributions
```r
source("scripts/plot_qc.R")
plot_qc_violin(seurat_obj)
plot_qc_scatter(seurat_obj)
plot_qc_histogram(seurat_obj)
```

**Step 2:** Identify outliers
- **Low nFeature**: Empty droplets or debris (remove)
- **High nFeature**: Potential doublets (remove)
- **High % MT**: Dying/stressed cells (remove)

**Step 3:** Use MAD-based filtering (alternative)
```r
# Median Absolute Deviation approach
median_features <- median(seurat_obj$nFeature_RNA)
mad_features <- mad(seurat_obj$nFeature_RNA)

# Remove cells >3 MAD from median
upper_bound <- median_features + (3 * mad_features)
lower_bound <- max(200, median_features - (3 * mad_features))

# Apply
seurat_filtered <- subset(seurat_obj,
                          subset = nFeature_RNA > lower_bound &
                                   nFeature_RNA < upper_bound &
                                   percent.mt < 15)
```

### Red Flags

**Too few cells passing filters (<50% retained):**
- Thresholds may be too stringent
- Sample quality may be poor
- Check experimental protocol

**Clusters driven by QC metrics:**
- Regression didn't work adequately
- Try SCTransform or add more variables to `vars.to.regress`

---

## Dimensionality Selection

### How Many PCs to Use?

**General recommendations:**
- Compute 50 PCs initially
- Use `suggest_n_pcs()` from `scale_and_pca.R` or the elbow plot to determine how many to keep
- **Standard range: 20-30 PCs. NEVER use <15 PCs.**
- For PBMC data: 20 PCs is standard, 30 PCs is conservative/safe
- Being conservative (using more PCs) rarely hurts; using too few causes underfitting

**Data-driven approaches:**

**1. Variance-based (Recommended)**
```r
source("scripts/scale_and_pca.R")
suggested_pcs <- suggest_n_pcs(seurat_obj)
# Uses 85% cumulative variance threshold with min=15, max=30 guardrails
```

**2. Elbow Plot**
```r
plot_elbow(seurat_obj, ndims = 50)
```
- Look for "elbow" where variance plateaus
- Typical range: 20-35 PCs

**3. PC Heatmaps**
```r
plot_pca_heatmaps(seurat_obj, dims = 1:20)
```
- Visual inspection of PC structure
- Stop when heatmaps look like noise

**4. Statistical Test (slow but rigorous)**
```r
determine_pcs(seurat_obj, method = "jackstraw")
```

**Decision process:**
1. Compute 50 PCs
2. Call `suggest_n_pcs(seurat_obj)` for an automated recommendation
3. Plot elbow and inspect visually
4. Use 30 PCs as safe default if unclear
5. **Do NOT use heuristics like "last PC where variance > X% of PC1"** — this often yields too few PCs

### Common Mistakes

❌ Using too few PCs (e.g., only 10):
- Using <15 PCs almost always loses biological variation
- **Do NOT use ad-hoc heuristics** — they often yield too few PCs
- For PBMC: 20 PCs is the community standard (Luecken & Theis 2019)

❌ Using all PCs:
- Introduces noise
- Slows computation

✅ Safe default: **20-30 PCs** for most datasets; never <15 PCs

---

## Clustering Resolution

### Understanding Resolution

- **Low (0.2-0.5)**: Broad cell types (T cells, B cells, Monocytes)
- **Medium (0.6-0.8)**: Standard granularity (CD4 T, CD8 T, NK)
- **High (1.0-2.0)**: Fine subpopulations (Naive CD4, Memory CD4, Tregs)

### Choosing Resolution

**Test multiple resolutions:**
```r
source("scripts/cluster_cells.R")
seurat_obj <- cluster_multiple_resolutions(
  seurat_obj,
  dims = 1:30,
  resolutions = c(0.4, 0.6, 0.8, 1.0, 1.2)
)

# Visualize
source("scripts/plot_dimreduction.R")
plot_clustering_comparison(seurat_obj, resolutions = c(0.4, 0.6, 0.8, 1.0))
```

**Evaluation criteria:**

1. **Biological coherence**: Do clusters have clear marker genes?
2. **Cluster stability**: Similar at adjacent resolutions?
3. **Size distribution**: Avoid clusters with <10 cells
4. **Research question**: Need broad types or fine subtypes?

**Silhouette analysis (quantitative):**
```r
optimize_clustering_resolution(seurat_obj, dims = 1:30)
```

### Common Issues

**Over-clustering:**
- Symptoms: Many small clusters, similar marker genes
- Solution: Lower resolution

**Under-clustering:**
- Symptoms: Mixed cell types in same cluster, poor separation
- Solution: Increase resolution or use more PCs

---

## Common Issues and Solutions

### Issue 1: SCTransform Fails

**Error:** "Model failed to converge"

**Solutions:**
1. Reduce dataset size temporarily for testing
2. Use LogNormalize workflow instead
3. Update Seurat to latest version
4. Check for extreme outlier cells

```r
# Fallback workflow
seurat_obj <- NormalizeData(seurat_obj)
seurat_obj <- FindVariableFeatures(seurat_obj)
seurat_obj <- ScaleData(seurat_obj)
```

### Issue 2: Clustering Separates by QC Metrics

**Symptom:** Clusters correlate with nFeature_RNA or percent.mt

**Solutions:**
1. Regress out QC metrics during normalization:
```r
seurat_obj <- SCTransform(seurat_obj, vars.to.regress = c("percent.mt", "nCount_RNA"))
```

2. Filter more stringently before analysis
3. Check for batch effects or sample quality issues

### Issue 3: No Clear Markers for Clusters

**Symptom:** FindAllMarkers returns few significant genes

**Solutions:**
1. Lower clustering resolution (may be over-clustering)
2. Check for doublets (use DoubletFinder)
3. Verify normalization completed correctly
4. Try different DE test:
```r
FindAllMarkers(seurat_obj, test.use = "MAST")  # Or "DESeq2", "LR"
```

### Issue 4: Memory Exhausted

**Solutions:**
1. Use sketch-based approach (Seurat v5):
```r
seurat_obj <- SketchData(seurat_obj, ncells = 50000)
```

2. Reduce number of variable features:
```r
seurat_obj <- SCTransform(seurat_obj, variable.features.n = 2000)
```

3. Use future package for parallelization:
```r
library(future)
plan("multicore", workers = 4)
```

### Issue 5: Batch Effects

**Symptom:** Cells cluster by sample/batch rather than biology

**Solutions:**
1. Include batch in SCTransform:
```r
seurat_obj <- SCTransform(seurat_obj, vars.to.regress = c("batch", "percent.mt"))
```

2. Use integration workflow (see integration-specific guide)
3. Use Harmony for batch correction

---

## Performance Optimization

### For Large Datasets (>50,000 cells)

**1. Use Seurat v5 Sketching:**
```r
seurat_obj <- SketchData(
  object = seurat_obj,
  ncells = 50000,
  method = "LeverageScore",
  sketched.assay = "sketch"
)
```

**2. Parallelize with future:**
```r
library(future)
plan("multicore", workers = 8)
options(future.globals.maxSize = 8000 * 1024^2)  # 8GB
```

**3. Limit variable features:**
```r
seurat_obj <- SCTransform(seurat_obj, variable.features.n = 2000)
```

### Memory Management

**Monitor memory usage:**
```r
# Check object size
object.size(seurat_obj) / 1024^3  # GB

# Clean up intermediate results
seurat_obj[["RNA"]]@scale.data <- matrix()  # Clear if not needed
gc()  # Force garbage collection
```

**Sparse matrices:**
- Seurat uses sparse matrices by default
- Don't convert to dense unless necessary
- Use RDS format for saving (preserves sparse structure)

### Speed Tips

1. **Skip unnecessary steps**: Don't run tSNE if only need UMAP
2. **Reduce PCs**: Use 20-30 instead of 50 if appropriate
3. **Limit marker genes**: Use `max.cells.per.ident` in FindAllMarkers
4. **Save intermediate objects**: Resume analysis without re-running

---

## Additional Resources

### Official Documentation
- Seurat vignettes: https://satijalab.org/seurat/articles/
- GitHub: https://github.com/satijalab/seurat
- Discussion forum: https://github.com/satijalab/seurat/discussions

### Key Papers
1. **Seurat v5**: Hao et al. (2024) Nat Biotechnol - Dictionary learning
2. **Seurat v4**: Hao et al. (2021) Cell - Integrated analysis
3. **SCTransform**: Hafemeister & Satija (2019) Genome Biol

### Related Workflows
- Integration: For multi-sample/batch correction
- Trajectory: For pseudotime and differentiation
- Spatial: For spatial transcriptomics with Seurat

---

**Last Updated:** January 2026
**Seurat Version:** 5.1.0
**R Version:** 4.4.0
