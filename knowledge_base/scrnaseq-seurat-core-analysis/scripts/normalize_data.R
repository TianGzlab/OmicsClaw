# ============================================================================
# DATA NORMALIZATION
# ============================================================================
#
# This script normalizes expression data using either SCTransform or LogNormalize.
#
# Functions:
#   - run_sctransform(): Normalize with SCTransform (recommended for UMI data)
#   - run_lognormalize(): Normalize with LogNormalize (classic workflow)
#   - scale_data(): Scale data (for LogNormalize workflow)
#
# Usage:
#   source("scripts/normalize_data.R")
#   # For SCTransform (recommended)
#   seurat_obj <- run_sctransform(seurat_obj)
#   # OR for LogNormalize
#   seurat_obj <- run_lognormalize(seurat_obj)

#' Normalize data using SCTransform
#'
#' SCTransform is recommended for UMI-based data (e.g., 10X Chromium).
#' It normalizes, finds variable features, and scales data in one step.
#'
#' @param seurat_obj Seurat object (post-filtering)
#' @param vars_to_regress Variables to regress out (default: c("percent.mt"))
#' @param n_genes Number of variable genes to return (default: 3000)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with SCT assay
#' @export
run_sctransform <- function(seurat_obj,
                            vars_to_regress = c("percent.mt"),
                            n_genes = 3000,
                            verbose = TRUE) {

  message("Running SCTransform normalization")
  message("  Variables to regress: ", paste(vars_to_regress, collapse = ", "))
  message("  Variable genes to identify: ", n_genes)

  # Check if vars_to_regress exist in metadata
  missing_vars <- setdiff(vars_to_regress, colnames(seurat_obj@meta.data))
  if (length(missing_vars) > 0) {
    warning("Variables not found in metadata: ", paste(missing_vars, collapse = ", "))
    vars_to_regress <- intersect(vars_to_regress, colnames(seurat_obj@meta.data))
  }

  # Run SCTransform
  seurat_obj <- SCTransform(
    seurat_obj,
    vars.to.regress = vars_to_regress,
    variable.features.n = n_genes,
    verbose = verbose
  )

  message("SCTransform complete")
  message("  Default assay: ", DefaultAssay(seurat_obj))
  message("  Variable features: ", length(VariableFeatures(seurat_obj)))

  return(seurat_obj)
}

#' Normalize data using LogNormalize
#'
#' Classic Seurat normalization workflow. Use when:
#' - Non-UMI data (e.g., Smart-seq2)
#' - SCTransform causes issues
#' - You need more control over individual steps
#'
#' @param seurat_obj Seurat object (post-filtering)
#' @param normalization_method Normalization method (default: "LogNormalize")
#' @param scale_factor Scale factor for normalization (default: 10000)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with normalized data
#' @export
run_lognormalize <- function(seurat_obj,
                             normalization_method = "LogNormalize",
                             scale_factor = 10000,
                             verbose = TRUE) {

  message("Running LogNormalize normalization")
  message("  Method: ", normalization_method)
  message("  Scale factor: ", scale_factor)

  # Normalize data
  seurat_obj <- NormalizeData(
    seurat_obj,
    normalization.method = normalization_method,
    scale.factor = scale_factor,
    verbose = verbose
  )

  message("Normalization complete")

  return(seurat_obj)
}

#' Scale data (for LogNormalize workflow)
#'
#' Scales and centers features. Only needed for LogNormalize workflow
#' (SCTransform does this automatically).
#'
#' @param seurat_obj Seurat object (after LogNormalize and FindVariableFeatures)
#' @param features Features to scale (default: all genes)
#' @param vars_to_regress Variables to regress out (default: NULL)
#' @param verbose Print progress (default: TRUE)
#' @return Seurat object with scaled data
#' @export
scale_data <- function(seurat_obj,
                      features = NULL,
                      vars_to_regress = NULL,
                      verbose = TRUE) {

  message("Scaling data")

  # Use all genes if not specified
  if (is.null(features)) {
    features <- rownames(seurat_obj)
    message("  Scaling all genes: ", length(features))
  } else {
    message("  Scaling specified features: ", length(features))
  }

  # Check if vars_to_regress exist
  if (!is.null(vars_to_regress)) {
    message("  Variables to regress: ", paste(vars_to_regress, collapse = ", "))
    missing_vars <- setdiff(vars_to_regress, colnames(seurat_obj@meta.data))
    if (length(missing_vars) > 0) {
      warning("Variables not found in metadata: ", paste(missing_vars, collapse = ", "))
      vars_to_regress <- intersect(vars_to_regress, colnames(seurat_obj@meta.data))
    }
  }

  # Scale data
  seurat_obj <- ScaleData(
    seurat_obj,
    features = features,
    vars.to.regress = vars_to_regress,
    verbose = verbose
  )

  message("Scaling complete")

  return(seurat_obj)
}

#' Compare SCTransform and LogNormalize results
#'
#' For testing/comparison purposes. Runs both methods and compares results.
#'
#' @param seurat_obj Seurat object (post-filtering)
#' @param output_dir Output directory for comparison plots
#' @return List with both Seurat objects
#' @export
compare_normalization_methods <- function(seurat_obj, output_dir = NULL) {

  message("Comparing SCTransform and LogNormalize methods")

  # Create two copies
  seurat_sct <- seurat_obj
  seurat_log <- seurat_obj

  # Run SCTransform
  seurat_sct <- run_sctransform(seurat_sct, verbose = FALSE)

  # Run LogNormalize workflow
  seurat_log <- run_lognormalize(seurat_log, verbose = FALSE)
  source("scripts/find_variable_features.R")
  seurat_log <- find_hvgs(seurat_log, verbose = FALSE)
  seurat_log <- scale_data(seurat_log, verbose = FALSE)

  # Run PCA for both
  seurat_sct <- RunPCA(seurat_sct, verbose = FALSE)
  seurat_log <- RunPCA(seurat_log, verbose = FALSE)

  message("Both methods completed. Compare PCA and clustering results.")

  if (!is.null(output_dir)) {
    message("Save comparison plots using plot_pca.R functions")
  }

  return(list(
    sct = seurat_sct,
    lognorm = seurat_log
  ))
}

