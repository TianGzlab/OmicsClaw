#' Batch Integration Methods for Seurat
#'
#' This module implements batch integration methods for single-cell RNA-seq
#' data in Seurat, including Harmony, Seurat CCA, and Seurat RPCA.
#'
#' For methodology and best practices, see references/integration_methods.md
#'
#' Functions:
#'   - run_harmony_integration(): Fast linear integration with Harmony
#'   - run_seurat_cca_integration(): Canonical Correlation Analysis integration
#'   - run_seurat_rpca_integration(): Reciprocal PCA integration (faster, large data)
#'   - setup_for_integration(): Prepare Seurat object for integration

library(Seurat)
library(dplyr)


#' Prepare Seurat object for integration
#'
#' @param seurat_obj Seurat object
#' @param batch_col Column in metadata with batch labels
#' @param n_features Number of variable features per batch (default: 2000)
#'
#' @return Seurat object prepared for integration
#'
#' @export
setup_for_integration <- function(
  seurat_obj,
  batch_col,
  n_features = 2000
) {
  cat("Preparing Seurat object for integration...\n")

  # Check batch column
  if (!batch_col %in% colnames(seurat_obj@meta.data)) {
    stop(sprintf("Batch column '%s' not found in metadata", batch_col))
  }

  n_batches <- length(unique(seurat_obj@meta.data[[batch_col]]))
  cat(sprintf("  Cells: %d\n", ncol(seurat_obj)))
  cat(sprintf("  Genes: %d\n", nrow(seurat_obj)))
  cat(sprintf("  Batches: %d (%s)\n", n_batches, batch_col))

  # Ensure normalized data exists
  if (!"RNA" %in% names(seurat_obj@assays)) {
    stop("RNA assay not found. Please ensure raw counts are in RNA assay.")
  }

  # Normalize if not already done
  if (is.null(seurat_obj@assays$RNA@data) ||
      all(seurat_obj@assays$RNA@data == seurat_obj@assays$RNA@counts)) {
    cat("  Normalizing data...\n")
    seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)
  }

  # Find variable features if not present
  if (is.null(VariableFeatures(seurat_obj)) ||
      length(VariableFeatures(seurat_obj)) == 0) {
    cat(sprintf("  Finding %d variable features...\n", n_features))
    seurat_obj <- FindVariableFeatures(
      seurat_obj,
      nfeatures = n_features,
      verbose = FALSE
    )
  }

  n_var_features <- length(VariableFeatures(seurat_obj))
  cat(sprintf("  Variable features: %d\n", n_var_features))

  cat("  Preparation complete.\n\n")

  return(seurat_obj)
}


