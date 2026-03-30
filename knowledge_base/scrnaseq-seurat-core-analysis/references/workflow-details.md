# Detailed Workflow Steps for scRNA-seq Analysis with Seurat

Complete code examples with parameters and options for each workflow step.

---

## Step 1: Ambient RNA Correction (Optional)

**When to use:** Raw CellRanger matrices or high-soup tissues (brain, lung, tumor)

### Full Example

```r
source("scripts/remove_ambient_rna.R")

# Run SoupX correction
seurat_obj <- run_soupx_correction(
  raw_matrix_dir = "raw_feature_bc_matrix/",
  filtered_matrix_dir = "filtered_feature_bc_matrix/",
  output_dir = "results/ambient",
  contamination_rate = NULL  # Auto-estimate (recommended)
)

# Alternative: Manually set contamination rate if auto-estimate fails
seurat_obj <- run_soupx_correction(
  raw_matrix_dir = "raw_feature_bc_matrix/",
  filtered_matrix_dir = "filtered_feature_bc_matrix/",
  output_dir = "results/ambient",
  contamination_rate = 0.1  # 10% contamination
)

# Estimate contamination fraction
contamination <- estimate_soup_fraction(seurat_obj)
cat(sprintf("Estimated ambient RNA: %.1f%%\n", contamination * 100))

# Visualize correction results
plot_soupx_results(seurat_obj, output_dir = "results/ambient")

# Compare before/after for key markers
compare_before_after_soupx(
  seurat_obj,
  markers = c("HBB", "HBA1"),  # Hemoglobin genes (common contaminants)
  output_dir = "results/ambient"
)
```

### Parameters

- `contamination_rate`: Auto-estimated (NULL) or manual (0.05-0.2)
- Typical contamination: PBMC 1-5%, Brain 10-20%, Tumor 5-15%

See [ambient_rna_correction.md](ambient_rna_correction.md) for detailed guidance.

---

## Step 2: Load Data and Calculate QC Metrics

### Load Data from Various Sources

```r
source("scripts/setup_and_import.R")
source("scripts/qc_metrics.R")

# Option A: 10X CellRanger directory
seurat_obj <- import_10x_data("path/to/filtered_feature_bc_matrix/")

# Option B: H5 file
seurat_obj <- import_h5_data("path/to/filtered_feature_bc_matrix.h5")

# Option C: Count matrix (CSV/TSV)
seurat_obj <- import_count_matrix(
  counts_file = "counts.csv",
  gene_col = 1,
  cell_col = 1
)

# Option D: SeuratData package
seurat_obj <- load_seurat_data("pbmc3k")

# Option E: Pre-existing Seurat object
seurat_obj <- readRDS("seurat_object.rds")
```

### Calculate QC Metrics

```r
# Calculate standard QC metrics
seurat_obj <- calculate_qc_metrics(
  seurat_obj,
  species = "human",  # or "mouse"
  mt_pattern = "^MT-",  # Human mitochondrial pattern
  rb_pattern = "^RP[SL]",  # Ribosomal pattern (optional)
  hb_pattern = "^HB[^(P)]"  # Hemoglobin pattern (optional)
)

# Metrics calculated:
# - nFeature_RNA: Number of genes detected
# - nCount_RNA: Total UMI counts
# - percent.mt: % mitochondrial genes
# - percent.rb: % ribosomal genes (if rb_pattern provided)
# - percent.hb: % hemoglobin genes (if hb_pattern provided)

# For mouse data
seurat_obj <- calculate_qc_metrics(
  seurat_obj,
  species = "mouse",
  mt_pattern = "^mt-"  # Mouse mitochondrial genes lowercase
)
```

### Batch-Aware MAD Outlier Detection

```r
# For multi-batch data
seurat_obj <- batch_mad_outlier_detection(
  seurat_obj,
  batch_col = "batch",
  metrics = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
  nmads = 5  # Number of MADs from median (5 = lenient, 3 = stringent)
)

# Creates column: outlier (TRUE/FALSE)
# Outliers are >nmads MADs away from batch-specific median

# Check outlier rates per batch
table(seurat_obj$batch, seurat_obj$outlier)
```

### Fixed Tissue-Specific Thresholds

