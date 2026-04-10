#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 5) {
  cat("Usage: Rscript sc_slingshot_pseudotime.R <h5ad_file> <output_dir> <cluster_key> <use_rep> <start_cluster> [end_clusters]\n")
  quit(status = 1)
}

h5ad_file <- args[1]
output_dir <- args[2]
cluster_key <- args[3]
use_rep <- args[4]
start_cluster <- args[5]
end_clusters_raw <- if (length(args) >= 6) args[6] else ""

suppressPackageStartupMessages({
  library(slingshot)
  library(SingleCellExperiment)
  library(zellkonverter)
})

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

tryCatch({
  sce <- readH5AD(h5ad_file, reader = "R")
  meta <- as.data.frame(SummarizedExperiment::colData(sce))
  if (!cluster_key %in% colnames(meta)) {
    stop(sprintf("Cluster key '%s' not found in metadata", cluster_key))
  }
  if (!use_rep %in% reducedDimNames(sce)) {
    stop(sprintf("Embedding '%s' not found in reducedDims", use_rep))
  }

  embedding <- as.matrix(SingleCellExperiment::reducedDim(sce, use_rep))
  if (ncol(embedding) < 2) {
    stop(sprintf("Embedding '%s' has fewer than 2 dimensions", use_rep))
  }

  labels <- as.character(meta[[cluster_key]])
  start_arg <- if (nzchar(start_cluster)) start_cluster else NULL
  end_arg <- NULL
  if (nzchar(end_clusters_raw)) {
    end_arg <- strsplit(end_clusters_raw, ",", fixed = TRUE)[[1]]
    end_arg <- trimws(end_arg)
    end_arg <- end_arg[nzchar(end_arg)]
    if (!length(end_arg)) {
      end_arg <- NULL
    }
  }

  sl <- slingshot::slingshot(
    data = embedding,
    clusterLabels = labels,
    start.clus = start_arg,
    end.clus = end_arg
  )

  pseudotime_df <- as.data.frame(slingshot::slingPseudotime(sl))
  if (ncol(pseudotime_df) == 0) {
    stop("Slingshot did not return any pseudotime columns")
  }
  colnames(pseudotime_df) <- paste0("Lineage", seq_len(ncol(pseudotime_df)))

  primary_pseudotime <- apply(pseudotime_df, 1, function(x) {
    if (all(is.na(x))) {
      return(NA_real_)
    }
    mean(x, na.rm = TRUE)
  })

  branch_df <- as.data.frame(slingshot::slingBranchID(sl))
  colnames(branch_df) <- paste0("Lineage", seq_len(ncol(branch_df)))

  pseudotime_out <- data.frame(
    cell_id = colnames(sce),
    slingshot_pseudotime = as.numeric(primary_pseudotime),
    pseudotime_df,
    stringsAsFactors = FALSE
  )

  branch_out <- data.frame(
    cell_id = colnames(sce),
    branch_df,
    stringsAsFactors = FALSE
  )

  curves <- slingshot::slingCurves(sl)
  curve_rows <- list()
  if (length(curves) > 0) {
    for (idx in seq_along(curves)) {
      curve <- curves[[idx]]
      coords <- as.matrix(curve$s)
      if (ncol(coords) < 2) {
        next
      }
      lineage_name <- names(curves)[idx]
      lineage_name <- paste0("Lineage", idx)
      curve_rows[[length(curve_rows) + 1]] <- data.frame(
        lineage = lineage_name,
        order = seq_len(nrow(coords)),
        coord1 = coords[, 1],
        coord2 = coords[, 2],
        stringsAsFactors = FALSE
      )
    }
  }
  curves_out <- if (length(curve_rows)) do.call(rbind, curve_rows) else data.frame(
    lineage = character(0),
    order = integer(0),
    coord1 = numeric(0),
    coord2 = numeric(0),
    stringsAsFactors = FALSE
  )
  write.csv(pseudotime_out, file.path(output_dir, "slingshot_pseudotime.csv"), quote = FALSE, row.names = FALSE)
  write.csv(branch_out, file.path(output_dir, "slingshot_branches.csv"), quote = FALSE, row.names = FALSE)
  write.csv(curves_out, file.path(output_dir, "slingshot_curves.csv"), quote = FALSE, row.names = FALSE)
}, error = function(e) {
  cat(sprintf("ERROR: %s\n", e$message), file = stderr())
  quit(status = 1)
})
