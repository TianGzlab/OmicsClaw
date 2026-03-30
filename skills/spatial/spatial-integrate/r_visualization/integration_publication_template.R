#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: integration_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
after_csv <- file.path(figure_data_dir, "umap_after_points.csv")

if (!file.exists(after_csv)) {
  stop(sprintf("Required input not found: %s", after_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

df <- read.csv(after_csv, stringsAsFactors = FALSE)
custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

p <- ggplot2::ggplot(
  df,
  ggplot2::aes(x = umap_1, y = umap_2, color = batch_label)
) +
  ggplot2::geom_point(size = 1.3, alpha = 0.85) +
  ggplot2::coord_equal() +
  ggplot2::theme_bw(base_size = 12) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    legend.title = ggplot2::element_blank(),
    legend.position = "right"
  ) +
  ggplot2::labs(
    title = "Integrated UMAP Publication View",
    subtitle = "R customization layer consuming OmicsClaw figure_data/"
  )

out_png <- file.path(custom_dir, "integration_umap_publication.png")
ggplot2::ggsave(out_png, plot = p, width = 8.5, height = 6.8, dpi = 300)

message(sprintf("Saved custom R visualization: %s", out_png))