```r
# For single batch or known tissue types
seurat_obj <- mark_outliers_fixed(
  seurat_obj,
  tissue = "pbmc"  # Options: pbmc, brain, tumor, lung, liver, kidney
)

# Custom thresholds
seurat_obj <- mark_outliers_fixed(
  seurat_obj,
  min_features = 200,
  max_features = 5000,
  max_mt_percent = 15
)
```

### Visualize QC

```r
source("scripts/plot_qc.R")

# Violin plots for all cells
plot_qc_violin(
  seurat_obj,
  batch_col = "batch",
  output_dir = "results/qc"
)

# Scatter plots (feature-count relationship)
plot_qc_scatter(
  seurat_obj,
  output_dir = "results/qc"
)

# Per-batch QC distributions
plot_qc_by_batch(
  seurat_obj,
  batch_col = "batch",
  output_dir = "results/qc"
)

# Histogram of each metric
plot_qc_histograms(
  seurat_obj,
  metrics = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
  output_dir = "results/qc"
)
```

---

## Step 3: Doublet Detection and Filtering

### Doublet Detection with DoubletFinder

```r
source("scripts/filter_cells.R")

# Run DoubletFinder (per batch if multi-batch)
seurat_obj <- run_doubletfinder(
  seurat_obj,
  batch_col = "batch",  # Run separately per batch
  expected_doublet_rate = 0.06,  # 6% (adjust based on loading)
  pcs = 1:30,
  pN = 0.25,  # Proportion of artificial doublets
  pK = NULL  # Auto-optimize (recommended)
)

# Expected doublet rates by cell loading:
# - 3k cells: 3% (0.03)
# - 5k cells: 4% (0.04)
# - 8k cells: 6% (0.06)
# - 10k cells: 8% (0.08)

# Creates column: doublet_finder_class (Singlet/Doublet)
# And: doublet_finder_score (0-1)

# Check doublet rates
table(seurat_obj$doublet_finder_class)
```

### Filter Cells

```r
# Option A: Filter by MAD outliers + doublets
seurat_obj_filtered <- filter_by_mad_outliers(
  seurat_obj,
  remove_doublets = TRUE
)

# Option B: Filter by fixed tissue thresholds + doublets
seurat_obj_filtered <- filter_cells_by_tissue(
  seurat_obj,
  tissue = "pbmc",
  remove_doublets = TRUE
)

# Option C: Custom filtering
seurat_obj_filtered <- subset(
  seurat_obj,
  subset = nFeature_RNA > 200 &
           nFeature_RNA < 5000 &
           percent.mt < 15 &
           doublet_finder_class == "Singlet"
)

# Check retention rate
cat(sprintf("Retained: %d/%d cells (%.1f%%)\n",
    ncol(seurat_obj_filtered),
    ncol(seurat_obj),
    100 * ncol(seurat_obj_filtered) / ncol(seurat_obj)))

# QC checkpoint: Aim for >70% retention
# If <70%, review thresholds
```

---

## Step 4: Normalize Data

### SCTransform (Recommended for UMI data)

```r
source("scripts/normalize_data.R")

# Standard SCTransform
seurat_obj <- run_sctransform(
  seurat_obj,
  vars_to_regress = c("percent.mt"),
  vst.flavor = "v2",  # Use v2 for Seurat v5
  n_genes = 3000,  # Number of variable genes
  min_cells = 5  # Gene must be in ≥5 cells
)

# With additional covariates
seurat_obj <- run_sctransform(
  seurat_obj,
  vars_to_regress = c("percent.mt", "S.Score", "G2M.Score"),  # Cell cycle
  vst.flavor = "v2"
)

# Creates assay: SCT
# Variable features automatically selected
```

### LogNormalize (Classic workflow)

```r
# Standard LogNormalize
seurat_obj <- run_lognormalize(
  seurat_obj,
  normalization.method = "LogNormalize",
  scale.factor = 10000
)

# Find variable features
seurat_obj <- find_hvgs(
  seurat_obj,
  selection.method = "vst",
  n_features = 2000
)

# Scale data
seurat_obj <- scale_data(
  seurat_obj,
  features = VariableFeatures(seurat_obj),
  vars_to_regress = c("percent.mt")
)

# Creates assay: RNA (normalized)
# Creates slot: scale.data
```

