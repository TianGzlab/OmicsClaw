# ============================================================================
# QUALITY CONTROL METRICS CALCULATION
# ============================================================================
#
# This script calculates QC metrics for filtering low-quality cells.
#
# Functions:
#   - calculate_qc_metrics(): Add QC metrics to Seurat object
#   - get_species_mito_pattern(): Get mitochondrial gene pattern for species
#   - get_species_ribo_pattern(): Get ribosomal gene pattern for species
#
# Usage:
#   source("scripts/qc_metrics.R")
#   seurat_obj <- calculate_qc_metrics(seurat_obj, species = "human")

#' Get mitochondrial gene pattern for species
#'
#' @param species Species name ("human" or "mouse")
#' @return Regular expression pattern for mitochondrial genes
#' @export
get_species_mito_pattern <- function(species) {
  patterns <- list(
    human = "^MT-",
    mouse = "^mt-"
  )

  species <- tolower(species)
  if (!species %in% names(patterns)) {
    stop("Species must be 'human' or 'mouse'")
  }

  return(patterns[[species]])
}

#' Get ribosomal gene pattern for species
#'
#' @param species Species name ("human" or "mouse")
#' @return Regular expression pattern for ribosomal genes
#' @export
get_species_ribo_pattern <- function(species) {
  patterns <- list(
    human = "^RP[SL]",
    mouse = "^Rp[sl]"
  )

  species <- tolower(species)
  if (!species %in% names(patterns)) {
    stop("Species must be 'human' or 'mouse'")
  }

  return(patterns[[species]])
}

#' Calculate QC metrics for Seurat object
#'
#' Adds the following metrics to object metadata:
#'   - nFeature_RNA: Number of genes detected per cell
#'   - nCount_RNA: Total UMI counts per cell
#'   - percent.mt: Percentage of mitochondrial gene expression
#'   - percent.ribo: Percentage of ribosomal gene expression (optional)
#'   - log10GenesPerUMI: Complexity metric
#'
#' @param seurat_obj Seurat object
#' @param species Species name ("human" or "mouse")
#' @param calculate_ribo Whether to calculate ribosomal percentage (default: TRUE)
#' @return Seurat object with QC metrics added to metadata
#' @export
calculate_qc_metrics <- function(seurat_obj,
                                 species = "human",
                                 calculate_ribo = TRUE) {

  message("Calculating QC metrics for ", species)

  # Get patterns
  mito_pattern <- get_species_mito_pattern(species)

  # Calculate mitochondrial percentage
  seurat_obj[["percent.mt"]] <- PercentageFeatureSet(
    seurat_obj,
    pattern = mito_pattern
  )

  message(sprintf("  Mitochondrial genes identified: %d",
                  sum(grepl(mito_pattern, rownames(seurat_obj)))))

  # Calculate ribosomal percentage if requested
  if (calculate_ribo) {
    ribo_pattern <- get_species_ribo_pattern(species)
    seurat_obj[["percent.ribo"]] <- PercentageFeatureSet(
      seurat_obj,
      pattern = ribo_pattern
    )
    message(sprintf("  Ribosomal genes identified: %d",
                    sum(grepl(ribo_pattern, rownames(seurat_obj)))))
  }

  # Calculate complexity metric (genes per UMI)
  # Higher values indicate more complex samples (good quality)
  seurat_obj[["log10GenesPerUMI"]] <- log10(
    seurat_obj$nFeature_RNA / seurat_obj$nCount_RNA
  )

  # Summary statistics
  message("\nQC Metrics Summary:")
  message(sprintf("  Cells: %d", ncol(seurat_obj)))
  message(sprintf("  Genes: %d", nrow(seurat_obj)))
  message(sprintf("  Median genes per cell: %.0f",
                  median(seurat_obj$nFeature_RNA)))
  message(sprintf("  Median UMIs per cell: %.0f",
                  median(seurat_obj$nCount_RNA)))
  message(sprintf("  Median percent.mt: %.2f%%",
                  median(seurat_obj$percent.mt)))

  if (calculate_ribo) {
    message(sprintf("  Median percent.ribo: %.2f%%",
                    median(seurat_obj$percent.ribo)))
  }

  return(seurat_obj)
}

