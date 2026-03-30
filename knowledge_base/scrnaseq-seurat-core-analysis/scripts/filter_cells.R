# ============================================================================
# CELL FILTERING BY QC METRICS
# ============================================================================
#
# This script filters cells based on QC thresholds.
#
# Functions:
#   - filter_cells_by_qc(): Filter cells using QC thresholds
#   - filter_cells_by_tissue(): Filter using tissue-specific thresholds
#   - compare_before_after_filtering(): Generate comparison plots
#
# Usage:
#   source("scripts/filter_cells.R")
#   seurat_filtered <- filter_cells_by_qc(seurat_obj, min_features = 200,
#                                          max_features = 2500, max_mt_percent = 5)

#' Filter cells based on QC thresholds
#'
#' @param seurat_obj Seurat object with QC metrics calculated
#' @param min_features Minimum number of genes detected
#' @param max_features Maximum number of genes detected (to remove doublets)
#' @param max_mt_percent Maximum percentage of mitochondrial reads
#' @param min_counts Minimum UMI counts (optional)
#' @param max_counts Maximum UMI counts (optional)
#' @return Filtered Seurat object
#' @export
filter_cells_by_qc <- function(seurat_obj,
                               min_features = 200,
                               max_features = 5000,
                               max_mt_percent = 10,
                               min_counts = NULL,
                               max_counts = NULL) {

  # Store original cell count
  n_cells_before <- ncol(seurat_obj)

  message("Filtering cells with thresholds:")
  message(sprintf("  min_features: %d", min_features))
  message(sprintf("  max_features: %d", max_features))
  message(sprintf("  max_mt_percent: %.1f%%", max_mt_percent))

  # Apply filters
  cells_to_keep <- seurat_obj$nFeature_RNA >= min_features &
                   seurat_obj$nFeature_RNA <= max_features &
                   seurat_obj$percent.mt <= max_mt_percent

  # Apply count filters if specified
  if (!is.null(min_counts)) {
    message(sprintf("  min_counts: %d", min_counts))
    cells_to_keep <- cells_to_keep & seurat_obj$nCount_RNA >= min_counts
  }

  if (!is.null(max_counts)) {
    message(sprintf("  max_counts: %d", max_counts))
    cells_to_keep <- cells_to_keep & seurat_obj$nCount_RNA <= max_counts
  }

  # Subset Seurat object
  seurat_filtered <- subset(seurat_obj, cells = colnames(seurat_obj)[cells_to_keep])

  # Report filtering results
  n_cells_after <- ncol(seurat_filtered)
  n_cells_removed <- n_cells_before - n_cells_after
  percent_removed <- (n_cells_removed / n_cells_before) * 100

  message(sprintf("\nFiltering complete:"))
  message(sprintf("  Cells before: %d", n_cells_before))
  message(sprintf("  Cells after: %d", n_cells_after))
  message(sprintf("  Cells removed: %d (%.1f%%)", n_cells_removed, percent_removed))

  # Warning if too many cells removed
  if (percent_removed > 50) {
    warning("More than 50% of cells were removed. Consider relaxing thresholds.")
  }

  # Warning if very few cells remain
  if (n_cells_after < 100) {
    warning("Fewer than 100 cells remaining. Analysis may not be reliable.")
  }

  return(seurat_filtered)
}

#' Filter cells using tissue-specific thresholds
#'
#' @param seurat_obj Seurat object with QC metrics calculated
#' @param tissue Tissue type (e.g., "pbmc", "brain", "tumor")
#' @return Filtered Seurat object
#' @export
filter_cells_by_tissue <- function(seurat_obj, tissue) {

  # Load QC metrics script to get thresholds
  source("scripts/qc_metrics.R")

  # Get tissue-specific thresholds
  thresholds <- get_tissue_qc_thresholds(tissue)

  # Apply filtering
  seurat_filtered <- filter_cells_by_qc(
    seurat_obj,
    min_features = thresholds$min_features,
    max_features = thresholds$max_features,
    max_mt_percent = thresholds$max_mt
  )

  return(seurat_filtered)
}

