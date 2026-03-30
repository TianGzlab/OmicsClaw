# ============================================================================
# QC VISUALIZATION
# ============================================================================
#
# This script generates QC plots to guide filtering decisions.
#
# Functions:
#   - plot_qc_violin(): Violin plots of QC metrics
#   - plot_qc_scatter(): Scatter plots showing relationships
#   - plot_qc_histogram(): Histograms of QC distributions
#
# Usage:
#   source("scripts/plot_qc.R")
#   plot_qc_violin(seurat_obj, output_dir = "results/qc")

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

#' Create violin plots for QC metrics
#'
#' @param seurat_obj Seurat object with QC metrics
#' @param features QC features to plot (default: standard QC metrics)
#' @param output_dir Output directory for plots
#' @param width Plot width in inches (default: 12)
#' @param height Plot height in inches (default: 4)
#' @return ggplot object
#' @export
plot_qc_violin <- function(seurat_obj,
                           features = c("nFeature_RNA", "nCount_RNA", "percent.mt"),
                           output_dir = NULL,
                           width = 12,
                           height = 4) {

  message("Creating QC violin plots")

  # Create violin plot
  p <- VlnPlot(
    seurat_obj,
    features = features,
    ncol = length(features),
    pt.size = 0.1
  ) &
    theme_prism() &
    theme(
      legend.position = "none",
      axis.title.x = element_blank()
    )

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
    .save_plot(p, file.path(output_dir, "qc_violin_plot.png"), width, height, dpi = 300)
  }

  return(p)
}

#' Create scatter plots for QC metrics
#'
#' Shows relationships between QC metrics to identify outliers
#'
#' @param seurat_obj Seurat object with QC metrics
#' @param output_dir Output directory for plots
#' @param width Plot width in inches (default: 12)
#' @param height Plot height in inches (default: 8)
#' @return Combined ggplot object
#' @export
plot_qc_scatter <- function(seurat_obj,
                            output_dir = NULL,
                            width = 12,
                            height = 8) {

  message("Creating QC scatter plots")

  # Get metadata
  metadata <- seurat_obj@meta.data

  # nCount vs nFeature (should be correlated)
  p1 <- ggplot(metadata, aes(x = nCount_RNA, y = nFeature_RNA, color = percent.mt)) +
    geom_point(size = 0.5, alpha = 0.5) +
    scale_color_viridis_c() +
    labs(
      x = "UMI Counts (nCount_RNA)",
      y = "Genes Detected (nFeature_RNA)",
      color = "% MT"
    ) +
    theme_prism() +
    theme(legend.position = "right")

  # nFeature vs percent.mt (low quality cells have high mt%)
  p2 <- ggplot(metadata, aes(x = nFeature_RNA, y = percent.mt, color = nCount_RNA)) +
    geom_point(size = 0.5, alpha = 0.5) +
    scale_color_viridis_c() +
    labs(
      x = "Genes Detected (nFeature_RNA)",
      y = "% Mitochondrial",
      color = "UMI\nCounts"
    ) +
    theme_prism() +
    theme(legend.position = "right")

  # nCount vs percent.mt
  p3 <- ggplot(metadata, aes(x = nCount_RNA, y = percent.mt, color = nFeature_RNA)) +
    geom_point(size = 0.5, alpha = 0.5) +
    scale_color_viridis_c() +
    labs(
      x = "UMI Counts (nCount_RNA)",
      y = "% Mitochondrial",
      color = "Genes"
    ) +
    theme_prism() +
    theme(legend.position = "right")

  # Complexity plot (if available)
  if ("log10GenesPerUMI" %in% colnames(metadata)) {
    p4 <- ggplot(metadata, aes(x = log10GenesPerUMI, y = percent.mt, color = nCount_RNA)) +
      geom_point(size = 0.5, alpha = 0.5) +
      scale_color_viridis_c() +
      labs(
        x = "Complexity (log10 Genes/UMI)",
        y = "% Mitochondrial",
        color = "UMI\nCounts"
      ) +
      theme_prism() +
      theme(legend.position = "right")

    combined <- (p1 | p2) / (p3 | p4)
  } else {
    combined <- (p1 | p2) / p3
  }

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
    .save_plot(combined, file.path(output_dir, "qc_scatter_plots.png"), width, height, dpi = 300)
  }

  return(combined)
}

#' Create histograms for QC metrics
#'
#' @param seurat_obj Seurat object with QC metrics
#' @param output_dir Output directory for plots
#' @param bins Number of bins for histograms (default: 50)
#' @param width Plot width in inches (default: 12)
#' @param height Plot height in inches (default: 4)
#' @return Combined ggplot object
#' @export
plot_qc_histogram <- function(seurat_obj,
                              output_dir = NULL,
                              bins = 50,
                              width = 12,
                              height = 4) {

  message("Creating QC histograms")

  # Get metadata
  metadata <- seurat_obj@meta.data

  # nFeature histogram
  p1 <- ggplot(metadata, aes(x = nFeature_RNA)) +
    geom_histogram(bins = bins, fill = "#4A90E2", color = "black", alpha = 0.7) +
    labs(
      x = "Genes Detected (nFeature_RNA)",
      y = "Number of Cells"
    ) +
    theme_prism()

  # nCount histogram
  p2 <- ggplot(metadata, aes(x = nCount_RNA)) +
    geom_histogram(bins = bins, fill = "#50C878", color = "black", alpha = 0.7) +
    labs(
      x = "UMI Counts (nCount_RNA)",
      y = "Number of Cells"
    ) +
    theme_prism()

  # percent.mt histogram
  p3 <- ggplot(metadata, aes(x = percent.mt)) +
    geom_histogram(bins = bins, fill = "#E24A4A", color = "black", alpha = 0.7) +
    labs(
      x = "% Mitochondrial",
      y = "Number of Cells"
    ) +
    theme_prism()

  combined <- p1 | p2 | p3

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
    .save_plot(combined, file.path(output_dir, "qc_histograms.png"), width, height, dpi = 300)
  }

  return(combined)
}

#' Create comprehensive QC report
#'
#' Generates all QC plots in a single function call
#'
#' @param seurat_obj Seurat object with QC metrics
#' @param output_dir Output directory for plots
#' @export
generate_qc_report <- function(seurat_obj, output_dir = "qc_report") {

  message("Generating comprehensive QC report")

  dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

  # Generate all plots
  plot_qc_violin(seurat_obj, output_dir = output_dir)
  plot_qc_scatter(seurat_obj, output_dir = output_dir)
  plot_qc_histogram(seurat_obj, output_dir = output_dir)

  message("QC report complete. Files saved in: ", output_dir)
}

