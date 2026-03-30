# ============================================================================
# MARKER GENE IDENTIFICATION
# ============================================================================
#
# Find genes that define each cluster through differential expression.
#
# Functions:
#   - find_all_cluster_markers(): Find markers for all clusters
#   - find_markers_for_cluster(): Find markers for specific cluster
#   - export_marker_tables(): Save marker tables to CSV
#   - plot_top_markers_heatmap(): Heatmap of top markers
#   - plot_markers_dotplot(): Dot plot of top markers
#   - plot_markers_violin(): Violin plots of top markers
#
# Usage:
#   source("scripts/find_markers.R")
#   all_markers <- find_all_cluster_markers(seurat_obj)

library(ggplot2)
library(ggprism)
library(patchwork)
library(dplyr)

#' Find markers for all clusters
#'
#' @param seurat_obj Seurat object with clusters
#' @param resolution Resolution to use (NULL for active idents)
#' @param only_pos Only return positive markers (default: TRUE)
#' @param min_pct Minimum fraction of cells expressing gene (default: 0.25)
#' @param logfc_threshold Minimum log2 fold change (default: 0.25)
#' @param test_use DE test to use (default: "wilcox")
#' @param verbose Print progress (default: TRUE)
#' @return Data frame with marker genes
#' @export
find_all_cluster_markers <- function(seurat_obj,
                                    resolution = NULL,
                                    only_pos = TRUE,
                                    min_pct = 0.25,
                                    logfc_threshold = 0.25,
                                    test_use = "wilcox",
                                    verbose = TRUE) {

  message("Finding markers for all clusters")

  # Set identity if resolution specified
  if (!is.null(resolution)) {
    col_name <- paste0("RNA_snn_res.", resolution)
    if (col_name %in% colnames(seurat_obj@meta.data)) {
      Idents(seurat_obj) <- col_name
      message("  Using resolution: ", resolution)
    } else {
      stop("Resolution column not found: ", col_name)
    }
  }

  n_clusters <- length(unique(Idents(seurat_obj)))
  message("  Number of clusters: ", n_clusters)
  message("  Test: ", test_use)
  message("  Min pct: ", min_pct)
  message("  Log2FC threshold: ", logfc_threshold)

  # Find all markers
  all_markers <- FindAllMarkers(
    seurat_obj,
    only.pos = only_pos,
    min.pct = min_pct,
    logfc.threshold = logfc_threshold,
    test.use = test_use,
    verbose = verbose
  )

  # Add cluster info
  all_markers <- all_markers %>%
    arrange(cluster, desc(avg_log2FC))

  message("Marker identification complete")
  message("  Total markers found: ", nrow(all_markers))
  message("  Markers per cluster:")
  print(table(all_markers$cluster))

  return(all_markers)
}

#' Find markers for specific cluster
#'
#' @param seurat_obj Seurat object with clusters
#' @param cluster_id Cluster ID to find markers for
#' @param resolution Resolution to use (NULL for active idents)
#' @param only_pos Only return positive markers (default: TRUE)
#' @param min_pct Minimum fraction of cells expressing gene (default: 0.25)
#' @param logfc_threshold Minimum log2 fold change (default: 0.25)
#' @return Data frame with marker genes
#' @export
find_markers_for_cluster <- function(seurat_obj,
                                    cluster_id,
                                    resolution = NULL,
                                    only_pos = TRUE,
                                    min_pct = 0.25,
                                    logfc_threshold = 0.25) {

  message("Finding markers for cluster ", cluster_id)

  # Set identity if resolution specified
  if (!is.null(resolution)) {
    col_name <- paste0("RNA_snn_res.", resolution)
    Idents(seurat_obj) <- col_name
  }

  # Find markers
  markers <- FindMarkers(
    seurat_obj,
    ident.1 = cluster_id,
    only.pos = only_pos,
    min.pct = min_pct,
    logfc.threshold = logfc_threshold
  )

  # Add gene names
  markers$gene <- rownames(markers)
  markers <- markers %>%
    arrange(desc(avg_log2FC))

  message("  Markers found: ", nrow(markers))

  return(markers)
}

#' Export marker tables to CSV
#'
#' @param all_markers Data frame from find_all_cluster_markers()
#' @param output_dir Output directory
#' @param top_n Number of top markers per cluster (default: 50)
#' @export
export_marker_tables <- function(all_markers, output_dir, top_n = 50) {

  message("Exporting marker tables")

  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  # Export all markers
  all_file <- file.path(output_dir, "cluster_markers_all.csv")
  write.csv(all_markers, all_file, row.names = FALSE)
  message("  Saved: ", all_file)

  # Export top N per cluster
  top_markers <- all_markers %>%
    group_by(cluster) %>%
    slice_head(n = top_n)

  top_file <- file.path(output_dir, paste0("cluster_markers_top", top_n, ".csv"))
  write.csv(top_markers, top_file, row.names = FALSE)
  message("  Saved: ", top_file)

  # Export separate file per cluster
  for (clust in unique(all_markers$cluster)) {
    clust_markers <- all_markers %>%
      filter(cluster == clust)

    clust_file <- file.path(output_dir, paste0("cluster_", clust, "_markers.csv"))
    write.csv(clust_markers, clust_file, row.names = FALSE)
  }

  message("  Individual cluster files saved")
}

