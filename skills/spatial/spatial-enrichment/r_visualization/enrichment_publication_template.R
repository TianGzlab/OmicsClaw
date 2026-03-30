#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: enrichment_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
top_terms_csv <- file.path(figure_data_dir, "top_enriched_terms.csv")
spatial_csv <- file.path(figure_data_dir, "enrichment_spatial_points.csv")

if (!file.exists(top_terms_csv)) {
  stop(sprintf("Required input not found: %s", top_terms_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

top_df <- read.csv(top_terms_csv, stringsAsFactors = FALSE)
custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

if (nrow(top_df) > 0) {
  plot_df <- utils::head(top_df, 12)
  if ("pvalue_adj" %in% colnames(plot_df) && any(!is.na(plot_df$pvalue_adj))) {
    plot_df$plot_value <- -log10(pmax(plot_df$pvalue_adj, 1e-300))
    x_label <- "-log10(adj. p-value)"
  } else if ("score" %in% colnames(plot_df)) {
    plot_df$plot_value <- plot_df$score
    x_label <- "Enrichment score"
  } else {
    plot_df$plot_value <- seq_len(nrow(plot_df))
    x_label <- "Rank surrogate"
  }

  plot_df$label <- paste(plot_df$group, plot_df$term, sep = " | ")
  plot_df$label <- factor(plot_df$label, levels = rev(plot_df$label))

  p_terms <- ggplot2::ggplot(
    plot_df,
    ggplot2::aes(x = plot_value, y = label)
  ) +
    ggplot2::geom_col(fill = "#2b8cbe", alpha = 0.92) +
    ggplot2::theme_bw(base_size = 12) +
    ggplot2::theme(
      panel.grid.major.y = ggplot2::element_blank(),
      panel.grid.minor = ggplot2::element_blank()
    ) +
    ggplot2::labs(
      title = "Top Enriched Terms",
      subtitle = "R customization layer consuming OmicsClaw figure_data/",
      x = x_label,
      y = "Group | Term"
    )

  out_terms <- file.path(custom_dir, "enrichment_top_terms_publication.png")
  ggplot2::ggsave(out_terms, plot = p_terms, width = 9.0, height = 6.8, dpi = 300)
  message(sprintf("Saved custom R visualization: %s", out_terms))
}

if (file.exists(spatial_csv)) {
  spatial_df <- read.csv(spatial_csv, stringsAsFactors = FALSE)
  score_cols <- grep("^ssgsea_", colnames(spatial_df), value = TRUE)
  if (length(score_cols) > 0) {
    score_col <- score_cols[[1]]
    p_spatial <- ggplot2::ggplot(
      spatial_df,
      ggplot2::aes(x = x, y = y, color = .data[[score_col]])
    ) +
      ggplot2::geom_point(size = 1.3, alpha = 0.9) +
      ggplot2::coord_equal() +
      ggplot2::scale_y_reverse() +
      ggplot2::scale_color_gradient2(
        low = "#2166ac",
        mid = "#f7f7f7",
        high = "#b2182b"
      ) +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(
        panel.grid = ggplot2::element_blank(),
        legend.position = "right"
      ) +
      ggplot2::labs(
        title = "Projected ssGSEA Spatial Score",
        subtitle = sprintf("Column: %s", score_col),
        x = "Spatial X",
        y = "Spatial Y",
        color = score_col
      )

    out_spatial <- file.path(custom_dir, "enrichment_spatial_score_publication.png")
    ggplot2::ggsave(out_spatial, plot = p_spatial, width = 8.4, height = 6.8, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", out_spatial))
  }
}