#' Run Harmony integration
#'
#' Harmony is a fast, interpretable integration method that iteratively
#' clusters and corrects PCA space.
#'
#' @param seurat_obj Seurat object
#' @param batch_col Column in metadata with batch labels
#' @param dims PCs to use for integration (default: 1:30)
#' @param theta Diversity penalty (default: 2)
#'   - 0: No correction
#'   - 1: Gentle correction
#'   - 2: Standard correction (recommended)
#'   - 4: Aggressive correction
#' @param lambda Ridge regression penalty (default: 1)
#' @param max_iter Maximum iterations (default: 10)
#' @param run_umap Whether to run UMAP after integration (default: TRUE)
#'
#' @return Seurat object with Harmony integration in "harmony" reduction
#'
#' @export
run_harmony_integration <- function(
  seurat_obj,
  batch_col,
  dims = 1:30,
  theta = 2,
  lambda = 1,
  max_iter = 10,
  run_umap = TRUE
) {
  # Check harmony package
  if (!requireNamespace("harmony", quietly = TRUE)) {
    stop("harmony package required. Install with: install.packages('harmony')")
  }

  library(harmony)

  cat("=" %R% 60 %R% "\n")
  cat("Harmony Integration\n")
  cat("=" %R% 60 %R% "\n\n")

  # Check batch column
  if (!batch_col %in% colnames(seurat_obj@meta.data)) {
    stop(sprintf("Batch column '%s' not found in metadata", batch_col))
  }

  n_batches <- length(unique(seurat_obj@meta.data[[batch_col]]))
  cat(sprintf("Batch information:\n"))
  cat(sprintf("  Batches: %d (%s)\n", n_batches, batch_col))
  cat(sprintf("  Cells: %d\n\n", ncol(seurat_obj)))

  # Run PCA if not present
  if (!"pca" %in% names(seurat_obj@reductions)) {
    cat("Running PCA...\n")
    seurat_obj <- ScaleData(seurat_obj, verbose = FALSE)
    seurat_obj <- RunPCA(seurat_obj, npcs = max(dims), verbose = FALSE)
  }

  cat(sprintf("PCA dimensions: %d\n", ncol(seurat_obj@reductions$pca)))

  # Run Harmony
  cat("\nRunning Harmony integration...\n")
  cat(sprintf("  Theta (diversity penalty): %.1f\n", theta))
  cat(sprintf("  Lambda (ridge penalty): %.1f\n", lambda))
  cat(sprintf("  Max iterations: %d\n", max_iter))
  cat(sprintf("  Dimensions: %d-%d\n", min(dims), max(dims)))

  seurat_obj <- RunHarmony(
    seurat_obj,
    group.by.vars = batch_col,
    dims.use = dims,
    theta = theta,
    lambda = lambda,
    max.iter.harmony = max_iter,
    verbose = FALSE
  )

  cat("\n  Harmony integration complete.\n")
  cat("  Integrated representation in 'harmony' reduction\n")

  # Run UMAP if requested
  if (run_umap) {
    cat("\nRunning UMAP on integrated space...\n")
    seurat_obj <- RunUMAP(
      seurat_obj,
      reduction = "harmony",
      dims = dims,
      verbose = FALSE
    )
  }

  # Store integration info
  seurat_obj@misc$harmony_integration <- list(
    batch_col = batch_col,
    theta = theta,
    lambda = lambda,
    max_iter = max_iter,
    dims = dims,
    n_batches = n_batches
  )

  cat("\n" %R% "=" %R% 60 %R% "\n")
  cat("Harmony integration complete!\n")
  cat("=" %R% 60 %R% "\n\n")
  cat("Next steps:\n")
  cat("  seurat_obj <- FindNeighbors(seurat_obj, reduction = 'harmony', dims = 1:30)\n")
  cat("  seurat_obj <- FindClusters(seurat_obj)\n")
  cat("  DimPlot(seurat_obj, group.by = c('batch', 'cell_type'))\n\n")

  return(seurat_obj)
}


