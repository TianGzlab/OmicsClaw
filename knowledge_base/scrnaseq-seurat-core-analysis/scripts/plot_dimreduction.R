# ============================================================================
# DIMENSIONALITY REDUCTION PLOTTING
# ============================================================================
#
# Visualization of PCA, UMAP, and clustering results.
#
# Functions:
#   - plot_umap_clusters(): UMAP colored by clusters
#   - plot_clustering_comparison(): Compare multiple resolutions
#   - plot_feature_umap(): Feature expression on UMAP
#   - plot_pca_clusters(): PCA colored by clusters
#
# Usage:
#   source("scripts/plot_dimreduction.R")
#   plot_umap_clusters(seurat_obj, output_dir = "results/umap")

library(ggplot2)
library(ggprism)
library(patchwork)

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
    library(svglite)
}

# Internal helper: Save plot in both PNG and SVG formats with graceful fallback
.save_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
    # Always save PNG
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")

    # Always try SVG - try ggsave first, fall back to svg() device
    svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
    tryCatch({
        ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        # If ggsave fails, try base R svg() device directly
        tryCatch({
            svg(svg_path, width = width, height = height)
            print(plot)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e2) {
            cat("   (SVG export failed - PNG available)\n")
        })
    })
}

#' Plot UMAP colored by clusters
#'
#' @param seurat_obj Seurat object with UMAP and clusters
#' @param group_by Metadata column to color by (default: active idents)
#' @param label Label clusters on plot (default: TRUE)
#' @param label_size Size of labels (default: 6)
#' @param output_dir Output directory for plots
#' @param width Plot width (default: 8)
#' @param height Plot height (default: 6)
#' @return ggplot object
#' @export
plot_umap_clusters <- function(seurat_obj,
                               group_by = NULL,
                               label = TRUE,
                               label_size = 6,
                               output_dir = NULL,
                               width = 8,
                               height = 6) {

  message("Creating UMAP cluster plot")

  # Create UMAP plot
  p <- DimPlot(
    seurat_obj,
    reduction = "umap",
    group.by = group_by,
    label = label,
    label.size = label_size,
    pt.size = 0.5
  ) +
    theme_prism() +
    theme(legend.position = "right") +
    labs(title = "UMAP of Cell Clusters")

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
    .save_plot(p, file.path(output_dir, "umap_clusters.png"), width, height, dpi = 300)
  }

  return(p)
}

#' Compare clustering at multiple resolutions
#'
#' @param seurat_obj Seurat object with multiple resolution columns
#' @param resolutions Resolutions to compare
#' @param output_dir Output directory for plots
#' @param width Plot width (default: 16)
#' @param height Plot height (default: 12)
#' @return Combined ggplot object
#' @export
plot_clustering_comparison <- function(seurat_obj,
                                      resolutions = c(0.4, 0.6, 0.8, 1.0),
                                      output_dir = NULL,
                                      width = 16,
                                      height = 12) {

  message("Comparing clustering resolutions")

  plots <- list()

  for (res in resolutions) {
    col_name <- paste0("RNA_snn_res.", res)

    if (!col_name %in% colnames(seurat_obj@meta.data)) {
      warning("Resolution ", res, " not found. Skipping.")
      next
    }

    p <- DimPlot(
      seurat_obj,
      reduction = "umap",
      group.by = col_name,
      label = TRUE,
      pt.size = 0.5
    ) +
      theme_prism() +
      labs(title = paste0("Resolution ", res)) +
      theme(legend.position = "none")

    plots[[as.character(res)]] <- p
  }

  # Combine plots
  combined <- wrap_plots(plots, ncol = 2)

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
    .save_plot(combined, file.path(output_dir, "clustering_comparison.png"), width, height, dpi = 300)
  }

  return(combined)
}

#' Plot feature expression on UMAP
#'
#' @param seurat_obj Seurat object with UMAP
#' @param features Vector of features to plot (genes or metadata columns)
#' @param ncol Number of columns in plot layout (default: 2)
#' @param output_dir Output directory for plots
#' @param width Plot width (default: 12)
#' @param height Plot height (default: calculated from features)
#' @return ggplot object
#' @export
plot_feature_umap <- function(seurat_obj,
                              features,
                              ncol = 2,
                              output_dir = NULL,
                              width = 12,
                              height = NULL) {

  message("Creating feature plots for: ", paste(features, collapse = ", "))

  # Calculate height if not specified
  if (is.null(height)) {
    nrow <- ceiling(length(features) / ncol)
    height <- nrow * 4
  }

  # Create feature plot
  p <- FeaturePlot(
    seurat_obj,
    features = features,
    ncol = ncol,
    pt.size = 0.5,
    reduction = "umap"
  ) &
    theme_prism() &
    scale_color_viridis_c()

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    # Create filename from features
    filename <- paste0("feature_plot_", paste(gsub("[^[:alnum:]]", "", features[1:min(3, length(features))]), collapse = "_"))

    .save_plot(p, file.path(output_dir, paste0(filename, ".png")), width, height, dpi = 300)
  }

  return(p)
}

#' Plot PCA colored by clusters
#'
#' @param seurat_obj Seurat object with PCA and clusters
#' @param dims PCs to plot (default: c(1, 2))
#' @param group_by Metadata column to color by (default: active idents)
#' @param output_dir Output directory for plots
#' @param width Plot width (default: 8)
#' @param height Plot height (default: 6)
#' @return ggplot object
#' @export
plot_pca_clusters <- function(seurat_obj,
                              dims = c(1, 2),
                              group_by = NULL,
                              output_dir = NULL,
                              width = 8,
                              height = 6) {

  message("Creating PCA plot")

  # Create PCA plot
  p <- DimPlot(
    seurat_obj,
    reduction = "pca",
    dims = dims,
    group.by = group_by,
    pt.size = 0.5
  ) +
    theme_prism() +
    theme(legend.position = "right") +
    labs(title = paste0("PCA: PC", dims[1], " vs PC", dims[2]))

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
    .save_plot(p, file.path(output_dir, paste0("pca_PC", dims[1], "_vs_PC", dims[2], ".png")), width, height, dpi = 300)
  }

  return(p)
}

#' Create split UMAP by condition
#'
#' @param seurat_obj Seurat object with UMAP
#' @param split_by Metadata column to split by
#' @param ncol Number of columns (default: auto)
#' @param output_dir Output directory for plots
#' @param width Plot width (default: 12)
#' @param height Plot height (default: 6)
#' @return ggplot object
#' @export
plot_split_umap <- function(seurat_obj,
                            split_by,
                            ncol = NULL,
                            output_dir = NULL,
                            width = 12,
                            height = 6) {

  message("Creating split UMAP by: ", split_by)

  # Create split UMAP
  p <- DimPlot(
    seurat_obj,
    reduction = "umap",
    split.by = split_by,
    ncol = ncol,
    pt.size = 0.5
  ) +
    theme_prism()

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
    .save_plot(p, file.path(output_dir, paste0("umap_split_by_", split_by, ".png")), width, height, dpi = 300)
  }

  return(p)
}