---

## Step 5: PCA and Determine Dimensionality

### Run PCA

```r
source("scripts/scale_and_pca.R")

# Run PCA on variable features
seurat_obj <- run_pca_analysis(
  seurat_obj,
  assay = "SCT",  # or "RNA" for LogNormalize
  n_pcs = 50,
  features = NULL  # NULL = use variable features
)

# Creates reduction: pca
```

### Determine Number of PCs

```r
# Option A: Elbow plot (visual inspection)
plot_elbow(
  seurat_obj,
  n_dims = 50,
  output_dir = "results/pca"
)
# Look for "elbow" where variance explained drops

# Option B: PCA heatmaps (top genes per PC)
plot_pca_heatmaps(
  seurat_obj,
  dims = 1:15,
  cells = 500,
  balanced = TRUE,
  output_dir = "results/pca"
)
# Check for biological signal vs noise

# Option C: PCA loadings (top contributing genes)
plot_pca_loadings(
  seurat_obj,
  dims = 1:4,
  n_features = 30,
  output_dir = "results/pca"
)

# Option D: Jackstraw (statistical, slow)
seurat_obj <- JackStraw(seurat_obj, num.replicate = 100, dims = 50)
seurat_obj <- ScoreJackStraw(seurat_obj, dims = 1:50)
JackStrawPlot(seurat_obj, dims = 1:50)

# Typical choice: 15-30 PCs (conservative: 30-40)
n_pcs <- 30
```

---

## Step 6: Batch Integration (Multi-Batch Only)

### Harmony Integration (Recommended)

```r
source("scripts/integrate_batches.R")

# Run Harmony
seurat_obj <- run_harmony_integration(
  seurat_obj,
  batch_var = "batch",
  dims_use = 1:30,
  theta = 2,  # Diversity clustering penalty (default: 2)
  lambda = 1,  # Ridge regression penalty (default: 1)
  sigma = 0.1,  # Width of soft k-means clusters (default: 0.1)
  max.iter.harmony = 10
)

# Creates reduction: harmony
# Use "harmony" for downstream clustering and UMAP
```

### Seurat CCA Integration

```r
# CCA integration (Seurat v5)
seurat_obj <- run_seurat_cca_integration(
  seurat_obj,
  batch_var = "batch",
  dims = 1:30,
  k.anchor = 5,  # Neighbors to use for finding anchors
  k.filter = 200,  # Neighbors to use for filtering anchors
  k.weight = 100  # Neighbors to use for weighting anchors
)

# Creates: integrated assay
# Use integrated assay for downstream analysis
```

### Seurat RPCA Integration

```r
# RPCA integration (faster, large datasets)
seurat_obj <- run_seurat_rpca_integration(
  seurat_obj,
  batch_var = "batch",
  dims = 1:30,
  k.anchor = 5
)

# Creates: integrated assay
```

### Validate Integration

```r
source("scripts/integration_diagnostics.R")

# Compute LISI (Local Inverse Simpson's Index)
lisi_scores <- compute_lisi_scores(
  seurat_obj,
  batch_var = "batch",
  label_var = "cell_type",  # If cell types known
  reduction = "harmony"  # or "pca" for integrated assay
)

# Batch LISI: Close to 1 = good mixing
# Cell type LISI: Close to # cell types = preserved biology

# Compute ASW (Average Silhouette Width)
asw_scores <- compute_asw_scores(
  seurat_obj,
  batch_var = "batch",
  label_var = "cell_type",
  reduction = "harmony"
)

# Batch ASW: Close to 0 = no batch separation
# Cell type ASW: Close to 1 = preserved cell type separation

# Visualize metrics
plot_integration_metrics(
  seurat_obj,
  lisi_scores,
  asw_scores,
  output_dir = "results/integration"
)

# Compare before/after
compare_integration_umap(
  seurat_obj,
  batch_var = "batch",
  reductions = c("pca", "harmony"),
  output_dir = "results/integration"
)
```

---

## Step 7: Clustering

### Graph-Based Clustering