#' Compare QC metrics before and after filtering
#'
#' @param seurat_before Seurat object before filtering
#' @param seurat_after Seurat object after filtering
#' @param output_dir Output directory for plots
#' @export
compare_before_after_filtering <- function(seurat_before,
                                           seurat_after,
                                           output_dir = NULL) {

  library(ggplot2)
  library(ggprism)
  library(patchwork)

  message("Generating before/after filtering comparison")

  # Combine metadata
  meta_before <- seurat_before@meta.data
  meta_before$filter_status <- "Before Filtering"

  meta_after <- seurat_after@meta.data
  meta_after$filter_status <- "After Filtering"

  # Add cells that were removed
  cells_removed <- setdiff(colnames(seurat_before), colnames(seurat_after))
  meta_removed <- seurat_before@meta.data[cells_removed, ]
  meta_removed$filter_status <- "Removed"

  combined_meta <- rbind(
    cbind(meta_before, type = "original"),
    cbind(meta_after, type = "filtered")
  )

  # Create comparison plots
  p1 <- ggplot(combined_meta, aes(x = filter_status, y = nFeature_RNA, fill = type)) +
    geom_violin() +
    geom_boxplot(width = 0.1, fill = "white", outlier.shape = NA) +
    labs(
      x = "",
      y = "Genes Detected (nFeature_RNA)",
      title = "Genes per Cell"
    ) +
    theme_prism() +
    theme(legend.position = "none")

  p2 <- ggplot(combined_meta, aes(x = filter_status, y = percent.mt, fill = type)) +
    geom_violin() +
    geom_boxplot(width = 0.1, fill = "white", outlier.shape = NA) +
    labs(
      x = "",
      y = "% Mitochondrial",
      title = "Mitochondrial %"
    ) +
    theme_prism() +
    theme(legend.position = "none")

  # Summary statistics table
  summary_stats <- data.frame(
    Metric = c("Total Cells", "Mean Genes", "Median Genes", "Mean % MT", "Median % MT"),
    Before = c(
      ncol(seurat_before),
      round(mean(seurat_before$nFeature_RNA), 0),
      round(median(seurat_before$nFeature_RNA), 0),
      round(mean(seurat_before$percent.mt), 2),
      round(median(seurat_before$percent.mt), 2)
    ),
    After = c(
      ncol(seurat_after),
      round(mean(seurat_after$nFeature_RNA), 0),
      round(median(seurat_after$nFeature_RNA), 0),
      round(mean(seurat_after$percent.mt), 2),
      round(median(seurat_after$percent.mt), 2)
    )
  )

  message("\nFiltering Summary:")
  print(summary_stats)

  # Save comparison plots if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    combined <- p1 | p2

    svg_file <- file.path(output_dir, "filtering_comparison.svg")
    ggsave(svg_file, plot = combined, width = 10, height = 5, dpi = 300)
    message("  Saved: ", svg_file)

    # Save summary table
    summary_file <- file.path(output_dir, "filtering_summary.csv")
    write.csv(summary_stats, summary_file, row.names = FALSE)
    message("  Saved: ", summary_file)
  }

  return(list(plot = p1 | p2, summary = summary_stats))
}


