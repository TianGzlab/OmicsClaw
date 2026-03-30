#' Ambient RNA Correction for Single-Cell RNA-seq Data
#'
#' This module provides functions for removing ambient RNA contamination using SoupX.
#'
#' For detailed guidance, see references/ambient_rna_correction.md

library(Seurat)
library(SoupX)
library(ggplot2)
library(ggprism)


#' Run SoupX ambient RNA correction
#'
#' SoupX estimates and removes ambient RNA contamination from droplet-based
#' scRNA-seq data by comparing raw and filtered count matrices.
#'
#' @param raw_matrix_dir Path to raw_feature_bc_matrix/ directory
#' @param filtered_matrix_dir Path to filtered_feature_bc_matrix/ directory
#' @param clusters Optional cluster assignments for cells (improves estimation)
#' @param output_dir Directory to save SoupX outputs
#' @param auto_estimate Auto-estimate contamination fraction (default: TRUE)
#' @param contamination_range Range for contamination estimation (default: c(0.01, 0.5))
#'
#' @return Seurat object with corrected counts
#'
#' @export
run_soupx_correction <- function(
  raw_matrix_dir,
  filtered_matrix_dir,
  clusters = NULL,
  output_dir = "results/soupx",
  auto_estimate = TRUE,
  contamination_range = c(0.01, 0.5)
) {
  # Create output directory
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  # Load raw and filtered matrices
  cat("Loading raw and filtered matrices...\n")
  raw_data <- Read10X(raw_matrix_dir)
  filtered_data <- Read10X(filtered_matrix_dir)

  # Create Seurat object from filtered data for clustering if needed
  if (is.null(clusters)) {
    cat("Performing quick clustering for contamination estimation...\n")
    seurat_temp <- CreateSeuratObject(counts = filtered_data)
    seurat_temp <- NormalizeData(seurat_temp, verbose = FALSE)
    seurat_temp <- FindVariableFeatures(seurat_temp, verbose = FALSE)
    seurat_temp <- ScaleData(seurat_temp, verbose = FALSE)
    seurat_temp <- RunPCA(seurat_temp, verbose = FALSE)
    seurat_temp <- FindNeighbors(seurat_temp, dims = 1:30, verbose = FALSE)
    seurat_temp <- FindClusters(seurat_temp, resolution = 0.8, verbose = FALSE)
    clusters <- Idents(seurat_temp)
  }

  # Create SoupChannel
  sc <- SoupChannel(raw_data, filtered_data)

  # Add cluster information
  sc <- setClusters(sc, clusters)

  # Estimate contamination
  if (auto_estimate) {
    cat("Auto-estimating contamination fraction...\n")
    sc <- autoEstCont(sc)
    contamination_fraction <- sc$metaData$rho[1]
    cat(sprintf("Estimated contamination fraction: %.3f (%.1f%%)\n",
                contamination_fraction, contamination_fraction * 100))
  } else {
    # Manual estimation
    cat("Manually estimating contamination fraction...\n")
    sc <- estimateContamination(sc, tfidfMin = 0.5, verbose = TRUE)
    contamination_fraction <- sc$fit$rho
  }

  # Correct counts
  cat("Correcting counts...\n")
  corrected_counts <- adjustCounts(sc)

  # Create Seurat object with corrected counts
  seurat_corrected <- CreateSeuratObject(counts = corrected_counts)

  # Store metadata
  seurat_corrected@misc$soupx <- list(
    contamination_fraction = contamination_fraction,
    raw_matrix_dir = raw_matrix_dir,
    filtered_matrix_dir = filtered_matrix_dir
  )

  # Save output
  saveRDS(seurat_corrected, file = file.path(output_dir, "seurat_soupx_corrected.rds"))
  write.csv(data.frame(contamination_fraction = contamination_fraction),
            file = file.path(output_dir, "contamination_estimate.csv"),
            row.names = FALSE)

  cat("SoupX correction completed successfully\n")
  return(seurat_corrected)
}


#' Estimate soup (ambient RNA) fraction
#'
#' Extract contamination fraction from SoupX-corrected Seurat object
#'
#' @param seurat_obj Seurat object with SoupX metadata
#'
#' @return Contamination fraction (0-1)
#'
#' @export
estimate_soup_fraction <- function(seurat_obj) {
  if (is.null(seurat_obj@misc$soupx)) {
    warning("No SoupX metadata found in Seurat object")
    return(0.0)
  }
  return(seurat_obj@misc$soupx$contamination_fraction)
}


#' Plot SoupX correction results
#'
#' Visualize the impact of ambient RNA correction
#'
#' @param seurat_obj Seurat object with SoupX metadata
#' @param output_dir Directory to save plots
#'
#' @export
plot_soupx_results <- function(seurat_obj, output_dir = "results/soupx") {
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  contamination_fraction <- estimate_soup_fraction(seurat_obj)

  # Plot contamination estimate
  p <- ggplot(data.frame(value = contamination_fraction), aes(x = 1, y = value)) +
    geom_col(fill = "#4575b4", width = 0.5) +
    ylim(0, 0.5) +
    labs(
      title = "Estimated Ambient RNA Contamination",
      y = "Contamination Fraction",
      x = ""
    ) +
    theme_prism() +
    theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())

  ggsave(file.path(output_dir, "contamination_estimate.svg"),
         plot = p, width = 4, height = 6, dpi = 300)

  cat(sprintf("Contamination fraction: %.1f%%\n", contamination_fraction * 100))
}


