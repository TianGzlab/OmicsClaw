#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: register_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
points_csv <- file.path(figure_data_dir, "registration_points.csv")
shift_summary_csv <- file.path(figure_data_dir, "registration_shift_by_slice.csv")
disparity_csv <- file.path(figure_data_dir, "registration_disparities.csv")

if (!file.exists(points_csv)) {
  stop(sprintf("Required input not found: %s", points_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

points_df <- read.csv(points_csv, stringsAsFactors = FALSE)
required_cols <- c(
  "slice",
  "original_x",
  "original_y",
  "aligned_x",
  "aligned_y"
)
missing_cols <- setdiff(required_cols, names(points_df))
if (length(missing_cols) > 0) {
  stop(sprintf(
    "Missing required columns in registration_points.csv: %s",
    paste(missing_cols, collapse = ", ")
  ))
}

before_df <- data.frame(
  slice = points_df$slice,
  basis = "Before",
  x = points_df$original_x,
  y = points_df$original_y,
  stringsAsFactors = FALSE
)
after_df <- data.frame(
  slice = points_df$slice,
  basis = "After",
  x = points_df$aligned_x,
  y = points_df$aligned_y,
  stringsAsFactors = FALSE
)
plot_df <- rbind(before_df, after_df)
plot_df$basis <- factor(plot_df$basis, levels = c("Before", "After"))
plot_df$slice <- factor(plot_df$slice)

registration_plot <- ggplot2::ggplot(
  plot_df,
  ggplot2::aes(x = x, y = y, color = slice)
) +
  ggplot2::geom_point(size = 0.7, alpha = 0.85) +
  ggplot2::coord_equal() +
  ggplot2::facet_wrap(~basis, scales = "free") +
  ggplot2::theme_bw(base_size = 12) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    legend.title = ggplot2::element_blank()
  ) +
  ggplot2::labs(
    title = "Spatial Registration Publication View",
    subtitle = "Before / after coordinate frames from OmicsClaw figure_data/",
    x = "X",
    y = "Y"
  )

registration_png <- file.path(custom_dir, "registration_before_after_publication.png")
ggplot2::ggsave(registration_png, plot = registration_plot, width = 10.4, height = 5.6, dpi = 300)
message(sprintf("Saved custom R visualization: %s", registration_png))

if (file.exists(shift_summary_csv)) {
  shift_df <- read.csv(shift_summary_csv, stringsAsFactors = FALSE)
  if (nrow(shift_df) > 0 && all(c("slice", "mean_shift", "max_shift") %in% names(shift_df))) {
    shift_df$slice <- factor(
      shift_df$slice,
      levels = shift_df$slice[order(shift_df$mean_shift)]
    )
    shift_plot <- ggplot2::ggplot(
      shift_df,
      ggplot2::aes(x = slice, y = mean_shift)
    ) +
      ggplot2::geom_col(fill = "#3182bd", width = 0.75) +
      ggplot2::geom_point(
        ggplot2::aes(y = max_shift),
        color = "#cb181d",
        size = 2.4
      ) +
      ggplot2::coord_flip() +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(panel.grid = ggplot2::element_blank()) +
      ggplot2::labs(
        title = "Per-Slice Shift Summary",
        subtitle = "Bars show mean shift, red points show max shift",
        x = "Slice",
        y = "Coordinate displacement"
      )

    shift_png <- file.path(custom_dir, "registration_shift_summary_publication.png")
    ggplot2::ggsave(shift_png, plot = shift_plot, width = 8.0, height = 5.6, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", shift_png))
  }
}

if (file.exists(disparity_csv)) {
  disparity_df <- read.csv(disparity_csv, stringsAsFactors = FALSE)
  if (nrow(disparity_df) > 0 && all(c("slice", "disparity") %in% names(disparity_df))) {
    disparity_df$slice <- factor(
      disparity_df$slice,
      levels = disparity_df$slice[order(disparity_df$disparity)]
    )
    disparity_plot <- ggplot2::ggplot(
      disparity_df,
      ggplot2::aes(x = slice, y = disparity)
    ) +
      ggplot2::geom_col(fill = "#756bb1", width = 0.75) +
      ggplot2::coord_flip() +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(panel.grid = ggplot2::element_blank()) +
      ggplot2::labs(
        title = "Registration Disparity",
        subtitle = "Method-reported disparity for non-reference slices",
        x = "Slice",
        y = "Disparity"
      )

    disparity_png <- file.path(custom_dir, "registration_disparity_publication.png")
    ggplot2::ggsave(disparity_png, plot = disparity_plot, width = 7.6, height = 5.2, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", disparity_png))
  }
}