#' Run DoubletFinder for doublet detection
#'
#' Detects doublets (cells containing RNA from 2+ cells) using DoubletFinder.
#' Optionally runs per batch to account for batch-specific doublet rates.
#'
#' @param seurat_obj Seurat object (normalized and processed through PCA)
#' @param batch_col Column in metadata containing batch labels (optional)
#'   If provided, runs DoubletFinder per batch separately
#' @param expected_doublet_rate Expected doublet rate (default: 0.06 for 6%)
#'   Typical rates: 0.04 for <5k cells, 0.06 for 5-10k, 0.08 for 10-15k
#' @param pcs Principal components to use (default: 1:30)
#' @param pK_value pK parameter (default: NULL for auto-detection)
#' @param verbose Print progress messages (default: TRUE)
#'
#' @return Seurat object with doublet predictions added to metadata
#'
#' @details
#' Adds metadata columns:
#'   - DF.classifications: "Singlet" or "Doublet"
#'   - pANN: Doublet score (0-1, higher = more likely doublet)
#'   - predicted_doublet: Logical doublet flag
#'
#' @export
run_doubletfinder <- function(
  seurat_obj,
  batch_col = NULL,
  expected_doublet_rate = 0.06,
  pcs = 1:30,
  pK_value = NULL,
  verbose = TRUE
) {
  # Check DoubletFinder package
  if (!requireNamespace("DoubletFinder", quietly = TRUE)) {
    stop("DoubletFinder package required.\n",
         "Install with: remotes::install_github('chris-mcginnis-ucsf/DoubletFinder')")
  }

  library(DoubletFinder)

  if (verbose) {
    cat("=" %R% 60, "\n")
    cat("DoubletFinder Doublet Detection\n")
    cat("=" %R% 60, "\n\n")
  }

  # Check if object is processed
  if (!"pca" %in% names(seurat_obj@reductions)) {
    stop("PCA not found. Please run NormalizeData, FindVariableFeatures, ScaleData, and RunPCA first.")
  }

  # Run per batch if specified
  if (!is.null(batch_col)) {
    if (!batch_col %in% colnames(seurat_obj@meta.data)) {
      stop(sprintf("Batch column '%s' not found in metadata", batch_col))
    }

    if (verbose) {
      n_batches <- length(unique(seurat_obj@meta.data[[batch_col]]))
      cat(sprintf("Running DoubletFinder per batch...\n"))
      cat(sprintf("  Batches: %d (%s)\n", n_batches, batch_col))
      cat(sprintf("  Expected doublet rate: %.1f%%\n\n", expected_doublet_rate * 100))
    }

    # Split by batch and run DoubletFinder
    batches <- unique(seurat_obj@meta.data[[batch_col]])
    all_classifications <- character(ncol(seurat_obj))
    all_scores <- numeric(ncol(seurat_obj))
    names(all_classifications) <- colnames(seurat_obj)
    names(all_scores) <- colnames(seurat_obj)

    for (batch in batches) {
      if (verbose) {
        cat(sprintf("  Processing batch: %s\n", batch))
      }

      batch_cells <- colnames(seurat_obj)[seurat_obj@meta.data[[batch_col]] == batch]
      batch_obj <- subset(seurat_obj, cells = batch_cells)

      # Ensure processing steps are run on batch
      batch_obj <- NormalizeData(batch_obj, verbose = FALSE)
      batch_obj <- FindVariableFeatures(batch_obj, verbose = FALSE)
      batch_obj <- ScaleData(batch_obj, verbose = FALSE)
      batch_obj <- RunPCA(batch_obj, npcs = max(pcs), verbose = FALSE)
      batch_obj <- FindNeighbors(batch_obj, dims = pcs, verbose = FALSE)
      batch_obj <- FindClusters(batch_obj, resolution = 0.5, verbose = FALSE)
      batch_obj <- RunUMAP(batch_obj, dims = pcs, verbose = FALSE)

      # Optimal pK parameter
      if (is.null(pK_value)) {
        if (verbose) {
          cat("    Finding optimal pK...\n")
        }
        sweep_res <- paramSweep_v3(batch_obj, PCs = pcs, sct = FALSE)
        sweep_stats <- summarizeSweep(sweep_res, GT = FALSE)
        bcmvn <- find.pK(sweep_stats)
        pK_optimal <- as.numeric(as.character(bcmvn$pK[which.max(bcmvn$BCmetric)]))
      } else {
        pK_optimal <- pK_value
      }

      if (verbose) {
        cat(sprintf("    Using pK = %.2f\n", pK_optimal))
      }

      # Estimate homotypic doublet proportion
      annotations <- batch_obj@meta.data$seurat_clusters
      homotypic_prop <- modelHomotypic(annotations)
      nExp_poi <- round(expected_doublet_rate * ncol(batch_obj))
      nExp_poi_adj <- round(nExp_poi * (1 - homotypic_prop))

      if (verbose) {
        cat(sprintf("    Expected doublets: %d (adjusted: %d)\n", nExp_poi, nExp_poi_adj))
      }

      # Run DoubletFinder
      batch_obj <- doubletFinder_v3(
        batch_obj,
        PCs = pcs,
        pN = 0.25,
        pK = pK_optimal,
        nExp = nExp_poi_adj,
        reuse.pANN = FALSE,
        sct = FALSE
      )

      # Extract results
      df_cols <- grep("^DF.classifications", colnames(batch_obj@meta.data), value = TRUE)
      pann_cols <- grep("^pANN", colnames(batch_obj@meta.data), value = TRUE)

      all_classifications[batch_cells] <- batch_obj@meta.data[[df_cols[1]]]
      all_scores[batch_cells] <- batch_obj@meta.data[[pann_cols[1]]]

      if (verbose) {
        n_doublets <- sum(batch_obj@meta.data[[df_cols[1]]] == "Doublet")
        cat(sprintf("    Doublets detected: %d (%.1f%%)\n\n",
                    n_doublets, 100 * n_doublets / ncol(batch_obj)))
      }
    }

    # Add to main object
    seurat_obj@meta.data$DF.classifications <- all_classifications
    seurat_obj@meta.data$pANN <- all_scores
    seurat_obj@meta.data$predicted_doublet <- all_classifications == "Doublet"

  } else {
    # Run on full dataset (no batches)
    if (verbose) {
      cat("Running DoubletFinder on full dataset...\n")
      cat(sprintf("  Expected doublet rate: %.1f%%\n\n", expected_doublet_rate * 100))
    }

    # Ensure processing steps
    if (!"umap" %in% names(seurat_obj@reductions)) {
      seurat_obj <- FindNeighbors(seurat_obj, dims = pcs, verbose = FALSE)
      seurat_obj <- FindClusters(seurat_obj, resolution = 0.5, verbose = FALSE)
      seurat_obj <- RunUMAP(seurat_obj, dims = pcs, verbose = FALSE)
    }

    # Optimal pK
    if (is.null(pK_value)) {
      if (verbose) {
        cat("  Finding optimal pK...\n")
      }
      sweep_res <- paramSweep_v3(seurat_obj, PCs = pcs, sct = FALSE)
      sweep_stats <- summarizeSweep(sweep_res, GT = FALSE)
      bcmvn <- find.pK(sweep_stats)
      pK_optimal <- as.numeric(as.character(bcmvn$pK[which.max(bcmvn$BCmetric)]))
    } else {
      pK_optimal <- pK_value
    }

    if (verbose) {
      cat(sprintf("  Using pK = %.2f\n", pK_optimal))
    }

    # Estimate homotypic doublets
    annotations <- seurat_obj@meta.data$seurat_clusters
    homotypic_prop <- modelHomotypic(annotations)
    nExp_poi <- round(expected_doublet_rate * ncol(seurat_obj))
    nExp_poi_adj <- round(nExp_poi * (1 - homotypic_prop))

    if (verbose) {
      cat(sprintf("  Expected doublets: %d (adjusted: %d)\n", nExp_poi, nExp_poi_adj))
    }

    # Run DoubletFinder
    seurat_obj <- doubletFinder_v3(
      seurat_obj,
      PCs = pcs,
      pN = 0.25,
      pK = pK_optimal,
      nExp = nExp_poi_adj,
      reuse.pANN = FALSE,
      sct = FALSE
    )

    # Rename columns
    df_cols <- grep("^DF.classifications", colnames(seurat_obj@meta.data), value = TRUE)
    pann_cols <- grep("^pANN", colnames(seurat_obj@meta.data), value = TRUE)

    seurat_obj@meta.data$DF.classifications <- seurat_obj@meta.data[[df_cols[1]]]
    seurat_obj@meta.data$pANN <- seurat_obj@meta.data[[pann_cols[1]]]
    seurat_obj@meta.data$predicted_doublet <- seurat_obj@meta.data$DF.classifications == "Doublet"

    # Clean up temporary columns
    seurat_obj@meta.data[[df_cols[1]]] <- NULL
    seurat_obj@meta.data[[pann_cols[1]]] <- NULL
  }

  # Summary
  n_doublets <- sum(seurat_obj@meta.data$predicted_doublet, na.rm = TRUE)
  pct_doublets <- 100 * n_doublets / ncol(seurat_obj)

  if (verbose) {
    cat("\n" %R% "=" %R% 60, "\n")
    cat("DoubletFinder complete!\n")
    cat("=" %R% 60, "\n\n")
    cat(sprintf("Total doublets detected: %d (%.1f%%)\n", n_doublets, pct_doublets))
    cat("\nAdded to metadata:\n")
    cat("  - DF.classifications: 'Singlet' or 'Doublet'\n")
    cat("  - pANN: Doublet score (0-1)\n")
    cat("  - predicted_doublet: Logical doublet flag\n\n")
  }

  return(seurat_obj)
}