#' Run Seurat CCA integration
#'
#' Canonical Correlation Analysis (CCA) learns shared correlation structure
#' across batches for integration.
#'
#' @param seurat_obj Seurat object
#' @param batch_col Column in metadata with batch labels
#' @param dims PCs to use for integration (default: 1:30)
#' @param n_features Number of features for anchor finding (default: 2000)
#' @param k_anchor Number of neighbors for anchor finding (default: 5)
#' @param k_filter Number of neighbors for filtering anchors (default: 200)
#' @param k_score Number of neighbors for scoring anchors (default: 30)
#' @param run_pca Whether to run PCA after integration (default: TRUE)
#' @param run_umap Whether to run UMAP after integration (default: TRUE)
#'
#' @return Seurat object with integrated assay
#'
#' @export
run_seurat_cca_integration <- function(
  seurat_obj,
  batch_col,
  dims = 1:30,
  n_features = 2000,
  k_anchor = 5,
  k_filter = 200,
  k_score = 30,
  run_pca = TRUE,
  run_umap = TRUE
) {
  cat("=" %R% 60 %R% "\n")
  cat("Seurat CCA Integration\n")
  cat("=" %R% 60 %R% "\n\n")

  # Check batch column
  if (!batch_col %in% colnames(seurat_obj@meta.data)) {
    stop(sprintf("Batch column '%s' not found in metadata", batch_col))
  }

  n_batches <- length(unique(seurat_obj@meta.data[[batch_col]]))
  cat(sprintf("Batch information:\n"))
  cat(sprintf("  Batches: %d (%s)\n", n_batches, batch_col))
  cat(sprintf("  Cells: %d\n\n", ncol(seurat_obj)))

  # Split by batch
  cat("Splitting object by batch...\n")
  seurat_list <- SplitObject(seurat_obj, split.by = batch_col)

  # Normalize and find variable features per batch
  cat(sprintf("Normalizing and finding %d variable features per batch...\n", n_features))
  seurat_list <- lapply(seurat_list, function(x) {
    x <- NormalizeData(x, verbose = FALSE)
    x <- FindVariableFeatures(x, nfeatures = n_features, verbose = FALSE)
    return(x)
  })

  # Select integration features
  cat("Selecting integration features...\n")
  features <- SelectIntegrationFeatures(
    seurat_list,
    nfeatures = n_features
  )

  cat(sprintf("  Integration features: %d\n\n", length(features)))

  # Find integration anchors
  cat("Finding integration anchors (CCA)...\n")
  cat(sprintf("  k.anchor: %d\n", k_anchor))
  cat(sprintf("  k.filter: %d\n", k_filter))
  cat(sprintf("  k.score: %d\n\n", k_score))

  anchors <- FindIntegrationAnchors(
    object.list = seurat_list,
    anchor.features = features,
    reduction = "cca",
    dims = dims,
    k.anchor = k_anchor,
    k.filter = k_filter,
    k.score = k_score,
    verbose = FALSE
  )

  cat(sprintf("  Anchors found: %d\n\n", nrow(anchors@anchors)))

  # Integrate data
  cat("Integrating data...\n")
  seurat_integrated <- IntegrateData(
    anchorset = anchors,
    dims = dims,
    verbose = FALSE
  )

  # Set default assay to integrated
  DefaultAssay(seurat_integrated) <- "integrated"

  cat("  Integration complete.\n")
  cat("  Integrated data in 'integrated' assay\n\n")

  # Scale integrated data
  cat("Scaling integrated data...\n")
  seurat_integrated <- ScaleData(seurat_integrated, verbose = FALSE)

  # Run PCA if requested
  if (run_pca) {
    cat("Running PCA on integrated data...\n")
    seurat_integrated <- RunPCA(
      seurat_integrated,
      npcs = max(dims),
      verbose = FALSE
    )
  }

  # Run UMAP if requested
  if (run_umap) {
    cat("Running UMAP on integrated data...\n")
    seurat_integrated <- RunUMAP(
      seurat_integrated,
      reduction = "pca",
      dims = dims,
      verbose = FALSE
    )
  }

  # Store integration info
  seurat_integrated@misc$cca_integration <- list(
    batch_col = batch_col,
    method = "cca",
    dims = dims,
    n_features = n_features,
    n_anchors = nrow(anchors@anchors),
    n_batches = n_batches
  )

  cat("\n" %R% "=" %R% 60 %R% "\n")
  cat("Seurat CCA integration complete!\n")
  cat("=" %R% 60 %R% "\n\n")
  cat("Next steps:\n")
  cat("  seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30)\n")
  cat("  seurat_obj <- FindClusters(seurat_obj)\n")
  cat("  DimPlot(seurat_obj, group.by = c('batch', 'cell_type'))\n\n")
  cat("IMPORTANT: For DE analysis, use RNA assay:\n")
  cat("  DefaultAssay(seurat_obj) <- 'RNA'\n\n")

  return(seurat_integrated)
}