```r
source("scripts/cluster_cells.R")

# Choose reduction based on integration
reduction <- if ("harmony" %in% names(seurat_obj@reductions)) "harmony" else "pca"

# Cluster at multiple resolutions
seurat_obj <- cluster_multiple_resolutions(
  seurat_obj,
  dims = 1:30,
  reduction = reduction,
  resolutions = c(0.4, 0.6, 0.8, 1.0),
  algorithm = 1,  # Louvain (default)
  k.param = 20  # Number of neighbors
)

# Algorithm options:
# 1 = Louvain (original)
# 2 = Louvain (refined)
# 3 = SLM (default in Seurat)
# 4 = Leiden (better than Louvain)

# Creates columns: RNA_snn_res.0.4, RNA_snn_res.0.6, etc.

# Set active resolution
Idents(seurat_obj) <- "RNA_snn_res.0.8"

# Check cluster sizes
table(seurat_obj$RNA_snn_res.0.8)
```

### Compare Resolutions

```r
# Visual comparison
plot_clustering_comparison(
  seurat_obj,
  resolutions = c(0.4, 0.6, 0.8, 1.0),
  output_dir = "results/clustering"
)

# Clustree (requires clustree package)
library(clustree)
clustree(seurat_obj, prefix = "RNA_snn_res.")
ggsave("results/clustering/clustree.png", width = 12, height = 10, dpi = 300)
```

---

## Step 8: UMAP and Visualization

### Run UMAP

```r
source("scripts/run_umap.R")

# Run UMAP on chosen reduction
seurat_obj <- run_umap_reduction(
  seurat_obj,
  dims = 1:30,
  reduction = reduction,  # "pca" or "harmony"
  n.neighbors = 30,
  min.dist = 0.3,
  metric = "cosine",
  spread = 1
)

# Creates reduction: umap
```

### Visualize Clustering

```r
source("scripts/plot_dimreduction.R")

# UMAP colored by clusters
plot_umap_clusters(
  seurat_obj,
  resolution = 0.8,
  output_dir = "results/umap"
)

# UMAP colored by batch (check integration)
plot_umap_by_batch(
  seurat_obj,
  batch_col = "batch",
  output_dir = "results/umap"
)

# UMAP colored by QC metrics (check for technical artifacts)
plot_feature_umap(
  seurat_obj,
  features = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
  output_dir = "results/umap"
)

# Feature plots for specific genes
plot_feature_umap(
  seurat_obj,
  features = c("CD3D", "CD8A", "CD4", "CD14", "MS4A1", "NKG7"),
  output_dir = "results/umap",
  ncol = 3
)
```

---

## Step 9: Find Marker Genes (Exploratory)

### Find All Cluster Markers

```r
source("scripts/find_markers.R")

# Find markers for all clusters (Wilcoxon rank sum test)
all_markers <- find_all_cluster_markers(
  seurat_obj,
  resolution = 0.8,
  test.use = "wilcox",  # Wilcoxon (fast, default)
  min.pct = 0.25,  # Gene must be detected in ≥25% of cells
  logfc.threshold = 0.25,  # Log2FC threshold
  only.pos = TRUE  # Only positive markers
)

# Alternative tests:
# - "wilcox": Wilcoxon rank sum (fast, default)
# - "bimod": Likelihood ratio test (slow)
# - "roc": ROC analysis (AUC)
# - "t": Student's t-test (assumes normality)
# - "negbinom": Negative binomial (DESeq2-like, very slow)
# - "poisson": Poisson (edgeR-like, slow)
# - "LR": Logistic regression (with covariates)

# Export marker tables
export_marker_tables(
  all_markers,
  output_dir = "results/markers",
  top_n = 50  # Top 50 markers per cluster
)
```

### Visualize Markers

```r
# Heatmap of top markers
plot_top_markers_heatmap(
  seurat_obj,
  all_markers,
  n_top = 10,
  output_dir = "results/markers"
)

# Dot plot of top markers
plot_markers_dotplot(
  seurat_obj,
  all_markers,
  n_top = 5,
  output_dir = "results/markers"
)

# Violin plots for specific markers
plot_markers_violin(
  seurat_obj,
  features = c("CD3D", "CD14", "MS4A1"),
  output_dir = "results/markers"
)
```