#' Filter cells based on MAD outlier detection
#'
#' Applies batch-aware MAD outlier detection from qc_metrics.R.
#'
#' @param seurat_obj Seurat object with QC metrics
#' @param batch_col Column in metadata with batch labels (default: 'batch')
#' @param nmads Number of MADs for outlier threshold (default: 5)
#'
#' @return Filtered Seurat object
#'
#' @export
filter_by_mad_outliers <- function(
  seurat_obj,
  batch_col = "batch",
  nmads = 5
) {
  # Source QC metrics script
  source("scripts/qc_metrics.R")

  # Mark outliers using MAD
  seurat_obj <- batch_mad_outlier_detection(
    seurat_obj,
    batch_col = batch_col,
    nmads = nmads
  )

  # Filter
  n_before <- ncol(seurat_obj)
  seurat_filtered <- subset(seurat_obj, subset = outlier == FALSE)
  n_after <- ncol(seurat_filtered)

  cat(sprintf("\nMAD filtering results:\n"))
  cat(sprintf("  Cells before: %d\n", n_before))
  cat(sprintf("  Cells after: %d\n", n_after))
  cat(sprintf("  Cells removed: %d (%.1f%%)\n",
              n_before - n_after, 100 * (n_before - n_after) / n_before))

  return(seurat_filtered)
}


