# ============================================================================
# EXPORT RESULTS
# ============================================================================
#
# Save processed Seurat object, tables, and figures.
#
# Functions:
#   - export_all(): Export all results (recommended, follows Agent Skills standard)
#   - export_seurat_results(): Alias for export_all()
#   - export_seurat_object(): Save Seurat object to RDS
#   - export_count_matrices(): Export normalized/scaled counts
#   - export_metadata(): Export cell metadata
#   - export_dimreductions(): Export UMAP/PCA coordinates
#   - create_summary_report(): Generate summary report
#
# Usage:
#   source("scripts/export_results.R")
#   export_all(seurat_obj, output_dir = "results")

library(dplyr)

#' Export all Seurat analysis results
#'
#' One-stop function to export everything following Agent Skills standard.
#'
#' @param seurat_obj Processed Seurat object
#' @param output_dir Output directory (default: "results")
#' @param all_markers Optional marker genes data frame to export
#' @param resolution Resolution to use for cluster info (NULL for active idents)
#' @param export_counts Export normalized counts (default: TRUE)
#' @param export_metadata Export cell metadata (default: TRUE)
#' @param export_dimreductions Export dimension reduction coordinates (default: TRUE)
#' @param create_summary Create summary report (default: TRUE)
#' @export
export_all <- function(seurat_obj,
                       output_dir = "results",
                       all_markers = NULL,
                       resolution = NULL,
                       export_counts = TRUE,
                       export_metadata = TRUE,
                       export_dimreductions = TRUE,
                       create_summary = TRUE) {

  message("\n=== Exporting Results ===")
  message("Output directory: ", output_dir)

  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  # 1. Export Seurat object (CRITICAL for downstream skills)
  export_seurat_object(seurat_obj, output_dir)
  message("  (Load with: seurat_obj <- readRDS('", file.path(output_dir, "seurat_processed.rds"), "'))")

  # 2. Export count matrices
  if (export_counts) {
    export_count_matrices(seurat_obj, output_dir)
  }

  # 3. Export metadata
  if (export_metadata) {
    export_metadata(seurat_obj, output_dir, resolution)
  }

  # 4. Export dimension reductions
  if (export_dimreductions) {
    export_dimreductions(seurat_obj, output_dir)
  }

  # 5. Export marker genes if provided
  if (!is.null(all_markers)) {
    export_markers(all_markers, output_dir)
  }

  # 6. Create summary statistics
  if (create_summary) {
    export_summary_stats(seurat_obj, output_dir)
  }

  message("\n=== Export Complete ===")
  message("All results saved in: ", output_dir)
}

#' Export all Seurat analysis results (Alias for export_all)
#'
#' This is an alias for export_all() for backwards compatibility.
#'
#' @inheritParams export_all
#' @export
export_seurat_results <- function(seurat_obj,
                                  output_dir = "results",
                                  all_markers = NULL,
                                  resolution = NULL,
                                  export_counts = TRUE,
                                  export_metadata = TRUE,
                                  export_dimreductions = TRUE,
                                  create_summary = TRUE) {

  export_all(seurat_obj, output_dir, all_markers, resolution,
             export_counts, export_metadata, export_dimreductions, create_summary)
}

#' Export Seurat object to RDS file
#'
#' @param seurat_obj Seurat object
#' @param output_dir Output directory
#' @param filename Filename (default: "seurat_processed.rds")
#' @export
export_seurat_object <- function(seurat_obj,
                                 output_dir,
                                 filename = "seurat_processed.rds") {

  message("Exporting Seurat object...")

  output_file <- file.path(output_dir, filename)

  # Try primary path, then fallback to tempdir if write fails
  write_targets <- c(output_file, file.path(tempdir(), filename))
  for (i in seq_along(write_targets)) {
    result <- tryCatch({
      saveRDS(seurat_obj, file = write_targets[i])
      # If we used fallback, copy to original location
      if (i > 1) {
        file.copy(write_targets[i], output_file, overwrite = TRUE)
        message("  (Used fallback write path, copied to ", output_file, ")")
      }
      TRUE
    }, error = function(e) {
      if (i == 1) {
        message("  WARNING: Primary save failed: ", conditionMessage(e), ". Trying fallback path...")
      }
      FALSE
    })
    if (isTRUE(result)) break
    if (i == length(write_targets) && !isTRUE(result)) {
      stop("Failed to save RDS file to all paths")
    }
  }

  # Verify file integrity
  file_size <- file.info(output_file)$size / (1024^2)  # MB
  if (file_size < 0.01) {
    message(sprintf("  WARNING: File suspiciously small (%.3f MB). May be corrupted.", file_size))
  } else {
    message(sprintf("  Saved: %s (%.1f MB)", output_file, file_size))
  }
}

