# Common Analysis Patterns for scRNA-seq with Seurat

Complete code examples for frequent single-cell RNA-seq analysis scenarios.

---

## Pattern 1: Standard 10X PBMC Analysis (Single Sample)

**Use case:** Analyze one 10X PBMC sample from filtered CellRanger output.

### Complete Workflow

```r
# Load libraries
source("scripts/setup_and_import.R")
source("scripts/qc_metrics.R")
source("scripts/filter_cells.R")
source("scripts/normalize_data.R")
source("scripts/scale_and_pca.R")
source("scripts/cluster_cells.R")
source("scripts/run_umap.R")
source("scripts/find_markers.R")
source("scripts/annotate_celltypes.R")
source("scripts/plot_dimreduction.R")

# Step 1: Load data
seurat_obj <- import_10x_data("filtered_feature_bc_matrix/")

# Step 2: Calculate QC metrics
seurat_obj <- calculate_qc_metrics(seurat_obj, species = "human")

# Visualize QC
plot_qc_violin(seurat_obj, output_dir = "results/qc")
plot_qc_scatter(seurat_obj, output_dir = "results/qc")

# Step 3: Doublet detection and filtering
seurat_obj <- run_doubletfinder(
  seurat_obj,
  expected_doublet_rate = 0.06,
  pcs = 1:30
)

# Filter by fixed PBMC thresholds
seurat_obj <- filter_cells_by_tissue(
  seurat_obj,
  tissue = "pbmc",
  remove_doublets = TRUE
)

cat(sprintf("Retained %d/%d cells (%.1f%%)\n",
    ncol(seurat_obj), ncol(seurat_obj_prefilt),
    100 * ncol(seurat_obj) / ncol(seurat_obj_prefilt)))

# Step 4: Normalize with SCTransform
seurat_obj <- run_sctransform(
  seurat_obj,
  vars_to_regress = c("percent.mt")
)

# Step 5: PCA
seurat_obj <- run_pca_analysis(seurat_obj, n_pcs = 50)
plot_elbow(seurat_obj, output_dir = "results/pca")

# Determine number of PCs (e.g., 30)
n_pcs <- 30

# Step 6: Clustering at multiple resolutions
seurat_obj <- cluster_multiple_resolutions(
  seurat_obj,
  dims = 1:n_pcs,
  reduction = "pca",
  resolutions = c(0.4, 0.6, 0.8, 1.0)
)

# Step 7: UMAP
seurat_obj <- run_umap_reduction(seurat_obj, dims = 1:n_pcs)

# Visualize clustering at different resolutions
plot_clustering_comparison(
  seurat_obj,
  resolutions = c(0.4, 0.6, 0.8, 1.0),
  output_dir = "results/umap"
)

# Step 8: Find markers at chosen resolution (0.8)
Idents(seurat_obj) <- "RNA_snn_res.0.8"
all_markers <- find_all_cluster_markers(
  seurat_obj,
  resolution = 0.8,
  min_pct = 0.25,
  logfc_threshold = 0.25
)

# Export and visualize markers
export_marker_tables(all_markers, output_dir = "results/markers")
plot_top_markers_heatmap(seurat_obj, all_markers, n_top = 10,
                         output_dir = "results/markers")

# Step 9: Annotate clusters manually
pbmc_annotations <- c(
  "0" = "CD4 T cells",
  "1" = "CD14+ Monocytes",
  "2" = "CD8 T cells",
  "3" = "B cells",
  "4" = "NK cells",
  "5" = "CD16+ Monocytes",
  "6" = "Dendritic cells",
  "7" = "Platelets"
)

seurat_obj <- annotate_clusters_manual(
  seurat_obj,
  annotations = pbmc_annotations,
  resolution = 0.8
)

# Visualize annotated UMAP
plot_annotated_umap(seurat_obj, output_dir = "results/annotation")

# Feature plots for key markers
plot_feature_umap(
  seurat_obj,
  features = c("CD3D", "CD8A", "CD4", "CD14", "FCGR3A", "MS4A1", "NKG7", "PPBP"),
  output_dir = "results/umap"
)

# Step 10: Export results
export_seurat_results(
  seurat_obj,
  output_dir = "results",
  resolution = 0.8,
  export_counts = TRUE,
  export_metadata = TRUE,
  export_dimreductions = TRUE
)
```