#' Combine all filters and apply to Seurat object
#'
#' Combines QC thresholds, doublet detection, and MAD outlier detection.
#'
#' @param seurat_obj Seurat object with QC metrics
#' @param use_mad Use MAD outlier detection (default: TRUE)
#' @param use_doubletfinder Use DoubletFinder (default: TRUE)
#' @param use_fixed_thresholds Use fixed tissue thresholds (default: FALSE)
#' @param tissue Tissue type for fixed thresholds (default: 'pbmc')
#' @param batch_col Batch column for per-batch processing (default: 'batch')
#' @param expected_doublet_rate Doublet rate (default: 0.06)
#' @param remove_doublets Remove predicted doublets (default: TRUE)
#' @param doublet_score_threshold Doublet score threshold (default: 0.25)
#'
#' @return Filtered Seurat object
#'
#' @export
combine_filters_and_apply <- function(
  seurat_obj,
  use_mad = TRUE,
  use_doubletfinder = TRUE,
  use_fixed_thresholds = FALSE,
  tissue = "pbmc",
  batch_col = "batch",
  expected_doublet_rate = 0.06,
  remove_doublets = TRUE,
  doublet_score_threshold = 0.25
) {
  cat("Applying combined filtering strategy...\n\n")

  n_original <- ncol(seurat_obj)

  # Source QC metrics script
  source("scripts/qc_metrics.R")

  # Step 1: Mark outliers
  if (use_mad) {
    cat("Step 1: Batch-aware MAD outlier detection\n")
    seurat_obj <- batch_mad_outlier_detection(
      seurat_obj,
      batch_col = batch_col,
      nmads = 5
    )
  } else if (use_fixed_thresholds) {
    cat("Step 1: Fixed tissue-specific thresholds\n")
    seurat_obj <- mark_outliers_fixed(seurat_obj, tissue = tissue)
  } else {
    seurat_obj@meta.data$outlier <- FALSE
  }

  # Step 2: Doublet detection
  if (use_doubletfinder) {
    cat("\nStep 2: DoubletFinder doublet detection\n")
    seurat_obj <- run_doubletfinder(
      seurat_obj,
      batch_col = batch_col,
      expected_doublet_rate = expected_doublet_rate,
      verbose = TRUE
    )
  } else {
    seurat_obj@meta.data$predicted_doublet <- FALSE
  }

  # Step 3: Combine filters
  cat("\nStep 3: Applying combined filters\n")

  keep_cells <- !seurat_obj@meta.data$outlier

  if (remove_doublets && use_doubletfinder) {
    keep_cells <- keep_cells & !seurat_obj@meta.data$predicted_doublet
  }

  # Filter
  seurat_filtered <- subset(seurat_obj, cells = colnames(seurat_obj)[keep_cells])

  # Summary
  n_final <- ncol(seurat_filtered)
  n_removed_qc <- sum(seurat_obj@meta.data$outlier)
  n_removed_doublets <- if (use_doubletfinder && remove_doublets) {
    sum(seurat_obj@meta.data$predicted_doublet)
  } else {
    0
  }
  n_total_removed <- n_original - n_final

  cat("\n" %R% "=" %R% 60, "\n")
  cat("Combined filtering complete!\n")
  cat("=" %R% 60, "\n\n")
  cat("Filtering summary:\n")
  cat(sprintf("  Original cells: %d\n", n_original))
  cat(sprintf("  Removed (QC outliers): %d (%.1f%%)\n",
              n_removed_qc, 100 * n_removed_qc / n_original))
  cat(sprintf("  Removed (doublets): %d (%.1f%%)\n",
              n_removed_doublets, 100 * n_removed_doublets / n_original))
  cat(sprintf("  Total removed: %d (%.1f%%)\n",
              n_total_removed, 100 * n_total_removed / n_original))
  cat(sprintf("  Final cells: %d (%.1f%%)\n\n",
              n_final, 100 * n_final / n_original))

  return(seurat_filtered)
}

