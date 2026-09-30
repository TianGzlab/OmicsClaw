#!/usr/bin/env Rscript
# sc_monocle3_r.R — Monocle3 principal graph pseudotime via R bridge
#
# Usage:
#   Rscript sc_monocle3_r.R <h5ad_file> <output_dir> <cluster_key> <use_rep> [root_cluster] [root_pr_nodes]
#
# Outputs:
#   monocle3_pseudotime.csv  — cell_id, monocle3_pseudotime, monocle3_cluster, monocle3_partition
#   monocle3_trajectory.csv  — principal graph edges (x_start, y_start, x_end, y_end)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  cat("Usage: Rscript sc_monocle3_r.R <h5ad_file> <output_dir> [cluster_key] [use_rep] [root_cluster] [root_pr_nodes]\n")
  quit(status = 1)
}

h5ad_file    <- args[1]
output_dir   <- args[2]
cluster_key  <- if (length(args) >= 3 && nzchar(args[3])) args[3] else "leiden"
use_rep      <- if (length(args) >= 4 && nzchar(args[4])) args[4] else "X_umap"
root_cluster <- if (length(args) >= 5 && nzchar(args[5])) args[5] else "auto"
root_pr_nodes_arg <- if (length(args) >= 6 && nzchar(args[6])) args[6] else "auto"

# Ensure RETICULATE_PYTHON is set for cluster_cells() leiden
if (nchar(Sys.getenv("RETICULATE_PYTHON")) == 0) {
  conda_prefix <- Sys.getenv("CONDA_PREFIX")
  if (nchar(conda_prefix) > 0) {
    Sys.setenv(RETICULATE_PYTHON = file.path(conda_prefix, "bin", "python"))
  }
}

suppressPackageStartupMessages({
  library(monocle3)
  library(SingleCellExperiment)
  library(SummarizedExperiment)
  library(zellkonverter)
  library(igraph)
})

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

# ---------------------------------------------------------------------------
# Helper: auto-select root principal graph node
# ---------------------------------------------------------------------------
.auto_select_root <- function(cds, cluster_key, root_cluster, umap_mat) {
  cell_meta <- as.data.frame(SummarizedExperiment::colData(cds))

  # Determine root cluster
  if (is.null(root_cluster) || root_cluster == "auto") {
    # Use cluster with most cells
    if (cluster_key %in% colnames(cell_meta)) {
      tbl <- sort(table(as.character(cell_meta[[cluster_key]])), decreasing = TRUE)
    } else {
      # fallback: use monocle3 clusters
      tbl <- sort(table(as.character(monocle3::clusters(cds))), decreasing = TRUE)
    }
    root_cluster <- names(tbl)[1]
    cat("Auto-selected root cluster:", root_cluster, "\n")
  }

  # Get root cluster cells mask
  if (cluster_key %in% colnames(cell_meta)) {
    root_cells_mask <- as.character(cell_meta[[cluster_key]]) == as.character(root_cluster)
  } else {
    root_cells_mask <- as.character(monocle3::clusters(cds)) == as.character(root_cluster)
  }

  if (sum(root_cells_mask) == 0) {
    cat("WARNING: root cluster '", root_cluster, "' has no cells. Falling back to largest cluster.\n")
    tbl <- sort(table(as.character(monocle3::clusters(cds))), decreasing = TRUE)
    root_cluster <- names(tbl)[1]
    root_cells_mask <- as.character(monocle3::clusters(cds)) == root_cluster
  }

  # Get UMAP coords of root cluster cells
  cell_umap <- umap_mat[root_cells_mask, 1:2, drop = FALSE]
  centroid <- colMeans(cell_umap)

  # Get principal graph node positions
  pr_graph_aux <- cds@principal_graph_aux[["UMAP"]]
  if (!is.null(pr_graph_aux) && !is.null(pr_graph_aux$dp_mst)) {
    pr_node_coords <- t(as.matrix(pr_graph_aux$dp_mst))  # n_nodes x 2
  } else {
    # Fallback: use igraph layout from the principal graph
    pr_graph <- monocle3::principal_graph(cds)[["UMAP"]]
    pr_node_coords <- igraph::layout_with_fr(pr_graph)
    rownames(pr_node_coords) <- igraph::V(pr_graph)$name
  }

  # Find nearest principal node to centroid
  dists <- sqrt(rowSums((pr_node_coords - matrix(centroid, nrow = nrow(pr_node_coords),
                                                   ncol = 2, byrow = TRUE))^2))
  names(dists) <- rownames(pr_node_coords)
  selected_node <- names(dists)[which.min(dists)]
  cat("Selected root principal node:", selected_node, "(distance:", min(dists), ")\n")
  return(selected_node)
}

