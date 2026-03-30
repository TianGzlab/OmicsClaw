#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: deconv_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
spatial_points_csv <- file.path(figure_data_dir, "deconv_spatial_points.csv")
mean_props_csv <- file.path(figure_data_dir, "mean_proportions.csv")
run_summary_csv <- file.path(figure_data_dir, "deconv_run_summary.csv")

if (!file.exists(spatial_points_csv)) {
  stop(sprintf("Required input not found: %s", spatial_points_csv))
}
if (!file.exists(mean_props_csv)) {
  stop(sprintf("Required input not found: %s", mean_props_csv))
}
if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

spatial_df <- read.csv(spatial_points_csv, stringsAsFactors = FALSE)
mean_df <- read.csv(mean_props_csv, stringsAsFactors = FALSE)

if (nrow(spatial_df) < 1) {
  stop("No rows available in deconv_spatial_points.csv")
}
if (nrow(mean_df) < 1) {
  stop("No rows available in mean_proportions.csv")
}

dominant_col <- NULL
dominant_prop_col <- NULL
assignment_margin_col <- NULL
if (file.exists(run_summary_csv)) {
  run_summary <- read.csv(run_summary_csv, stringsAsFactors = FALSE)
  if (all(c("metric", "value") %in% names(run_summary))) {
    metric_lookup <- setNames(run_summary$value, run_summary$metric)
    dominant_col <- metric_lookup[["dominant_label_column"]]
    dominant_prop_col <- metric_lookup[["dominant_proportion_column"]]
    assignment_margin_col <- metric_lookup[["assignment_margin_column"]]
  }
}

if (is.null(dominant_col) || !nzchar(dominant_col) || !dominant_col %in% names(spatial_df)) {
  dominant_candidates <- grep("dominant_cell_type$", names(spatial_df), value = TRUE)
  if (length(dominant_candidates) < 1) {
    stop("Could not resolve the dominant cell-type column from exported figure_data.")
  }
  dominant_col <- dominant_candidates[[1]]
}

if (is.null(dominant_prop_col) || !nzchar(dominant_prop_col) || !dominant_prop_col %in% names(spatial_df)) {
  dominant_prop_candidates <- grep("dominant_proportion$", names(spatial_df), value = TRUE)
  dominant_prop_col <- if (length(dominant_prop_candidates) > 0) dominant_prop_candidates[[1]] else NULL
}

if (is.null(assignment_margin_col) || !nzchar(assignment_margin_col) || !assignment_margin_col %in% names(spatial_df)) {
  margin_candidates <- grep("assignment_margin$", names(spatial_df), value = TRUE)
  assignment_margin_col <- if (length(margin_candidates) > 0) margin_candidates[[1]] else NULL
}

custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

point_layer <- if (!is.null(dominant_prop_col) && dominant_prop_col %in% names(spatial_df)) {
  ggplot2::geom_point(
    ggplot2::aes(alpha = .data[[dominant_prop_col]]),
    size = 2.4
  )
} else {
  ggplot2::geom_point(size = 2.4, alpha = 0.85)
}

dominant_plot <- ggplot2::ggplot(
  spatial_df,
  ggplot2::aes(
    x = .data[["x"]],
    y = .data[["y"]],
    color = .data[[dominant_col]]
  )
) +
  point_layer +
  ggplot2::scale_y_reverse() +
  ggplot2::coord_equal() +
  ggplot2::theme_bw(base_size = 12) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    legend.title = ggplot2::element_blank()
  ) +
  ggplot2::labs(
    title = "Spatial Deconvolution Publication View",
    subtitle = "Dominant cell type map from OmicsClaw figure_data/",
    x = "Spatial X",
    y = "Spatial Y"
  )

dominant_png <- file.path(custom_dir, "deconv_dominant_publication.png")
ggplot2::ggsave(dominant_png, plot = dominant_plot, width = 8.8, height = 7.2, dpi = 300)
message(sprintf("Saved custom R visualization: %s", dominant_png))

mean_df <- mean_df[order(mean_df$mean_proportion, decreasing = FALSE), , drop = FALSE]
mean_df$cell_type <- factor(mean_df$cell_type, levels = mean_df$cell_type)

mean_plot <- ggplot2::ggplot(
  mean_df,
  ggplot2::aes(x = cell_type, y = mean_proportion)
) +
  ggplot2::geom_col(fill = "#d95f0e", width = 0.72) +
  ggplot2::coord_flip() +
  ggplot2::theme_bw(base_size = 12) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank()
  ) +
  ggplot2::labs(
    title = "Mean Cell-Type Proportions",
    subtitle = "Publication-style summary built from OmicsClaw figure_data/",
    x = NULL,
    y = "Mean proportion"
  )

mean_png <- file.path(custom_dir, "deconv_mean_proportions_publication.png")
ggplot2::ggsave(mean_png, plot = mean_plot, width = 7.8, height = 5.6, dpi = 300)
message(sprintf("Saved custom R visualization: %s", mean_png))

if (!is.null(assignment_margin_col) && assignment_margin_col %in% names(spatial_df)) {
  margin_plot <- ggplot2::ggplot(
    spatial_df,
    ggplot2::aes(x = .data[[assignment_margin_col]])
  ) +
    ggplot2::geom_histogram(bins = 24, fill = "#756bb1", color = "white") +
    ggplot2::theme_bw(base_size = 12) +
    ggplot2::theme(
      panel.grid = ggplot2::element_blank()
    ) +
    ggplot2::labs(
      title = "Assignment Margin Distribution",
      subtitle = "Lower values indicate more ambiguous dominant cell-type assignments",
      x = "Top1 - Top2 proportion",
      y = "Number of spots"
    )

  margin_png <- file.path(custom_dir, "deconv_assignment_margin_publication.png")
  ggplot2::ggsave(margin_png, plot = margin_plot, width = 7.6, height = 5.2, dpi = 300)
  message(sprintf("Saved custom R visualization: %s", margin_png))
}