#' Get recommended QC thresholds by tissue type
#'
#' @param tissue Tissue type (e.g., "pbmc", "brain", "tumor")
#' @return List with recommended thresholds
#' @export
get_tissue_qc_thresholds <- function(tissue) {

  thresholds <- list(
    pbmc = list(
      min_features = 200,
      max_features = 2500,
      max_mt = 5,
      description = "Peripheral blood mononuclear cells"
    ),
    brain = list(
      min_features = 200,
      max_features = 6000,
      max_mt = 10,
      description = "Brain tissue (neurons have many genes)"
    ),
    tumor = list(
      min_features = 200,
      max_features = 5000,
      max_mt = 20,
      description = "Tumor samples (higher mt% tolerated)"
    ),
    kidney = list(
      min_features = 200,
      max_features = 4000,
      max_mt = 15,
      description = "Kidney tissue"
    ),
    liver = list(
      min_features = 200,
      max_features = 4000,
      max_mt = 15,
      description = "Liver tissue"
    ),
    heart = list(
      min_features = 200,
      max_features = 4000,
      max_mt = 15,
      description = "Heart tissue (cardiomyocytes have high mt%)"
    ),
    default = list(
      min_features = 200,
      max_features = 4000,
      max_mt = 10,
      description = "General tissue (adjust based on your data)"
    )
  )

  tissue <- tolower(tissue)
  if (!tissue %in% names(thresholds)) {
    message("Tissue '", tissue, "' not recognized. Using default thresholds.")
    message("Available tissues: ", paste(names(thresholds), collapse = ", "))
    return(thresholds$default)
  }

  result <- thresholds[[tissue]]
  message("Using thresholds for: ", result$description)
  message(sprintf("  min_features: %d", result$min_features))
  message(sprintf("  max_features: %d", result$max_features))
  message(sprintf("  max_mt: %.1f%%", result$max_mt))

  return(result)
}


#' Batch-aware MAD (Median Absolute Deviation) outlier detection
#'
#' This approach adapts to batch-specific distributions instead of using
#' fixed thresholds, preventing bias against metabolically active cell types.
#'
#' @param seurat_obj Seurat object with QC metrics
#' @param batch_col Column in metadata containing batch labels (default: 'batch')
#' @param metrics QC metrics to check for outliers
#'   Default: c('nFeature_RNA', 'nCount_RNA', 'percent.mt')
#' @param nmads Number of MADs from median to define outliers (default: 5)
#'
#' @return Seurat object with outlier flags added to metadata
#'
#' @details
#' Creates/updates metadata columns:
#'   - outlier: Overall outlier flag (logical)
#'   - outlier_{metric}: Per-metric outlier flags
#'
#' @export
batch_mad_outlier_detection <- function(
  seurat_obj,
  batch_col = "batch",
  metrics = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
  nmads = 5
) {
  cat(sprintf("Performing batch-aware MAD outlier detection (nmads=%d)...\n", nmads))

  # Check if batch column exists
  if (!batch_col %in% colnames(seurat_obj@meta.data)) {
    cat(sprintf("Warning: '%s' not found in metadata. Treating as single batch.\n", batch_col))
    seurat_obj@meta.data[[batch_col]] <- "batch_1"
  }

  # Add log-transformed metrics if not present
  if (!"log10_nFeature_RNA" %in% colnames(seurat_obj@meta.data)) {
    seurat_obj@meta.data$log10_nFeature_RNA <- log10(seurat_obj$nFeature_RNA + 1)
  }
  if (!"log10_nCount_RNA" %in% colnames(seurat_obj@meta.data)) {
    seurat_obj@meta.data$log10_nCount_RNA <- log10(seurat_obj$nCount_RNA + 1)
  }

  # Initialize outlier column
  seurat_obj@meta.data$outlier <- FALSE

  # Track outliers per metric
  for (metric in metrics) {
    # Use log-transformed version if available
    metric_to_use <- metric
    log_metric <- paste0("log10_", metric)
    if (log_metric %in% colnames(seurat_obj@meta.data)) {
      metric_to_use <- log_metric
    }

    if (!metric_to_use %in% colnames(seurat_obj@meta.data)) {
      cat(sprintf("Warning: Metric '%s' not found in metadata. Skipping.\n", metric_to_use))
      next
    }

    outlier_col <- paste0("outlier_", metric)
    seurat_obj@meta.data[[outlier_col]] <- FALSE

    # Process each batch separately
    for (batch in unique(seurat_obj@meta.data[[batch_col]])) {
      batch_mask <- seurat_obj@meta.data[[batch_col]] == batch
      batch_values <- seurat_obj@meta.data[batch_mask, metric_to_use]

      # Calculate MAD
      batch_median <- median(batch_values, na.rm = TRUE)
      mad <- median(abs(batch_values - batch_median), na.rm = TRUE)

      # Avoid division by zero
      if (mad == 0) {
        cat(sprintf("  Warning: MAD=0 for %s in batch %s. Skipping.\n", metric_to_use, batch))
        next
      }

      # Define outlier thresholds
      lower <- batch_median - nmads * mad
      upper <- batch_median + nmads * mad

      # Identify outliers
      batch_outliers <- (batch_values < lower) | (batch_values > upper)

      # Update outlier flags
      seurat_obj@meta.data[batch_mask, outlier_col] <- batch_outliers
      seurat_obj@meta.data[batch_mask, "outlier"] <-
        seurat_obj@meta.data[batch_mask, "outlier"] | batch_outliers

      n_outliers <- sum(batch_outliers, na.rm = TRUE)
      if (n_outliers > 0) {
        cat(sprintf("  %s [%s]: %d outliers (thresholds: %.2f - %.2f)\n",
                    metric_to_use, batch, n_outliers, lower, upper))
      }
    }
  }

  # Summary
  n_total_outliers <- sum(seurat_obj@meta.data$outlier, na.rm = TRUE)
  pct_outliers <- 100 * n_total_outliers / ncol(seurat_obj)

  cat(sprintf("\nTotal outliers: %d (%.1f%%)\n", n_total_outliers, pct_outliers))
  cat(sprintf("Cells passing QC: %d (%.1f%%)\n",
              ncol(seurat_obj) - n_total_outliers, 100 - pct_outliers))

  return(seurat_obj)
}