#' Run Seurat RPCA integration
#'
#' Reciprocal PCA (RPCA) is faster than CCA and scales better for large
#' datasets, but requires similar cell type compositions across batches.
#'
#' @param seurat_obj Seurat object
#' @param batch_col Column in metadata with batch labels
#' @param dims PCs to use for integration (default: 1:30)
#' @param n_features Number of features for anchor finding (default: 2000)
#' @param k_anchor Number of neighbors for anchor finding (default: 5)
#' @param k_filter Number of neighbors for filtering anchors (default: 200)
#' @param k_score Number of neighbors for scoring anchors (default: 30)
#' @param run_pca Whether to run PCA after integration (default: TRUE)
#' @param run_umap Whether to run UMAP after integration (default: TRUE)
#'
#' @return Seurat object with integrated assay
#'
#' @export
run_seurat_rpca_integration <- function(
  seurat_obj,
  batch_col,
  dims = 1:30,
  n_features = 2000,
  k_anchor = 5,
  k_filter = 200,
  k_score = 30,
  run_pca = TRUE,
  run_umap = TRUE
) {
  cat("=" %R% 60 %R% "\n")
  cat("Seurat RPCA Integration\n")
  cat("=" %R% 60 %R% "\n\n")

  # Check batch column
  if (!batch_col %in% colnames(seurat_obj@meta.data)) {
    stop(sprintf("Batch column '%s' not found in metadata", batch_col))
  }

  n_batches <- length(unique(seurat_obj@meta.data[[batch_col]]))
  cat(sprintf("Batch information:\n"))
  cat(sprintf("  Batches: %d (%s)\n", n_batches, batch_col))
  cat(sprintf("  Cells: %d\n\n", ncol(seurat_obj)))

  # Split by batch
  cat("Splitting object by batch...\n")
  seurat_list <- SplitObject(seurat_obj, split.by = batch_col)

  # Normalize, find features, and run PCA per batch
  cat(sprintf("Normalizing, finding features, and running PCA per batch...\n"))
  seurat_list <- lapply(seurat_list, function(x) {
    x <- NormalizeData(x, verbose = FALSE)
    x <- FindVariableFeatures(x, nfeatures = n_features, verbose = FALSE)
    x <- ScaleData(x, verbose = FALSE)
    x <- RunPCA(x, npcs = max(dims), verbose = FALSE)
    return(x)
  })

  # Select integration features
  cat("Selecting integration features...\n")
  features <- SelectIntegrationFeatures(
    seurat_list,
    nfeatures = n_features
  )

  cat(sprintf("  Integration features: %d\n\n", length(features)))

  # Find integration anchors using RPCA
  cat("Finding integration anchors (RPCA)...\n")
  cat(sprintf("  k.anchor: %d\n", k_anchor))
  cat(sprintf("  k.filter: %d\n", k_filter))
  cat(sprintf("  k.score: %d\n\n", k_score))

  anchors <- FindIntegrationAnchors(
    object.list = seurat_list,
    anchor.features = features,
    reduction = "rpca",
    dims = dims,
    k.anchor = k_anchor,
    k.filter = k_filter,
    k.score = k_score,
    verbose = FALSE
  )

  cat(sprintf("  Anchors found: %d\n\n", nrow(anchors@anchors)))

  # Integrate data
  cat("Integrating data...\n")
  seurat_integrated <- IntegrateData(
    anchorset = anchors,
    dims = dims,
    verbose = FALSE
  )

  # Set default assay to integrated
  DefaultAssay(seurat_integrated) <- "integrated"

  cat("  Integration complete.\n")
  cat("  Integrated data in 'integrated' assay\n\n")

  # Scale integrated data
  cat("Scaling integrated data...\n")
  seurat_integrated <- ScaleData(seurat_integrated, verbose = FALSE)

  # Run PCA if requested
  if (run_pca) {
    cat("Running PCA on integrated data...\n")
    seurat_integrated <- RunPCA(
      seurat_integrated,
      npcs = max(dims),
      verbose = FALSE
    )
  }

  # Run UMAP if requested
  if (run_umap) {
    cat("Running UMAP on integrated data...\n")
    seurat_integrated <- RunUMAP(
      seurat_integrated,
      reduction = "pca",
      dims = dims,
      verbose = FALSE
    )
  }

  # Store integration info
  seurat_integrated@misc$rpca_integration <- list(
    batch_col = batch_col,
    method = "rpca",
    dims = dims,
    n_features = n_features,
    n_anchors = nrow(anchors@anchors),
    n_batches = n_batches
  )

  cat("\n" %R% "=" %R% 60 %R% "\n")
  cat("Seurat RPCA integration complete!\n")
  cat("=" %R% 60 %R% "\n\n")
  cat("Next steps:\n")
  cat("  seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30)\n")
  cat("  seurat_obj <- FindClusters(seurat_obj)\n")
  cat("  DimPlot(seurat_obj, group.by = c('batch', 'cell_type'))\n\n")
  cat("IMPORTANT: For DE analysis, use RNA assay:\n")
  cat("  DefaultAssay(seurat_obj) <- 'RNA'\n\n")

  return(seurat_integrated)
}


# Example usage
if (FALSE) {
  # Example Harmony workflow
  cat("Example Harmony integration:\n")
  cat("  seurat_obj <- setup_for_integration(seurat_obj, 'batch')\n")
  cat("  seurat_obj <- run_harmony_integration(seurat_obj, 'batch', theta = 2)\n")
  cat("  seurat_obj <- FindNeighbors(seurat_obj, reduction = 'harmony', dims = 1:30)\n")
  cat("  seurat_obj <- FindClusters(seurat_obj)\n\n")

  # Example CCA workflow
  cat("Example Seurat CCA integration:\n")
  cat("  seurat_obj <- setup_for_integration(seurat_obj, 'batch')\n")
  cat("  seurat_obj <- run_seurat_cca_integration(seurat_obj, 'batch')\n")
  cat("  seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30)\n")
  cat("  seurat_obj <- FindClusters(seurat_obj)\n\n")

  # Example RPCA workflow
  cat("Example Seurat RPCA integration:\n")
  cat("  seurat_obj <- setup_for_integration(seurat_obj, 'batch')\n")
  cat("  seurat_obj <- run_seurat_rpca_integration(seurat_obj, 'batch')\n")
  cat("  seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30)\n")
  cat("  seurat_obj <- FindClusters(seurat_obj)\n")
}

