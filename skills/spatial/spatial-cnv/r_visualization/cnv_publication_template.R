#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: cnv_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
spatial_csv <- file.path(figure_data_dir, "cnv_spatial_points.csv")
umap_csv <- file.path(figure_data_dir, "cnv_umap_points.csv")

input_csv <- NULL
if (file.exists(spatial_csv)) {
  input_csv <- spatial_csv
} else if (file.exists(umap_csv)) {
  input_csv <- umap_csv
} else {
  stop("Required inputs not found: cnv_spatial_points.csv or cnv_umap_points.csv")
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

df <- read.csv(input_csv, stringsAsFactors = FALSE)
custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

if (all(c("x", "y") %in% colnames(df))) {
  p <- ggplot2::ggplot(
    df,
    ggplot2::aes(x = x, y = y, color = cnv_score)
  ) +
    ggplot2::geom_point(size = 1.4, alpha = 0.88) +
    ggplot2::scale_color_gradient2(
      low = "#2166ac",
      mid = "#f7f7f7",
      high = "#b2182b",
      midpoint = stats::median(df$cnv_score, na.rm = TRUE)
    ) +
    ggplot2::coord_equal() +
    ggplot2::scale_y_reverse() +
    ggplot2::theme_bw(base_size = 12) +
    ggplot2::theme(
      panel.grid = ggplot2::element_blank(),
      legend.position = "right"
    ) +
    ggplot2::labs(
      title = "Spatial CNV Publication View",
      subtitle = "R customization layer consuming OmicsClaw figure_data/",
      x = "Spatial X",
      y = "Spatial Y",
      color = "CNV score"
    )
  out_png <- file.path(custom_dir, "cnv_spatial_publication.png")
  ggplot2::ggsave(out_png, plot = p, width = 8.2, height = 6.8, dpi = 300)
  message(sprintf("Saved custom R visualization: %s", out_png))
} else {
  p <- ggplot2::ggplot(
    df,
    ggplot2::aes(x = umap_1, y = umap_2, color = cnv_score)
  ) +
    ggplot2::geom_point(size = 1.2, alpha = 0.85) +
    ggplot2::scale_color_gradient2(
      low = "#2166ac",
      mid = "#f7f7f7",
      high = "#b2182b",
      midpoint = stats::median(df$cnv_score, na.rm = TRUE)
    ) +
    ggplot2::coord_equal() +
    ggplot2::theme_bw(base_size = 12) +
    ggplot2::theme(
      panel.grid = ggplot2::element_blank(),
      legend.position = "right"
    ) +
    ggplot2::labs(
      title = "CNV UMAP Publication View",
      subtitle = "Fallback view when spatial coordinates are not exported",
      x = "UMAP 1",
      y = "UMAP 2",
      color = "CNV score"
    )
  out_png <- file.path(custom_dir, "cnv_umap_publication.png")
  ggplot2::ggsave(out_png, plot = p, width = 8.0, height = 6.4, dpi = 300)
  message(sprintf("Saved custom R visualization: %s", out_png))
}