#' Plot heatmap of top markers
#'
#' @param seurat_obj Seurat object
#' @param all_markers Data frame from find_all_cluster_markers()
#' @param n_top Number of top markers per cluster (default: 10)
#' @param output_dir Output directory for plots
#' @return Heatmap object
#' @export
plot_top_markers_heatmap <- function(seurat_obj,
                                    all_markers,
                                    n_top = 10,
                                    output_dir = NULL) {

  message("Creating marker heatmap")

  # Get top markers per cluster
  top_markers <- all_markers %>%
    group_by(cluster) %>%
    slice_head(n = n_top) %>%
    pull(gene)

  message("  Plotting ", length(top_markers), " markers")

  # Create heatmap
  p <- DoHeatmap(
    seurat_obj,
    features = top_markers,
    size = 3
  ) +
    theme_prism() +
    theme(axis.text.y = element_text(size = 6))

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    svg_file <- file.path(output_dir, "markers_heatmap.svg")
    ggsave(svg_file, plot = p, width = 12, height = 14, dpi = 300)
    message("  Saved: ", svg_file)

    png_file <- file.path(output_dir, "markers_heatmap.png")
    ggsave(png_file, plot = p, width = 12, height = 14, dpi = 300)
    message("  Saved: ", png_file)
  }

  return(p)
}

#' Plot dot plot of top markers
#'
#' @param seurat_obj Seurat object
#' @param all_markers Data frame from find_all_cluster_markers()
#' @param n_top Number of top markers per cluster (default: 5)
#' @param output_dir Output directory for plots
#' @return ggplot object
#' @export
plot_markers_dotplot <- function(seurat_obj,
                                all_markers,
                                n_top = 5,
                                output_dir = NULL) {

  message("Creating marker dot plot")

  # Get top markers per cluster
  top_markers <- all_markers %>%
    group_by(cluster) %>%
    slice_head(n = n_top) %>%
    pull(gene) %>%
    unique()

  message("  Plotting ", length(top_markers), " markers")

  # Create dot plot
  p <- DotPlot(
    seurat_obj,
    features = top_markers
  ) +
    theme_prism() +
    theme(axis.text.x = element_text(angle = 90, hjust = 1, vjust = 0.5)) +
    labs(title = "Top Marker Genes per Cluster")

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    svg_file <- file.path(output_dir, "markers_dotplot.svg")
    ggsave(svg_file, plot = p, width = 12, height = 6, dpi = 300)
    message("  Saved: ", svg_file)

    png_file <- file.path(output_dir, "markers_dotplot.png")
    ggsave(png_file, plot = p, width = 12, height = 6, dpi = 300)
    message("  Saved: ", png_file)
  }

  return(p)
}

#' Plot violin plots of top markers
#'
#' @param seurat_obj Seurat object
#' @param all_markers Data frame from find_all_cluster_markers()
#' @param n_top Number of top markers per cluster (default: 3)
#' @param output_dir Output directory for plots
#' @return Combined ggplot object
#' @export
plot_markers_violin <- function(seurat_obj,
                               all_markers,
                               n_top = 3,
                               output_dir = NULL) {

  message("Creating marker violin plots")

  # Get top markers per cluster
  top_markers <- all_markers %>%
    group_by(cluster) %>%
    slice_head(n = n_top) %>%
    pull(gene) %>%
    unique()

  # Limit to reasonable number
  if (length(top_markers) > 20) {
    message("  Too many markers, limiting to 20")
    top_markers <- head(top_markers, 20)
  }

  message("  Plotting ", length(top_markers), " markers")

  # Create violin plot
  p <- VlnPlot(
    seurat_obj,
    features = top_markers,
    ncol = 4,
    pt.size = 0
  ) &
    theme_prism() &
    theme(
      legend.position = "none",
      axis.title.x = element_blank(),
      axis.text.x = element_text(angle = 45, hjust = 1)
    )

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    # Calculate height based on number of features
    nrow <- ceiling(length(top_markers) / 4)
    height <- nrow * 3

    svg_file <- file.path(output_dir, "markers_violin.svg")
    ggsave(svg_file, plot = p, width = 16, height = height, dpi = 300)
    message("  Saved: ", svg_file)

    png_file <- file.path(output_dir, "markers_violin.png")
    ggsave(png_file, plot = p, width = 16, height = height, dpi = 300)
    message("  Saved: ", png_file)
  }

  return(p)
}