---

## Pattern 2: Multi-Batch PBMC with Harmony Integration

**Use case:** Analyze multiple PBMC samples from different batches/donors.

### Complete Workflow

```r
# Load all libraries
source("scripts/setup_and_import.R")
source("scripts/qc_metrics.R")
source("scripts/filter_cells.R")
source("scripts/normalize_data.R")
source("scripts/scale_and_pca.R")
source("scripts/integrate_batches.R")
source("scripts/integration_diagnostics.R")
source("scripts/cluster_cells.R")
source("scripts/run_umap.R")
source("scripts/find_markers.R")
source("scripts/annotate_celltypes.R")

# Step 1: Load multiple samples
sample_dirs <- c(
  "sample1/filtered_feature_bc_matrix/",
  "sample2/filtered_feature_bc_matrix/",
  "sample3/filtered_feature_bc_matrix/"
)

seurat_list <- lapply(sample_dirs, function(dir) {
  import_10x_data(dir)
})

# Merge samples
seurat_obj <- merge(
  seurat_list[[1]],
  y = seurat_list[2:length(seurat_list)],
  add.cell.ids = c("sample1", "sample2", "sample3")
)

# Add batch metadata
seurat_obj$batch <- sapply(
  strsplit(colnames(seurat_obj), "_"),
  function(x) x[1]
)

# Step 2: Batch-aware MAD QC
seurat_obj <- calculate_qc_metrics(seurat_obj, species = "human")
seurat_obj <- batch_mad_outlier_detection(
  seurat_obj,
  batch_col = "batch",
  metrics = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
  nmads = 5
)

# Visualize QC per batch
plot_qc_by_batch(seurat_obj, batch_col = "batch", output_dir = "results/qc")

# Step 3: Doublet detection per batch
seurat_obj <- run_doubletfinder(
  seurat_obj,
  batch_col = "batch",
  expected_doublet_rate = 0.06
)

# Filter
seurat_obj <- filter_by_mad_outliers(
  seurat_obj,
  remove_doublets = TRUE
)

# Step 4: Normalize with SCTransform
seurat_obj <- run_sctransform(
  seurat_obj,
  vars_to_regress = c("percent.mt")
)

# Step 5: PCA
seurat_obj <- run_pca_analysis(seurat_obj, n_pcs = 50)

# Check for batch effects BEFORE integration
plot_pca_batch(seurat_obj, batch_col = "batch", output_dir = "results/pca")

# Step 6: Harmony integration
seurat_obj <- run_harmony_integration(
  seurat_obj,
  batch_var = "batch",
  dims_use = 1:30
)

# Validate integration with LISI
lisi_scores <- compute_lisi_scores(
  seurat_obj,
  batch_var = "batch",
  reduction = "harmony"
)

# Plot integration quality
plot_integration_metrics(
  seurat_obj,
  lisi_scores,
  output_dir = "results/integration"
)

# Compare before/after integration
compare_integration_umap(
  seurat_obj,
  batch_var = "batch",
  reductions = c("pca", "harmony"),
  output_dir = "results/integration"
)

# Step 7: Cluster on integrated space
seurat_obj <- cluster_multiple_resolutions(
  seurat_obj,
  dims = 1:30,
  reduction = "harmony",
  resolutions = c(0.4, 0.6, 0.8, 1.0)
)

# Step 8: UMAP on integrated space
seurat_obj <- run_umap_reduction(
  seurat_obj,
  dims = 1:30,
  reduction = "harmony"
)

# Visualize by batch and clusters
plot_umap_by_batch(seurat_obj, batch_col = "batch", output_dir = "results/umap")
plot_umap_clusters(seurat_obj, output_dir = "results/umap")

# Step 9: Find markers and annotate
Idents(seurat_obj) <- "RNA_snn_res.0.8"
all_markers <- find_all_cluster_markers(seurat_obj, resolution = 0.8)

seurat_obj <- annotate_clusters_manual(
  seurat_obj,
  annotations = pbmc_annotations,
  resolution = 0.8
)

# Step 10: Export
export_seurat_results(
  seurat_obj,
  output_dir = "results",
  resolution = 0.8
)
```