# ---------------------------------------------------------------------------
# Main workflow wrapped in tryCatch
# ---------------------------------------------------------------------------
tryCatch({
  cat("Reading h5ad file:", h5ad_file, "\n")
  sce <- suppressWarnings(zellkonverter::readH5AD(h5ad_file, reader = "R"))
  cat("Loaded SCE:", ncol(sce), "cells x", nrow(sce), "genes\n")

  # Validate UMAP key exists
  if (!use_rep %in% reducedDimNames(sce)) {
    stop(sprintf("UMAP key '%s' not found in reducedDims. Available: %s",
                 use_rep, paste(reducedDimNames(sce), collapse = ", ")))
  }

  # Build CellDataSet
  expr_data <- tryCatch(
    SingleCellExperiment::counts(sce),
    error = function(e) {
      cat("No 'counts' assay, using 'X' assay\n")
      SummarizedExperiment::assay(sce, "X")
    }
  )

  cell_meta <- as.data.frame(SummarizedExperiment::colData(sce))
  gene_meta <- data.frame(
    gene_short_name = rownames(sce),
    row.names = rownames(sce)
  )

  cds <- monocle3::new_cell_data_set(
    expression_data = expr_data,
    cell_metadata   = cell_meta,
    gene_metadata   = gene_meta
  )
  cat("Created CellDataSet\n")

  # Inject existing UMAP (must be named "UMAP" for monocle3)
  umap_mat <- as.matrix(SingleCellExperiment::reducedDim(sce, use_rep))[, 1:2, drop = FALSE]
  SingleCellExperiment::reducedDims(cds)[["UMAP"]] <- umap_mat
  cat("Injected UMAP from '", use_rep, "'\n")

  # Cluster cells
  # monocle3 needs its own clustering even if we have cluster labels
  # Use louvain to avoid issues with leiden requiring Python igraph
  cat("Clustering cells with louvain...\n")
  cds <- tryCatch({
    monocle3::cluster_cells(cds, reduction_method = "UMAP",
                            cluster_method = "louvain", verbose = FALSE)
  }, error = function(e) {
    cat("WARNING: cluster_cells failed:", conditionMessage(e), "\n")
    cat("Trying with leiden...\n")
    monocle3::cluster_cells(cds, reduction_method = "UMAP",
                            cluster_method = "leiden", verbose = FALSE)
  })
  cat("Clustering done\n")

  # Learn principal graph
  cat("Learning principal graph (this may take a while)...\n")
  cds <- monocle3::learn_graph(cds, use_partition = FALSE, verbose = FALSE,
                                close_loop = FALSE)
  cat("Principal graph learned\n")

  # Auto-select or use explicit root principal node
  if (root_pr_nodes_arg == "auto") {
    root_pr_node <- .auto_select_root(cds, cluster_key, root_cluster, umap_mat)
  } else {
    root_pr_node <- root_pr_nodes_arg
  }

  # Order cells
  cat("Ordering cells with root node:", root_pr_node, "\n")
  cds <- monocle3::order_cells(cds, root_pr_nodes = root_pr_node)
  cat("Ordering done\n")

  # Extract pseudotime
  pt_vec <- monocle3::pseudotime(cds)
  pt_vec[is.infinite(pt_vec)] <- NA_real_

  cluster_vec <- tryCatch(
    as.character(monocle3::clusters(cds)),
    error = function(e) rep(NA_character_, ncol(cds))
  )
  partition_vec <- tryCatch(
    as.character(monocle3::partitions(cds)),
    error = function(e) rep(NA_character_, ncol(cds))
  )

  # Write pseudotime CSV
  pseudotime_out <- data.frame(
    cell_id             = colnames(cds),
    monocle3_pseudotime = as.numeric(pt_vec),
    monocle3_cluster    = cluster_vec,
    monocle3_partition  = partition_vec,
    stringsAsFactors = FALSE
  )
  write.csv(pseudotime_out, file.path(output_dir, "monocle3_pseudotime.csv"),
            row.names = FALSE, quote = FALSE)
  cat("Wrote monocle3_pseudotime.csv:", nrow(pseudotime_out), "cells,",
      sum(!is.na(pseudotime_out$monocle3_pseudotime)), "with pseudotime\n")

  # Write principal graph edges for trajectory plotting
  pr_graph <- monocle3::principal_graph(cds)[["UMAP"]]
  pr_graph_aux <- cds@principal_graph_aux[["UMAP"]]

  if (!is.null(pr_graph_aux) && !is.null(pr_graph_aux$dp_mst)) {
    dp_mst_coords <- t(as.matrix(pr_graph_aux$dp_mst))  # n_nodes x 2
  } else {
    dp_mst_coords <- igraph::layout_with_fr(pr_graph)
    rownames(dp_mst_coords) <- igraph::V(pr_graph)$name
  }

  edge_list <- igraph::as_edgelist(pr_graph, names = FALSE)  # numeric indices
  if (nrow(edge_list) > 0) {
    traj_df <- data.frame(
      x_start = dp_mst_coords[edge_list[, 1], 1],
      y_start = dp_mst_coords[edge_list[, 1], 2],
      x_end   = dp_mst_coords[edge_list[, 2], 1],
      y_end   = dp_mst_coords[edge_list[, 2], 2],
      stringsAsFactors = FALSE
    )
  } else {
    traj_df <- data.frame(
      x_start = numeric(0), y_start = numeric(0),
      x_end = numeric(0), y_end = numeric(0)
    )
  }
  write.csv(traj_df, file.path(output_dir, "monocle3_trajectory.csv"),
            row.names = FALSE, quote = FALSE)
  cat("Wrote monocle3_trajectory.csv:", nrow(traj_df), "edges\n")

  cat("monocle3 pseudotime complete.\n")

}, error = function(e) {
  cat(sprintf("ERROR: %s\n", conditionMessage(e)), file = stderr())
  quit(status = 1)
})