---

## Step 10: Annotate Cell Types

### Manual Annotation

```r
source("scripts/annotate_celltypes.R")

# Define annotations based on marker genes
annotations <- c(
  "0" = "CD4 T cells",
  "1" = "CD14+ Monocytes",
  "2" = "CD8 T cells",
  "3" = "B cells",
  "4" = "NK cells",
  "5" = "CD16+ Monocytes",
  "6" = "Dendritic cells",
  "7" = "Platelets"
)

# Apply annotations
seurat_obj <- annotate_clusters_manual(
  seurat_obj,
  annotations = annotations,
  resolution = 0.8,
  column_name = "cell_type"
)

# Creates column: cell_type

# Visualize annotated UMAP
plot_annotated_umap(
  seurat_obj,
  group_by = "cell_type",
  output_dir = "results/annotation"
)
```

### Automated Annotation with SingleR

```r
# Run SingleR
seurat_obj <- annotate_with_singler(
  seurat_obj,
  reference = "HPCA",  # Human Primary Cell Atlas
  species = "human"
)

# Reference options:
# - "HPCA": Human Primary Cell Atlas (broad)
# - "MonacoImmune": Monaco immune reference
# - "BlueprintEncode": Blueprint/ENCODE
# - "DatabaseImmuneCellExpression": DICE
# - Custom reference

# Compare automated vs manual
table(seurat_obj$cell_type, seurat_obj$singler_labels)
```

---

## Step 11: Pseudobulk Differential Expression (Multi-Sample)

### Aggregate to Pseudobulk

```r
source("scripts/pseudobulk_de.R")

# Aggregate counts per sample × cell type
pseudobulk_data <- aggregate_to_pseudobulk(
  seurat_obj,
  sample_col = "sample_id",
  celltype_col = "cell_type",
  min_cells = 10,  # Minimum cells per sample-celltype
  min_counts = 1,  # Minimum total counts
  min_samples = 2  # Minimum samples per cell type
)

# Returns list with:
# - counts: Pseudobulk count matrix
# - metadata: Sample metadata
# - summary: Cell counts per sample-celltype
```

### Run DESeq2 Per Cell Type

```r
# DESeq2 analysis
de_results <- run_pseudobulk_deseq2(
  pseudobulk_data,
  formula = "~ batch + condition",  # Include covariates
  contrast = c("condition", "treated", "control"),
  output_dir = "results/pseudobulk_de",
  alpha = 0.05,  # FDR threshold
  lfcThreshold = 0  # No LFC threshold for testing
)

# Returns list of DESeq2 results per cell type

# Export results
export_de_results(
  de_results,
  output_dir = "results/pseudobulk_de",
  fdr_threshold = 0.05,
  lfc_threshold = 1
)
```

### Visualize DE Results

```r
# Per cell type
for (celltype in names(de_results)) {
  # Volcano plot
  plot_volcano(
    de_results[[celltype]],
    celltype = celltype,
    padj_threshold = 0.05,
    fc_threshold = 1,
    output_dir = "results/pseudobulk_de"
  )

  # MA plot
  plot_ma(
    de_results[[celltype]],
    celltype = celltype,
    output_dir = "results/pseudobulk_de"
  )
}
```

---

## Step 12: Export Results

```r
source("scripts/export_results.R")

# Export all results
export_seurat_results(
  seurat_obj,
  output_dir = "results",
  resolution = 0.8,
  export_counts = TRUE,
  export_metadata = TRUE,
  export_dimreductions = TRUE
)

# Exports:
# - seurat_processed.rds: Complete Seurat object
# - normalized_counts.csv: Normalized expression
# - cell_metadata.csv: Cell annotations and QC
# - umap_coordinates.csv: UMAP coordinates
# - cluster_markers_all.csv: All marker genes
```

---

**Related Documentation:**
- [decision-guide.md](decision-guide.md) - Decision guidance for each step
- [common-patterns.md](common-patterns.md) - Complete analysis patterns
- [seurat_best_practices.md](seurat_best_practices.md) - Best practices
- [troubleshooting_guide.md](troubleshooting_guide.md) - Common issues


---