---

## Pattern 3: Brain Tissue with Raw Data (Ambient RNA Correction)

**Use case:** Analyze brain tissue starting from raw CellRanger output.

### Complete Workflow

```r
source("scripts/remove_ambient_rna.R")
source("scripts/setup_and_import.R")
# ... other scripts

# Step 1: Ambient RNA correction
seurat_obj <- run_soupx_correction(
  raw_matrix_dir = "raw_feature_bc_matrix/",
  filtered_matrix_dir = "filtered_feature_bc_matrix/",
  output_dir = "results/ambient"
)

# Estimate contamination
contamination <- estimate_soup_fraction(seurat_obj)
cat(sprintf("Estimated contamination: %.1f%%\n", contamination * 100))

# Visualize correction
plot_soupx_results(seurat_obj, output_dir = "results/ambient")

# Step 2: QC with brain-specific thresholds
seurat_obj <- calculate_qc_metrics(seurat_obj, species = "human")
seurat_obj <- mark_outliers_fixed(seurat_obj, tissue = "brain")

# Brain allows higher MT% (up to 10%)
plot_qc_violin(seurat_obj, output_dir = "results/qc")

# Step 3: Filter
seurat_obj <- run_doubletfinder(seurat_obj)
seurat_obj <- filter_cells_by_tissue(
  seurat_obj,
  tissue = "brain",
  remove_doublets = TRUE
)

# Continue with standard workflow (Steps 4-10 as in Pattern 1)
# ...
```

---

## Pattern 4: Condition Comparison with Pseudobulk DE

**Use case:** Compare treated vs control samples across multiple donors.

### Complete Workflow

```r
# Prerequisites: Completed clustering and annotation (Patterns 1-3)
# seurat_obj should have:
#   - sample_id: Unique identifier per sample
#   - condition: "treated" or "control"
#   - cell_type: Cell type annotations
#   - donor_id: Donor identifier (if paired)

source("scripts/pseudobulk_de.R")

# Step 1: Aggregate to pseudobulk
pseudobulk_data <- aggregate_to_pseudobulk(
  seurat_obj,
  sample_col = "sample_id",
  celltype_col = "cell_type",
  min_cells = 10,  # Minimum 10 cells per sample-celltype
  min_counts = 1
)

# Check sample distribution
print(pseudobulk_data$sample_metadata)

# Step 2: Run DESeq2 per cell type
de_results <- run_pseudobulk_deseq2(
  pseudobulk_data,
  formula = "~ donor_id + condition",  # Include donor as covariate if paired
  contrast = c("condition", "treated", "control"),
  output_dir = "results/pseudobulk_de"
)

# Step 3: Export results
export_de_results(de_results, output_dir = "results/pseudobulk_de")

# Step 4: Visualize per cell type
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

# Step 5: Summarize significant genes
significant_summary <- lapply(de_results, function(res) {
  sig <- res[res$padj < 0.05 & abs(res$log2FoldChange) > 1, ]
  data.frame(
    n_sig = nrow(sig),
    n_up = sum(sig$log2FoldChange > 1),
    n_down = sum(sig$log2FoldChange < -1)
  )
})

significant_df <- do.call(rbind, significant_summary)
significant_df$celltype <- rownames(significant_df)
write.csv(significant_df, "results/pseudobulk_de/significant_summary.csv")

# Step 6: Functional enrichment (optional, use functional-enrichment-from-degs)
# For each cell type with significant genes, run enrichment analysis
for (celltype in names(de_results)) {
  sig_genes <- de_results[[celltype]][
    de_results[[celltype]]$padj < 0.05 & abs(de_results[[celltype]]$log2FoldChange) > 1,
  ]

  if (nrow(sig_genes) > 10) {
    # Export for enrichment analysis
    write.csv(
      sig_genes,
      paste0("results/pseudobulk_de/", celltype, "_for_enrichment.csv")
    )
  }
}
```