#' Compare counts before and after SoupX correction
#'
#' @param seurat_before Seurat object before correction
#' @param seurat_after Seurat object after correction
#' @param marker_genes Vector of marker gene names to compare
#' @param output_dir Directory to save comparison plots
#'
#' @export
compare_before_after_soupx <- function(
  seurat_before,
  seurat_after,
  marker_genes = NULL,
  output_dir = "results/soupx"
) {
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  # Compare total counts per cell
  before_counts <- colSums(seurat_before@assays$RNA@counts)
  after_counts <- colSums(seurat_after@assays$RNA@counts)

  comparison_df <- data.frame(
    before = before_counts,
    after = after_counts
  )

  # Scatter plot
  p_scatter <- ggplot(comparison_df, aes(x = before, y = after)) +
    geom_point(alpha = 0.3, size = 0.5, color = "#4575b4") +
    geom_abline(slope = 1, intercept = 0, linetype = "dashed", color = "red") +
    labs(
      title = "Total Counts Before vs After Correction",
      x = "Before Correction",
      y = "After Correction"
    ) +
    theme_prism()

  ggsave(file.path(output_dir, "counts_comparison.svg"),
         plot = p_scatter, width = 6, height = 6, dpi = 300)

  # Summary statistics
  reduction_pct <- (1 - mean(after_counts) / mean(before_counts)) * 100

  cat(sprintf("Mean counts before: %.1f\n", mean(before_counts)))
  cat(sprintf("Mean counts after: %.1f\n", mean(after_counts)))
  cat(sprintf("Reduction: %.1f%%\n", reduction_pct))

  # If marker genes provided, compare their expression
  if (!is.null(marker_genes)) {
    marker_genes <- intersect(marker_genes, rownames(seurat_before))

    if (length(marker_genes) > 0) {
      before_expr <- as.matrix(seurat_before@assays$RNA@counts[marker_genes, ])
      after_expr <- as.matrix(seurat_after@assays$RNA@counts[marker_genes, ])

      marker_comparison <- data.frame(
        gene = rep(marker_genes, each = ncol(seurat_before)),
        before = as.vector(t(before_expr)),
        after = as.vector(t(after_expr))
      )

      p_markers <- ggplot(marker_comparison, aes(x = before, y = after)) +
        geom_point(alpha = 0.3, size = 0.5) +
        geom_abline(slope = 1, intercept = 0, linetype = "dashed", color = "red") +
        facet_wrap(~gene, scales = "free") +
        labs(
          title = "Marker Gene Expression Before vs After",
          x = "Before Correction",
          y = "After Correction"
        ) +
        theme_prism()

      ggsave(file.path(output_dir, "marker_comparison.svg"),
             plot = p_markers, width = 12, height = 8, dpi = 300)
    }
  }
}


#' Run SoupX with custom parameters for high-soup tissues
#'
#' Specialized function for tissues with high ambient RNA (brain, lung, tumor)
#'
#' @param raw_matrix_dir Path to raw_feature_bc_matrix/ directory
#' @param filtered_matrix_dir Path to filtered_feature_bc_matrix/ directory
#' @param output_dir Directory to save outputs
#'
#' @return Seurat object with corrected counts
#'
#' @export
run_soupx_high_soup <- function(
  raw_matrix_dir,
  filtered_matrix_dir,
  output_dir = "results/soupx"
) {
  # Use more aggressive settings for high-soup tissues
  seurat_corrected <- run_soupx_correction(
    raw_matrix_dir = raw_matrix_dir,
    filtered_matrix_dir = filtered_matrix_dir,
    output_dir = output_dir,
    auto_estimate = TRUE,
    contamination_range = c(0.05, 0.5)  # Higher expected contamination
  )

  contamination <- estimate_soup_fraction(seurat_corrected)

  if (contamination > 0.15) {
    cat("WARNING: High contamination detected (>15%).\n")
    cat("Consider reviewing filtering thresholds and data quality.\n")
  }

  return(seurat_corrected)
}


# Example usage
if (FALSE) {
  # Run SoupX correction
  seurat_corrected <- run_soupx_correction(
    raw_matrix_dir = "raw_feature_bc_matrix/",
    filtered_matrix_dir = "filtered_feature_bc_matrix/",
    output_dir = "results/soupx"
  )

  # Check contamination
  contamination <- estimate_soup_fraction(seurat_corrected)
  cat(sprintf("Contamination: %.1f%%\n", contamination * 100))

  # Plot results
  plot_soupx_results(seurat_corrected, output_dir = "results/soupx")
}

