# Seurat Troubleshooting Guide

Common issues and solutions for scRNA-seq analysis with Seurat.

---

## Common Errors

### Error: "Cannot find 10X files"

**Symptoms:**
```
Error in Read10X: No such file or directory
```

**Solutions:**
1. Verify you're pointing to the directory containing the three required files:
   - `barcodes.tsv.gz` (or `.tsv`)
   - `features.tsv.gz` (or `genes.tsv.gz` for older versions)
   - `matrix.mtx.gz` (or `.mtx`)

2. Check file structure:
```r
list.files("path/to/filtered_feature_bc_matrix/")
# Should show: barcodes.tsv.gz, features.tsv.gz, matrix.mtx.gz
```

3. Ensure you're not pointing to the parent directory or a compressed file

---

### Error: "SCTransform failed"

**Symptoms:**
```
Error in sctransform::vst: Model failed to converge
```

**Causes:**
- Very small dataset (<500 cells)
- Extreme outlier cells
- Very sparse data
- Insufficient memory

**Solutions:**

**Option 1: Use LogNormalize workflow instead**
```r
seurat_obj <- run_lognormalize(seurat_obj)
source("scripts/find_variable_features.R")
seurat_obj <- find_hvgs(seurat_obj, n_features = 2000)
seurat_obj <- scale_data(seurat_obj)
```

**Option 2: Filter more stringently**
```r
# Remove extreme outliers
seurat_obj <- subset(seurat_obj,
  subset = nFeature_RNA > 500 & nFeature_RNA < 5000 & percent.mt < 10)
```

**Option 3: Update Seurat**
```r
# Update to latest version
install.packages("Seurat")
```

**Option 4: Reduce dataset size temporarily**
```r
# Subsample for testing
cells_subset <- sample(colnames(seurat_obj), size = min(2000, ncol(seurat_obj)))
seurat_test <- subset(seurat_obj, cells = cells_subset)
seurat_test <- run_sctransform(seurat_test)
```

---

### Warning: "Did not converge"

**Symptoms:**
```
Warning: Algorithm did not converge
```

**Context:** Usually during clustering (`FindClusters`)

**When to worry:**
- Generally safe to ignore for clustering
- Doesn't affect downstream analysis significantly

**Solutions if persistent:**
1. Try different clustering algorithm:
```r
seurat_obj <- FindClusters(seurat_obj, algorithm = 2)  # Louvain (default = 1)
```

2. Adjust resolution:
```r
seurat_obj <- FindClusters(seurat_obj, resolution = 0.5)  # Lower resolution
```

---

### Error: "Memory exhausted"

**Symptoms:**
```
Error: cannot allocate vector of size X GB
```

**Solutions:**

**1. Increase R memory limit (Windows)**
```r
memory.limit(size = 16000)  # 16GB
```

**2. Use sketch-based approach (Seurat v5)**
```r
seurat_obj <- SketchData(seurat_obj, ncells = 50000, method = "LeverageScore")
```

**3. Reduce variable features**
```r
seurat_obj <- SCTransform(seurat_obj, variable.features.n = 2000)  # Default: 3000
```

**4. Clear scale.data if not needed**
```r
# After PCA
seurat_obj[["RNA"]]@scale.data <- matrix()
gc()  # Force garbage collection
```

**5. Use future package for better memory management**
```r
library(future)
plan("multicore", workers = 4)
options(future.globals.maxSize = 8000 * 1024^2)  # 8GB
```

---

## Analysis Issues

### Issue: Clustering separates by QC metrics

**Symptoms:**
- Clusters correlate strongly with `nFeature_RNA`, `nCount_RNA`, or `percent.mt`
- Plot QC metrics on UMAP shows clear separation

**Diagnosis:**
```r
# Check if QC drives clustering
plot_feature_umap(seurat_obj, features = c("nFeature_RNA", "percent.mt"))
```

**Solutions:**

**1. Regress out QC metrics during normalization**
```r
seurat_obj <- SCTransform(seurat_obj,
  vars.to.regress = c("percent.mt", "nCount_RNA"))
```