---

## Pattern 5: Automated Annotation with SingleR

**Use case:** Quickly annotate standard tissue types without manual marker review.

### Complete Workflow

```r
source("scripts/annotate_celltypes.R")

# After clustering (Step 7-8 from Pattern 1)

# Option A: Use Human Primary Cell Atlas (broad)
seurat_obj <- annotate_with_singler(
  seurat_obj,
  reference = "HPCA",
  species = "human"
)

# Option B: Use Monaco Immune reference (immune-focused)
seurat_obj <- annotate_with_singler(
  seurat_obj,
  reference = "MonacoImmune",
  species = "human"
)

# Option C: Use Blueprint/ENCODE (general)
seurat_obj <- annotate_with_singler(
  seurat_obj,
  reference = "BlueprintEncode",
  species = "human"
)

# Visualize automated annotations
plot_annotated_umap(
  seurat_obj,
  group_by = "singler_labels",
  output_dir = "results/annotation"
)

# Compare automated vs cluster identity
table(seurat_obj$RNA_snn_res.0.8, seurat_obj$singler_labels)

# Manual validation: Check if automated labels make sense
# Find markers for each automated cell type
Idents(seurat_obj) <- "singler_labels"
auto_markers <- find_all_cluster_markers(seurat_obj)

# Review top markers for each cell type
export_marker_tables(auto_markers, output_dir = "results/markers_automated")

# Optional: Refine automated labels manually
# Create refined annotations based on automated + marker review
refined_annotations <- seurat_obj$singler_labels
refined_annotations[refined_annotations == "T cells"] <- ifelse(
  seurat_obj@assays$RNA@data["CD8A", ] > 1,
  "CD8 T cells",
  "CD4 T cells"
)

seurat_obj$cell_type_refined <- refined_annotations
```

---

## Pattern 6: Large Dataset (>100k cells) Optimization

**Use case:** Analyze very large datasets efficiently.

### Optimizations

```r
# Step 1: Use LogNormalize instead of SCTransform (faster)
seurat_obj <- run_lognormalize(seurat_obj)
seurat_obj <- find_hvgs(seurat_obj, n_features = 2000)
seurat_obj <- scale_data(seurat_obj, features = VariableFeatures(seurat_obj))

# Step 2: Reduce PCA dimensions
seurat_obj <- run_pca_analysis(seurat_obj, n_pcs = 30)

# Step 3: Use RPCA for integration (if multi-batch)
if (length(unique(seurat_obj$batch)) > 1) {
  seurat_obj <- run_seurat_rpca_integration(
    seurat_obj,
    batch_var = "batch",
    dims = 1:30
  )
}

# Step 4: Use approximate UMAP
seurat_obj <- run_umap_reduction(
  seurat_obj,
  dims = 1:30,
  n.neighbors = 30L,  # Default
  min.dist = 0.3,
  metric = "cosine",
  verbose = TRUE
)

# Step 5: Find markers on subset for speed
# Downsample for marker finding
seurat_subset <- subset(seurat_obj, downsample = 1000)  # Max 1000 cells per cluster
all_markers <- find_all_cluster_markers(
  seurat_subset,
  resolution = 0.8,
  max.cells.per.ident = 1000
)

# Apply markers to full dataset for annotation
seurat_obj <- annotate_clusters_manual(
  seurat_obj,
  annotations = annotations,
  resolution = 0.8
)
```

---

## Pattern 7: Time Course / Trajectory Setup

**Use case:** Prepare data for downstream trajectory analysis (Monocle3, Slingshot).

### Complete Workflow