#' Mark outliers using fixed tissue-specific thresholds
#'
#' Use this for single-batch data or when tissue-specific guidelines exist.
#' For multi-batch data, prefer batch_mad_outlier_detection().
#'
#' @param seurat_obj Seurat object with QC metrics
#' @param tissue Tissue type (default: 'pbmc')
#' @param min_features Minimum features per cell (overrides tissue default)
#' @param max_features Maximum features per cell (overrides tissue default)
#' @param max_mt Maximum mitochondrial percentage (overrides tissue default)
#'
#' @return Seurat object with outlier flags added to metadata
#'
#' @export
mark_outliers_fixed <- function(
  seurat_obj,
  tissue = "pbmc",
  min_features = NULL,
  max_features = NULL,
  max_mt = NULL
) {
  # Get tissue-specific thresholds
  thresholds <- get_tissue_qc_thresholds(tissue)

  # Override with user-specified values
  if (!is.null(min_features)) thresholds$min_features <- min_features
  if (!is.null(max_features)) thresholds$max_features <- max_features
  if (!is.null(max_mt)) thresholds$max_mt <- max_mt

  cat("\nApplying fixed QC thresholds:\n")
  cat(sprintf("  min_features: %d\n", thresholds$min_features))
  cat(sprintf("  max_features: %d\n", thresholds$max_features))
  cat(sprintf("  max_mt: %.1f%%\n", thresholds$max_mt))

  # Mark outliers
  seurat_obj@meta.data$outlier <- (
    seurat_obj$nFeature_RNA < thresholds$min_features |
    seurat_obj$nFeature_RNA > thresholds$max_features |
    seurat_obj$percent.mt > thresholds$max_mt
  )

  # Track outliers by criterion
  seurat_obj@meta.data$outlier_low_features <- seurat_obj$nFeature_RNA < thresholds$min_features
  seurat_obj@meta.data$outlier_high_features <- seurat_obj$nFeature_RNA > thresholds$max_features
  seurat_obj@meta.data$outlier_high_mt <- seurat_obj$percent.mt > thresholds$max_mt

  # Summary
  n_total_outliers <- sum(seurat_obj@meta.data$outlier, na.rm = TRUE)
  pct_outliers <- 100 * n_total_outliers / ncol(seurat_obj)

  cat("\nOutlier summary:\n")
  cat(sprintf("  Low features: %d\n", sum(seurat_obj@meta.data$outlier_low_features)))
  cat(sprintf("  High features: %d\n", sum(seurat_obj@meta.data$outlier_high_features)))
  cat(sprintf("  High MT%%: %d\n", sum(seurat_obj@meta.data$outlier_high_mt)))
  cat(sprintf("  Total outliers: %d (%.1f%%)\n", n_total_outliers, pct_outliers))
  cat(sprintf("  Cells passing QC: %d (%.1f%%)\n",
              ncol(seurat_obj) - n_total_outliers, 100 - pct_outliers))

  return(seurat_obj)
}