**2. Filter more stringently before analysis**
```r
# Tighter QC thresholds
seurat_obj <- filter_cells_by_qc(
  seurat_obj,
  min_features = 500,    # Higher minimum
  max_features = 4000,   # Lower maximum
  max_mt_percent = 3     # More stringent
)
```

**3. Check for batch effects**
```r
# If you have sample/batch info
plot_split_umap(seurat_obj, split_by = "batch")
```

---

### Issue: No clear marker genes for clusters

**Symptoms:**
- `FindAllMarkers` returns very few significant genes
- Markers have low fold changes
- No biological interpretation possible

**Causes:**
- Over-clustering (too many small clusters)
- Doublets mixed with singlets
- Poor quality data
- Insufficient normalization

**Solutions:**

**1. Lower clustering resolution**
```r
seurat_obj <- cluster_seurat(seurat_obj, dims = 1:30, resolution = 0.4)
```

**2. Check for doublets**
```r
library(DoubletFinder)
# Run doublet detection (see references/best_practices.md)
```

**3. Try different DE test**
```r
markers <- FindAllMarkers(seurat_obj,
  test.use = "MAST",      # More sensitive
  min.pct = 0.1,          # Lower threshold
  logfc.threshold = 0.1)
```

**4. Verify normalization**
```r
# Check if normalized
if (!"data" %in% slotNames(seurat_obj[["RNA"]])) {
  message("Data not normalized!")
}
```

---

### Issue: Poor cluster separation in UMAP

**Symptoms:**
- Clusters overlap heavily
- No clear structure
- Looks like a blob

**Solutions:**

**1. Use more PCs**
```r
# Try 40-50 PCs instead of 20-30
seurat_obj <- FindNeighbors(seurat_obj, dims = 1:40)
seurat_obj <- FindClusters(seurat_obj, resolution = 0.8)
seurat_obj <- run_umap_reduction(seurat_obj, dims = 1:40)
```

**2. Adjust UMAP parameters**
```r
seurat_obj <- RunUMAP(seurat_obj,
  dims = 1:30,
  n.neighbors = 15,     # Lower (default: 30)
  min.dist = 0.1)       # Lower (default: 0.3)
```

**3. Check if PCA captured structure**
```r
# If PCA also shows no separation, issue is earlier
plot_pca_clusters(seurat_obj, dims = c(1, 2))
```

---

### Issue: High doublet rate

**Symptoms:**
- Clusters express markers from multiple cell types
- Cells with very high gene counts
- Intermediate expression states

**Detection:**
```r
library(DoubletFinder)

# Optimize parameters
sweep_res <- paramSweep_v3(seurat_obj, PCs = 1:20)
sweep_stats <- summarizeSweep(sweep_res, GT = FALSE)
bcmvn <- find.pK(sweep_stats)

# Run DoubletFinder
optimal_pK <- bcmvn$pK[which.max(bcmvn$BCmetric)]
expected_doublets <- 0.08 * ncol(seurat_obj)  # 8% for 10k cells

seurat_obj <- doubletFinder_v3(
  seurat_obj,
  PCs = 1:20,
  pN = 0.25,
  pK = as.numeric(as.character(optimal_pK)),
  nExp = expected_doublets
)
```

**Remove doublets:**
```r
# Filter out predicted doublets
seurat_obj <- subset(seurat_obj,
  subset = DF.classifications == "Singlet")
```

---

### Issue: Batch effects

**Symptoms:**
- Cells cluster by sample/batch rather than cell type
- UMAP shows sample-specific clusters
- Same cell types separate by batch

**Diagnosis:**
```r
# Color UMAP by batch
plot_split_umap(seurat_obj, split_by = "batch")
```

**Solutions:**

**1. Regress out batch in normalization**
```r
seurat_obj <- SCTransform(seurat_obj,
  vars.to.regress = c("batch", "percent.mt"))
```

