#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: communication_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
spatial_csv <- file.path(figure_data_dir, "communication_spatial_points.csv")

if (!file.exists(spatial_csv)) {
  stop(sprintf("Required input not found: %s", spatial_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

df <- read.csv(spatial_csv, stringsAsFactors = FALSE)
custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

hub_col <- "communication_hub_score"
if (!hub_col %in% colnames(df)) {
  stop(sprintf("Column '%s' not found in %s", hub_col, spatial_csv))
}

p <- ggplot2::ggplot(
  df,
  ggplot2::aes(x = x, y = y, color = .data[[hub_col]])
) +
  ggplot2::geom_point(size = 1.5, alpha = 0.88) +
  ggplot2::scale_color_gradient(
    low = "#fdd49e",
    high = "#b30000"
  ) +
  ggplot2::coord_equal() +
  ggplot2::scale_y_reverse() +
  ggplot2::theme_bw(base_size = 12) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    legend.position = "right"
  ) +
  ggplot2::labs(
    title = "Spatial Communication Hub Score",
    subtitle = "R customization layer consuming OmicsClaw figure_data/",
    x = "Spatial X",
    y = "Spatial Y",
    color = "Hub score"
  )

out_png <- file.path(custom_dir, "communication_hub_spatial_publication.png")
ggplot2::ggsave(out_png, plot = p, width = 8.4, height = 6.8, dpi = 300)

message(sprintf("Saved custom R visualization: %s", out_png))
