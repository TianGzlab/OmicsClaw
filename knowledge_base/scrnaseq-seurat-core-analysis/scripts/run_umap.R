# ============================================================================
# UMAP DIMENSIONALITY REDUCTION
# ============================================================================
#
# Run UMAP for visualization of cell populations.
#
# Functions:
#   - run_umap_reduction(): Generate UMAP embedding
#   - run_tsne_reduction(): Generate tSNE embedding (alternative)
#
# Usage:
#   source("scripts/run_umap.R")
#   seurat_obj <- run_umap_reduction(seurat_obj, dims = 1:30)

#' Run UMAP dimensionality reduction
#'
#' @param seurat_obj Seurat object (after PCA)
#' @param dims PCs to use for UMAP (default: 1:30)
#' @param n_neighbors UMAP n.neighbors parameter (default: 30)
#' @param min_dist UMAP min.dist parameter (default: 0.3)
#' @param metric Distance metric (default: "cosine")
#' @param seed Random seed for reproducibility (default: 42)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with UMAP reduction
#' @export
run_umap_reduction <- function(seurat_obj,
                               dims = 1:30,
                               n_neighbors = 30,
                               min_dist = 0.3,
                               metric = "cosine",
                               seed = 42,
                               verbose = TRUE) {

  message("Running UMAP")
  message("  Dimensions: ", paste(range(dims), collapse = "-"))
  message("  n.neighbors: ", n_neighbors)
  message("  min.dist: ", min_dist)
  message("  metric: ", metric)

  # Set seed for reproducibility
  set.seed(seed)

  # Run UMAP
  seurat_obj <- RunUMAP(
    seurat_obj,
    dims = dims,
    n.neighbors = n_neighbors,
    min.dist = min_dist,
    metric = metric,
    seed.use = seed,
    verbose = verbose
  )

  message("UMAP complete")

  return(seurat_obj)
}

#' Run tSNE dimensionality reduction
#'
#' Alternative to UMAP. tSNE is good for visualization but can be slower.
#'
#' @param seurat_obj Seurat object (after PCA)
#' @param dims PCs to use for tSNE (default: 1:30)
#' @param perplexity tSNE perplexity parameter (default: 30)
#' @param seed Random seed for reproducibility (default: 42)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with tSNE reduction
#' @export
run_tsne_reduction <- function(seurat_obj,
                               dims = 1:30,
                               perplexity = 30,
                               seed = 42,
                               verbose = TRUE) {

  message("Running tSNE")
  message("  Dimensions: ", paste(range(dims), collapse = "-"))
  message("  Perplexity: ", perplexity)

  # Set seed for reproducibility
  set.seed(seed)

  # Run tSNE
  seurat_obj <- RunTSNE(
    seurat_obj,
    dims = dims,
    perplexity = perplexity,
    seed.use = seed,
    verbose = verbose
  )

  message("tSNE complete")

  return(seurat_obj)
}

#' Run both UMAP and tSNE
#'
#' For comparison purposes.
#'
#' @param seurat_obj Seurat object (after PCA)
#' @param dims PCs to use (default: 1:30)
#' @return Seurat object with both reductions
#' @export
run_both_reductions <- function(seurat_obj, dims = 1:30) {

  message("Running both UMAP and tSNE for comparison")

  seurat_obj <- run_umap_reduction(seurat_obj, dims = dims, verbose = FALSE)
  seurat_obj <- run_tsne_reduction(seurat_obj, dims = dims, verbose = FALSE)

  message("Both reductions complete")
  message("  Available reductions: ", paste(names(seurat_obj@reductions), collapse = ", "))

  return(seurat_obj)
}