**2. Use Harmony for batch correction**
```r
library(harmony)
seurat_obj <- RunHarmony(seurat_obj,
  group.by.vars = "batch",
  dims.use = 1:30)

# Use harmony reduction for downstream
seurat_obj <- FindNeighbors(seurat_obj, reduction = "harmony", dims = 1:30)
seurat_obj <- FindClusters(seurat_obj)
seurat_obj <- RunUMAP(seurat_obj, reduction = "harmony", dims = 1:30)
```

**3. Use Seurat integration (for multiple samples)**
```r
# See integration workflow (separate guide)
```

---

## Performance Issues

### Issue: Analysis is very slow

**For datasets >50,000 cells:**

**1. Use Seurat v5 sketch-based analysis**
```r
seurat_obj <- SketchData(
  object = seurat_obj,
  ncells = 50000,
  method = "LeverageScore"
)
```

**2. Parallelize with future**
```r
library(future)
plan("multicore", workers = 8)  # Use 8 cores
```

**3. Reduce resolution of intensive steps**
```r
# Fewer PCs
seurat_obj <- RunPCA(seurat_obj, npcs = 30)  # Instead of 50

# Fewer variable features
seurat_obj <- SCTransform(seurat_obj, variable.features.n = 2000)
```

---

### Issue: Specific functions hang/freeze

**Function-specific solutions:**

**JackStraw (very slow):**
```r
# Skip JackStraw, use elbow plot instead
plot_elbow(seurat_obj)
```

**FindAllMarkers (slow for many cells):**
```r
# Limit cells per cluster
markers <- FindAllMarkers(seurat_obj, max.cells.per.ident = 500)

# Or use faster test
markers <- FindAllMarkers(seurat_obj, test.use = "wilcox")  # Fastest
```

---

## Installation Issues

### Issue: Cannot install Seurat

**Solution for various systems:**

**Mac with Apple Silicon:**
```r
# Install from source if binary fails
install.packages("Seurat", type = "source")
```

**Missing system dependencies (Linux):**
```bash
# Ubuntu/Debian
sudo apt-get install libhdf5-dev libgeos-dev libproj-dev

# CentOS/RHEL
sudo yum install hdf5-devel geos-devel proj-devel
```

---

### Issue: Cannot install SeuratData

**Solution:**
```r
# Use remotes instead of devtools
if (!requireNamespace("remotes", quietly = TRUE))
  install.packages("remotes")

remotes::install_github("satijalab/seurat-data", force = TRUE)
```

---

## Data Quality Issues

### Issue: Very few cells after filtering

**Diagnosis:**
```r
# Check how many cells were removed
message("Before filtering: ", ncol(seurat_obj_raw))
message("After filtering: ", ncol(seurat_obj_filtered))
message("% retained: ",
  round(ncol(seurat_obj_filtered) / ncol(seurat_obj_raw) * 100, 1), "%")
```

**If <50% retained:**

1. **Relax thresholds:**
```r
seurat_obj <- filter_cells_by_qc(
  seurat_obj,
  min_features = 200,   # Don't go lower
  max_features = 6000,  # Higher
  max_mt_percent = 15   # More permissive
)
```

2. **Check sample quality:**
- May indicate sample degradation
- Check experimental protocol
- Consider repeating experiment

---

### Issue: Cells have very low UMI counts

**Expected counts by technology:**
- 10X v2: 2,000-5,000 UMIs/cell
- 10X v3: 5,000-20,000 UMIs/cell
- Drop-seq: 1,000-3,000 UMIs/cell

**If much lower:**
- Check sequencing depth
- Verify sample preparation
- May need to re-sequence

---

## Getting Help

### Before asking for help:

1. Check Seurat version:
```r
packageVersion("Seurat")
```

2. Save session info:
```r
sessionInfo()
```

3. Create reproducible example:
```r
# Use pbmc3k test dataset
library(SeuratData)
data("pbmc3k")
# ... demonstrate your issue
```

### Where to get help:

- **Seurat GitHub Discussions**: https://github.com/satijalab/seurat/discussions
- **Seurat GitHub Issues**: https://github.com/satijalab/seurat/issues
- **Bioconductor Support**: https://support.bioconductor.org/
- **Biostars**: https://www.biostars.org/

---

**Last Updated:** January 2026
**Seurat Version:** 5.1.0