```r
# After standard analysis (Pattern 1)

# Step 1: Subset to relevant cell types
# Example: Extract T cells for differentiation analysis
Idents(seurat_obj) <- "cell_type"
tcells <- subset(seurat_obj, idents = c("Naive T cells", "Memory T cells", "Effector T cells"))

# Step 2: Re-cluster at higher resolution
tcells <- cluster_multiple_resolutions(
  tcells,
  dims = 1:30,
  resolutions = c(0.8, 1.0, 1.2, 1.5)
)

Idents(tcells) <- "RNA_snn_res.1.2"

# Step 3: Find markers for trajectory cell states
tcell_markers <- find_all_cluster_markers(tcells, resolution = 1.2)

# Step 4: Visualize potential trajectory
plot_umap_clusters(tcells, output_dir = "results/trajectory")

# Add pseudotime metadata if available
if ("timepoint" %in% colnames(tcells@meta.data)) {
  plot_umap_by_metadata(
    tcells,
    metadata_col = "timepoint",
    output_dir = "results/trajectory"
  )
}

# Step 5: Export for trajectory analysis
# Convert to format for Monocle3, Slingshot, etc.
export_for_monocle3(tcells, output_dir = "results/trajectory")
export_for_slingshot(tcells, output_dir = "results/trajectory")
```

---

## Pattern 8: Multi-Modal Analysis (CITE-seq)

**Use case:** Analyze RNA + protein (ADT) simultaneously.

### Complete Workflow

```r
# Step 1: Load multi-modal data
seurat_obj <- import_10x_multimodal(
  rna_dir = "filtered_feature_bc_matrix/",
  adt_matrix = "adt_counts.csv"
)

# Step 2: QC for both modalities
seurat_obj <- calculate_qc_metrics(seurat_obj, species = "human")
seurat_obj <- calculate_adt_qc(seurat_obj)

# Visualize QC for RNA and ADT
plot_qc_violin(seurat_obj, output_dir = "results/qc")
plot_adt_qc(seurat_obj, output_dir = "results/qc")

# Step 3: Normalize both modalities
# RNA: SCTransform
seurat_obj <- run_sctransform(seurat_obj, assay = "RNA")

# ADT: CLR normalization
seurat_obj <- NormalizeData(
  seurat_obj,
  normalization.method = "CLR",
  margin = 2,
  assay = "ADT"
)

# Step 4: Cluster on RNA
seurat_obj <- run_pca_analysis(seurat_obj, n_pcs = 50)
seurat_obj <- cluster_multiple_resolutions(seurat_obj, dims = 1:30)
seurat_obj <- run_umap_reduction(seurat_obj, dims = 1:30, reduction.name = "umap.rna")

# Step 5: UMAP on ADT for comparison
seurat_obj <- RunUMAP(
  seurat_obj,
  reduction.name = "umap.adt",
  reduction.key = "UMAP_ADT_",
  features = rownames(seurat_obj@assays$ADT),
  assay = "ADT"
)

# Step 6: Visualize protein markers
# Dot plot showing protein expression
plot_adt_dotplot(
  seurat_obj,
  features = c("CD3", "CD4", "CD8", "CD14", "CD19", "CD56"),
  output_dir = "results/cite"
)

# Step 7: Annotate using protein markers
# Can use protein levels to validate/refine RNA-based annotations
seurat_obj <- annotate_with_adt(
  seurat_obj,
  adt_markers = list(
    "CD4 T cells" = "CD3+CD4+",
    "CD8 T cells" = "CD3+CD8+",
    "B cells" = "CD19+",
    "NK cells" = "CD56+",
    "Monocytes" = "CD14+"
  )
)
```

---

**Related Documentation:**
- [workflow-details.md](workflow-details.md) - Step-by-step detailed workflow
- [decision-guide.md](decision-guide.md) - Decision guidance for each step
- [seurat_best_practices.md](seurat_best_practices.md) - Best practices
- [troubleshooting_guide.md](troubleshooting_guide.md) - Common issues
