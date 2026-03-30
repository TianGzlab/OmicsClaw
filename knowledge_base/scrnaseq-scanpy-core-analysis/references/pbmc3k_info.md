# PBMC 3k Dataset Information

Standard test dataset for scRNA-seq analysis with Seurat.

---

## Dataset Overview

**Name:** Peripheral Blood Mononuclear Cells (PBMC) 3k

**Source:** 10X Genomics

**Technology:** 10X Chromium Single Cell 3' v1

**Sample:** Healthy donor peripheral blood

**Cells:** ~2,700 cells

**URL:** https://cf.10xgenomics.com/samples/cell/pbmc3k/pbmc3k_filtered_gene_bc_matrices.tar.gz

---

## Quick Start

### Option 1: Load from SeuratData Package

**Installation:**
```r
# Install SeuratData
if (!requireNamespace("remotes", quietly = TRUE)) {
  install.packages("remotes")
}
remotes::install_github("satijalab/seurat-data")

# Install pbmc3k dataset
library(SeuratData)
InstallData("pbmc3k")
```

**Usage:**
```r
library(Seurat)
library(SeuratData)

# Load pre-processed dataset
data("pbmc3k")
seurat_obj <- pbmc3k

# Or load and analyze from scratch
source("scripts/setup_and_import.R")
setup_seurat_libraries()
seurat_obj <- load_seurat_data("pbmc3k", type = "filtered")
```

### Option 2: Download from 10X Genomics

**Download and extract:**
```bash
# Download
wget https://cf.10xgenomics.com/samples/cell/pbmc3k/pbmc3k_filtered_gene_bc_matrices.tar.gz

# Extract
tar -xzf pbmc3k_filtered_gene_bc_matrices.tar.gz
```

**Load in R:**
```r
source("scripts/setup_and_import.R")
setup_seurat_libraries()

# Load from extracted directory
seurat_obj <- import_10x_data("filtered_gene_bc_matrices/hg19/")
```

---

## Expected Cell Types

This dataset contains the major immune cell populations found in peripheral blood:

### Cell Type Composition

| Cell Type | Approximate % | Key Markers |
|-----------|--------------|-------------|
| **CD4+ T cells** | ~40% | CD3D, CD3E, IL7R, CD4 |
| **CD8+ T cells** | ~20% | CD3D, CD3E, CD8A, CD8B |
| **B cells** | ~15% | MS4A1 (CD20), CD79A |
| **NK cells** | ~10% | GNLY, NKG7, GZMB |
| **CD14+ Monocytes** | ~10% | CD14, LYZ, S100A8 |
| **FCGR3A+ Monocytes** | ~3% | FCGR3A (CD16), MS4A7 |
| **Dendritic cells** | ~2% | FCER1A, CST3 |

---

## Expected QC Metrics

### Quality Control Thresholds

**Recommended thresholds:**
- nFeature_RNA: 200 - 2,500 genes
- percent.mt: < 5%

**Expected distributions:**
- Median genes per cell: ~900
- Median UMIs per cell: ~2,500
- Mean % mitochondrial: ~3%

### Filtering Results

With standard thresholds, expect to retain:
- **~2,600-2,700 cells** (>95% retention)
- Very clean dataset, minimal filtering needed

---

## Expected Analysis Results

### Clustering

**At resolution 0.5:**
- **~7-9 clusters** representing major cell types

**At resolution 0.8:**
- **~9-11 clusters** with some T cell subtypes separated

**At resolution 1.0:**
- **~11-13 clusters** with fine-grained separation

### Dimensionality

**PCs to use:**
- Elbow at ~10-15 PCs
- Recommended: Use 20-30 PCs for clustering

### Variable Features

**Expected HVGs:**
- ~2,000 variable genes
- Top genes include: S100A8, S100A9, LYZ, HLA genes, immunoglobulins

---

## Complete Analysis Example

