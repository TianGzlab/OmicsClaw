#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: trajectory_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
umap_csv <- file.path(figure_data_dir, "trajectory_umap_points.csv")
spatial_csv <- file.path(figure_data_dir, "trajectory_spatial_points.csv")

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

point_csv <- NULL
basis <- NULL
if (file.exists(umap_csv)) {
  point_csv <- umap_csv
  basis <- "umap"
} else if (file.exists(spatial_csv)) {
  point_csv <- spatial_csv
  basis <- "spatial"
} else {
  stop("Neither trajectory_umap_points.csv nor trajectory_spatial_points.csv was found.")
}

df <- read.csv(point_csv, stringsAsFactors = FALSE)
custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

pseudotime_candidates <- grep("pseudotime", colnames(df), value = TRUE)
if (length(pseudotime_candidates) == 0) {
  stop(sprintf("No pseudotime column found in %s", point_csv))
}
pseudotime_col <- pseudotime_candidates[[1]]

if (basis == "umap") {
  x_col <- "umap_1"
  y_col <- "umap_2"
  x_label <- "UMAP 1"
  y_label <- "UMAP 2"
} else {
  x_col <- "x"
  y_col <- "y"
  x_label <- "Spatial X"
  y_label <- "Spatial Y"
}

p <- ggplot2::ggplot(
  df,
  ggplot2::aes(x = .data[[x_col]], y = .data[[y_col]], color = .data[[pseudotime_col]])
) +
  ggplot2::geom_point(size = 1.5, alpha = 0.88) +
  ggplot2::scale_color_gradient(
    low = "#f7fcf0",
    high = "#00441b"
  ) +
  ggplot2::theme_bw(base_size = 12) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    legend.position = "right"
  ) +
  ggplot2::labs(
    title = "Trajectory Pseudotime",
    subtitle = sprintf("R customization layer using %s", basename(point_csv)),
    x = x_label,
    y = y_label,
    color = pseudotime_col
  )

if (basis == "spatial") {
  p <- p + ggplot2::coord_equal() + ggplot2::scale_y_reverse()
}

out_pseudotime <- file.path(custom_dir, "trajectory_pseudotime_publication.png")
ggplot2::ggsave(out_pseudotime, plot = p, width = 8.4, height = 6.8, dpi = 300)
message(sprintf("Saved custom R visualization: %s", out_pseudotime))

if ("traj_fate_max_prob" %in% colnames(df)) {
  p_fate <- ggplot2::ggplot(
    df,
    ggplot2::aes(x = .data[[x_col]], y = .data[[y_col]], color = .data[["traj_fate_max_prob"]])
  ) +
    ggplot2::geom_point(size = 1.5, alpha = 0.88) +
    ggplot2::scale_color_gradient(
      low = "#fee8c8",
      high = "#b30000"
    ) +
    ggplot2::theme_bw(base_size = 12) +
    ggplot2::theme(
      panel.grid = ggplot2::element_blank(),
      legend.position = "right"
    ) +
    ggplot2::labs(
      title = "Trajectory Fate Confidence",
      subtitle = "Most likely fate / branch probability",
      x = x_label,
      y = y_label,
      color = "traj_fate_max_prob"
    )

  if (basis == "spatial") {
    p_fate <- p_fate + ggplot2::coord_equal() + ggplot2::scale_y_reverse()
  }

  out_fate <- file.path(custom_dir, "trajectory_fate_confidence_publication.png")
  ggplot2::ggsave(out_fate, plot = p_fate, width = 8.4, height = 6.8, dpi = 300)
  message(sprintf("Saved custom R visualization: %s", out_fate))
}
