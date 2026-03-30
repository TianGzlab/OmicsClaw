#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: velocity_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
top_genes_csv <- file.path(figure_data_dir, "velocity_top_genes.csv")
spatial_csv <- file.path(figure_data_dir, "velocity_spatial_points.csv")

if (!file.exists(top_genes_csv)) {
  stop(sprintf("Required input not found: %s", top_genes_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

top_genes_df <- read.csv(top_genes_csv, stringsAsFactors = FALSE)
custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

if (nrow(top_genes_df) > 0) {
  plot_df <- utils::head(top_genes_df, 12)
  score_col <- NA_character_
  for (candidate in c("fit_likelihood", "velocity_r2", "velocity_qreg_ratio")) {
    if (candidate %in% colnames(plot_df) && any(!is.na(plot_df[[candidate]]))) {
      score_col <- candidate
      break
    }
  }
  if (is.na(score_col)) {
    plot_df$plot_value <- seq_len(nrow(plot_df))
    x_label <- "Rank surrogate"
  } else {
    plot_df$plot_value <- plot_df[[score_col]]
    x_label <- score_col
  }

  plot_df$gene <- factor(plot_df$gene, levels = rev(plot_df$gene))
  fill_values <- if ("velocity_genes" %in% colnames(plot_df)) {
    ifelse(as.logical(plot_df$velocity_genes), "velocity_gene", "other")
  } else {
    rep("velocity_gene", nrow(plot_df))
  }
  plot_df$fill_group <- factor(fill_values, levels = c("other", "velocity_gene"))

  p_genes <- ggplot2::ggplot(
    plot_df,
    ggplot2::aes(x = plot_value, y = gene, fill = fill_group)
  ) +
    ggplot2::geom_col(alpha = 0.94) +
    ggplot2::scale_fill_manual(values = c(other = "#9ecae1", velocity_gene = "#238b45")) +
    ggplot2::theme_bw(base_size = 12) +
    ggplot2::theme(
      panel.grid.major.y = ggplot2::element_blank(),
      panel.grid.minor = ggplot2::element_blank(),
      legend.position = "none"
    ) +
    ggplot2::labs(
      title = "Top Velocity Genes",
      subtitle = "R customization layer consuming OmicsClaw figure_data/",
      x = x_label,
      y = "Gene"
    )

  out_genes <- file.path(custom_dir, "velocity_top_genes_publication.png")
  ggplot2::ggsave(out_genes, plot = p_genes, width = 8.8, height = 6.4, dpi = 300)
  message(sprintf("Saved custom R visualization: %s", out_genes))
}

if (file.exists(spatial_csv)) {
  spatial_df <- read.csv(spatial_csv, stringsAsFactors = FALSE)
  score_col <- NA_character_
  for (candidate in c("velocity_confidence", "velocity_speed", "velocity_pseudotime", "latent_time")) {
    if (candidate %in% colnames(spatial_df) && any(!is.na(spatial_df[[candidate]]))) {
      score_col <- candidate
      break
    }
  }

  if (!is.na(score_col)) {
    p_spatial <- ggplot2::ggplot(
      spatial_df,
      ggplot2::aes(x = x, y = y, color = .data[[score_col]])
    ) +
      ggplot2::geom_point(size = 1.4, alpha = 0.9) +
      ggplot2::coord_equal() +
      ggplot2::scale_y_reverse() +
      ggplot2::scale_color_gradient(
        low = "#f7fbff",
        high = "#08519c"
      ) +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(
        panel.grid = ggplot2::element_blank(),
        legend.position = "right"
      ) +
      ggplot2::labs(
        title = "Spatial Velocity Metric Map",
        subtitle = sprintf("Column: %s", score_col),
        x = "Spatial X",
        y = "Spatial Y",
        color = score_col
      )

    out_spatial <- file.path(custom_dir, "velocity_spatial_metric_publication.png")
    ggplot2::ggsave(out_spatial, plot = p_spatial, width = 8.2, height = 6.6, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", out_spatial))
  }
}