```r
# Load libraries
source("scripts/setup_and_import.R")
source("scripts/qc_metrics.R")
source("scripts/plot_qc.R")
source("scripts/filter_cells.R")
source("scripts/normalize_data.R")
source("scripts/scale_and_pca.R")
source("scripts/cluster_cells.R")
source("scripts/run_umap.R")
source("scripts/plot_dimreduction.R")
source("scripts/find_markers.R")
source("scripts/annotate_celltypes.R")
source("scripts/export_results.R")

setup_seurat_libraries()

# 1. Load data
seurat_obj <- load_seurat_data("pbmc3k")

# 2. QC
seurat_obj <- calculate_qc_metrics(seurat_obj, species = "human")
plot_qc_violin(seurat_obj, output_dir = "results/qc")
plot_qc_scatter(seurat_obj, output_dir = "results/qc")

# 3. Filter
seurat_obj <- filter_cells_by_qc(
  seurat_obj,
  min_features = 200,
  max_features = 2500,
  max_mt_percent = 5
)

# 4. Normalize (SCTransform)
seurat_obj <- run_sctransform(seurat_obj, vars_to_regress = c("percent.mt"))

# 5. PCA
seurat_obj <- run_pca_analysis(seurat_obj, n_pcs = 50)
plot_elbow(seurat_obj, output_dir = "results/pca")

# 6. Cluster
seurat_obj <- cluster_multiple_resolutions(
  seurat_obj,
  dims = 1:30,
  resolutions = c(0.4, 0.6, 0.8, 1.0)
)

# Set resolution 0.8 as default
Idents(seurat_obj) <- "RNA_snn_res.0.8"

# 7. UMAP
seurat_obj <- run_umap_reduction(seurat_obj, dims = 1:30)
plot_umap_clusters(seurat_obj, output_dir = "results/umap")

# 8. Find markers
all_markers <- find_all_cluster_markers(seurat_obj, resolution = 0.8)
export_marker_tables(all_markers, output_dir = "results/markers")
plot_top_markers_heatmap(seurat_obj, all_markers, output_dir = "results/markers")

# 9. Annotate
annotations <- c(
  "0" = "CD4 T cells",
  "1" = "CD14+ Monocytes",
  "2" = "CD8 T cells",
  "3" = "B cells",
  "4" = "NK cells",
  "5" = "FCGR3A+ Monocytes",
  "6" = "Dendritic cells",
  "7" = "Megakaryocytes"
)

seurat_obj <- annotate_clusters_manual(seurat_obj, annotations, resolution = 0.8)
plot_annotated_umap(seurat_obj, output_dir = "results/annotation")

# 10. Export
export_seurat_results(seurat_obj, output_dir = "pbmc3k_results", resolution = 0.8)
```

---

## Expected Runtime

**On standard laptop (16GB RAM, 4 cores):**
- Data loading: <1 min
- QC and filtering: <1 min
- SCTransform: 2-5 min
- PCA: <1 min
- Clustering: <1 min
- UMAP: 1-2 min
- Marker finding: 2-5 min
- **Total: ~15-20 minutes**

---

## Alternative Test Datasets

### PBMC 8k (Larger)

**Source:** 10X Genomics (8,000 cells)
**Use case:** Testing performance on medium-sized datasets

### IFNB Dataset

**Source:** SeuratData package
**Cells:** ~13,999 cells (control + IFN-β stimulated)
**Use case:** Testing integration and differential expression between conditions

```r
InstallData("ifnb")
data("ifnb")
```

### PBMC 33k (Large)

**Source:** 10X Genomics (33,000 cells)
**Use case:** Testing sketch-based methods and large-scale analysis

---

## Troubleshooting

### Issue: Can't install SeuratData

**Solution:**
```r
remotes::install_github("satijalab/seurat-data", force = TRUE)
```

### Issue: pbmc3k dataset download fails

**Solution:** Download manually from 10X Genomics website
```r
# Use direct 10X data loading
seurat_obj <- import_10x_data("path/to/filtered_gene_bc_matrices/hg19/")
```

### Issue: Different results than expected

**Possible causes:**
- Different Seurat version (results may vary slightly)
- Different random seed (clustering, UMAP)
- Different parameters used

**Solution:** Set random seed for reproducibility
```r
set.seed(42)
```

---

## References

1. **Dataset source**: 10X Genomics. (2016). 2,700 Peripheral blood mononuclear cells (PBMCs) from a healthy donor. Retrieved from https://www.10xgenomics.com/resources/datasets/

2. **Seurat tutorial**: Satija Lab. PBMC 3k guided tutorial. https://satijalab.org/seurat/articles/pbmc3k_tutorial.html

3. **Original technology paper**: Zheng GXY et al. (2017). Massively parallel digital transcriptional profiling of single cells. *Nat Commun* 8, 14049.

---

**Last Updated:** January 2026
**Dataset Version:** v1 (2016)
**Genome:** GRCh37/hg19
