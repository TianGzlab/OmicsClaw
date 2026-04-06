#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: raw_processing_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
stage_summary_csv <- file.path(figure_data_dir, "stage_summary.csv")
spatial_points_csv <- file.path(figure_data_dir, "raw_processing_spatial_points.csv")
saturation_csv <- file.path(figure_data_dir, "saturation_curve.csv")

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

if (file.exists(spatial_points_csv)) {
  spatial_df <- read.csv(spatial_points_csv, stringsAsFactors = FALSE)
  if (all(c("x", "y", "total_counts") %in% names(spatial_df))) {
    p <- ggplot2::ggplot(
      spatial_df,
      ggplot2::aes(x = x, y = y, color = total_counts)
    ) +
      ggplot2::geom_point(size = 0.8, alpha = 0.9) +
      ggplot2::coord_equal() +
      ggplot2::scale_y_reverse() +
      ggplot2::scale_color_viridis_c(option = "C") +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(panel.grid = ggplot2::element_blank()) +
      ggplot2::labs(
        title = "Spatial Raw Count Density",
        subtitle = "R customization layer consuming OmicsClaw figure_data/",
        x = "X coordinate",
        y = "Y coordinate",
        color = "Total counts"
      )

    out_path <- file.path(custom_dir, "raw_processing_total_counts_publication.png")
    ggplot2::ggsave(out_path, plot = p, width = 8.2, height = 6.6, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", out_path))
  }
}

if (file.exists(stage_summary_csv)) {
  stage_df <- read.csv(stage_summary_csv, stringsAsFactors = FALSE)
  if (nrow(stage_df) > 0 && all(c("stage_label", "reads") %in% names(stage_df))) {
    stage_df$stage_label <- factor(stage_df$stage_label, levels = stage_df$stage_label)
    p <- ggplot2::ggplot(stage_df, ggplot2::aes(x = stage_label, y = reads / 1e6)) +
      ggplot2::geom_col(fill = "#5b8def", width = 0.75) +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(
        panel.grid = ggplot2::element_blank(),
        axis.text.x = ggplot2::element_text(angle = 25, hjust = 1)
      ) +
      ggplot2::labs(
        title = "st_pipeline Read Attrition",
        x = "Pipeline stage",
        y = "Reads (millions)"
      )

    out_path <- file.path(custom_dir, "raw_processing_stage_attrition_publication.png")
    ggplot2::ggsave(out_path, plot = p, width = 8.8, height = 5.2, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", out_path))
  }
}

if (file.exists(saturation_csv)) {
  sat_df <- read.csv(saturation_csv, stringsAsFactors = FALSE)
  if (nrow(sat_df) > 0 && all(c("reads_sampled", "genes_detected") %in% names(sat_df))) {
    p <- ggplot2::ggplot(sat_df, ggplot2::aes(x = reads_sampled, y = genes_detected)) +
      ggplot2::geom_line(color = "#2d6a4f", linewidth = 0.9) +
      ggplot2::geom_point(color = "#2d6a4f", size = 2.0) +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(panel.grid = ggplot2::element_blank()) +
      ggplot2::labs(
        title = "Sequencing Saturation",
        x = "Reads sampled",
        y = "Genes detected"
      )

    out_path <- file.path(custom_dir, "raw_processing_saturation_publication.png")
    ggplot2::ggsave(out_path, plot = p, width = 7.4, height = 5.2, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", out_path))
  }
}