#' Export count matrices
#'
#' @param seurat_obj Seurat object
#' @param output_dir Output directory
#' @param which Which matrices to export: "normalized", "scaled", or "both" (default: "normalized")
#' @export
export_count_matrices <- function(seurat_obj,
                                  output_dir,
                                  which = "normalized") {

  message("Exporting count matrices...")

  # Export normalized counts
  if (which %in% c("normalized", "both")) {
    message("  Exporting normalized counts (this may take a while for large datasets)...")

    norm_counts <- GetAssayData(seurat_obj, slot = "data")

    # Convert sparse matrix to dense for export (optional: keep sparse)
    norm_counts_dense <- as.matrix(norm_counts)

    output_file <- file.path(output_dir, "normalized_counts.csv")
    write.csv(norm_counts_dense, output_file)
    message("    Saved: ", output_file)

    # Also save as RDS for faster loading
    output_rds <- file.path(output_dir, "normalized_counts.rds")
    saveRDS(norm_counts, output_rds)
    message("    Saved: ", output_rds, " (sparse format)")
  }

  # Export scaled counts (if available)
  if (which %in% c("scaled", "both")) {
    if ("scale.data" %in% slotNames(seurat_obj@assays$RNA)) {
      message("  Exporting scaled counts...")

      scaled_counts <- GetAssayData(seurat_obj, slot = "scale.data")

      if (ncol(scaled_counts) > 0) {
        output_file <- file.path(output_dir, "scaled_counts.csv")
        write.csv(as.matrix(scaled_counts), output_file)
        message("    Saved: ", output_file)
      } else {
        message("    No scaled data available")
      }
    }
  }
}

#' Export cell metadata
#'
#' @param seurat_obj Seurat object
#' @param output_dir Output directory
#' @param resolution Resolution to include (NULL for active idents)
#' @export
export_metadata <- function(seurat_obj, output_dir, resolution = NULL) {

  message("Exporting cell metadata...")

  # Get metadata
  metadata <- seurat_obj@meta.data

  # Add active identity
  metadata$active_ident <- Idents(seurat_obj)

  # Add specific resolution if requested
  if (!is.null(resolution)) {
    col_name <- paste0("RNA_snn_res.", resolution)
    if (col_name %in% colnames(metadata)) {
      metadata$selected_clusters <- metadata[[col_name]]
    }
  }

  # Export
  output_file <- file.path(output_dir, "cell_metadata.csv")
  write.csv(metadata, output_file)

  message(sprintf("  Saved: %s (%d cells, %d columns)",
                  output_file, nrow(metadata), ncol(metadata)))
}

#' Export dimension reduction coordinates
#'
#' @param seurat_obj Seurat object
#' @param output_dir Output directory
#' @param reductions Which reductions to export (default: c("pca", "umap"))
#' @export
export_dimreductions <- function(seurat_obj,
                                output_dir,
                                reductions = c("pca", "umap")) {

  message("Exporting dimension reduction coordinates...")

  available_reductions <- names(seurat_obj@reductions)

  for (reduction in reductions) {
    if (reduction %in% available_reductions) {
      coords <- Embeddings(seurat_obj, reduction = reduction)

      output_file <- file.path(output_dir, paste0(reduction, "_coordinates.csv"))
      write.csv(coords, output_file)

      message(sprintf("  Saved: %s (%d cells, %d dimensions)",
                      output_file, nrow(coords), ncol(coords)))
    } else {
      message("  ", reduction, " not found, skipping")
    }
  }
}

#' Export marker gene tables (wrapper)
#'
#' @param all_markers Marker genes data frame from find_markers.R
#' @param output_dir Output directory
#' @export
export_markers <- function(all_markers, output_dir) {

  message("Exporting marker gene tables...")

  # Load find_markers script for export function
  source("scripts/find_markers.R")

  # Export using the function from find_markers.R
  export_marker_tables(all_markers, output_dir)
}

#' Create summary statistics table
#'
#' @param seurat_obj Seurat object
#' @param output_dir Output directory
#' @export
export_summary_stats <- function(seurat_obj, output_dir) {

  message("Creating summary statistics...")

  # Collect summary statistics
  summary_stats <- data.frame(
    Metric = c(
      "Total Cells",
      "Total Genes",
      "Median Genes per Cell",
      "Median UMIs per Cell",
      "Median % Mitochondrial",
      "Number of Clusters",
      "Default Assay",
      "Available Reductions"
    ),
    Value = c(
      ncol(seurat_obj),
      nrow(seurat_obj),
      round(median(seurat_obj$nFeature_RNA), 0),
      round(median(seurat_obj$nCount_RNA), 0),
      round(median(seurat_obj$percent.mt), 2),
      length(unique(Idents(seurat_obj))),
      DefaultAssay(seurat_obj),
      paste(names(seurat_obj@reductions), collapse = ", ")
    )
  )

  # Save
  output_file <- file.path(output_dir, "analysis_summary.csv")
  write.csv(summary_stats, output_file, row.names = FALSE)

  message("  Saved: ", output_file)

  # Print to console
  message("\nAnalysis Summary:")
  print(summary_stats)

  return(summary_stats)
}

