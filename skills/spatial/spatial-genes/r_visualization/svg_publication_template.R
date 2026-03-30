#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: svg_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
spatial_csv <- file.path(figure_data_dir, "top_svg_spatial_points.csv")
top_scores_csv <- file.path(figure_data_dir, "top_svg_scores.csv")
run_summary_csv <- file.path(figure_data_dir, "svg_run_summary.csv")

if (!file.exists(spatial_csv)) {
  stop(sprintf("Required input not found: %s", spatial_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

df <- read.csv(spatial_csv, stringsAsFactors = FALSE)
if (!"rank" %in% names(df)) {
  df$rank <- ave(seq_len(nrow(df)), df$gene, FUN = min)
}

gene_order <- unique(df[order(df$rank), "gene"])
gene_order <- gene_order[seq_len(min(length(gene_order), 4))]
df <- df[df$gene %in% gene_order, , drop = FALSE]
df$gene <- factor(df$gene, levels = gene_order)

custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

score_label <- "Score"
score_column <- NULL
if (file.exists(run_summary_csv)) {
  run_summary <- read.csv(run_summary_csv, stringsAsFactors = FALSE)
  if (all(c("metric", "value") %in% names(run_summary))) {
    metric_lookup <- setNames(run_summary$value, run_summary$metric)
    if ("score_label" %in% names(metric_lookup) && nzchar(metric_lookup[["score_label"]])) {
      score_label <- metric_lookup[["score_label"]]
    }
    if ("score_column" %in% names(metric_lookup) && nzchar(metric_lookup[["score_column"]])) {
      score_column <- metric_lookup[["score_column"]]
    }
  }
}

p <- ggplot2::ggplot(
  df,
  ggplot2::aes(x = x, y = y, color = expression)
) +
  ggplot2::geom_point(size = 0.8, alpha = 0.9) +
  ggplot2::facet_wrap(~gene, ncol = 2, scales = "fixed") +
  ggplot2::scale_y_reverse() +
  ggplot2::coord_equal() +
  ggplot2::scale_color_gradient(
    low = "#f7fbff",
    high = "#084594",
    name = "Expression"
  ) +
  ggplot2::theme_bw(base_size = 12) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    axis.title = ggplot2::element_blank(),
    axis.text = ggplot2::element_blank(),
    axis.ticks = ggplot2::element_blank(),
    strip.background = ggplot2::element_rect(fill = "#f0f0f0", color = NA)
  ) +
  ggplot2::labs(
    title = "Spatial Genes Publication View",
    subtitle = "R customization layer consuming OmicsClaw figure_data/"
  )

out_png <- file.path(custom_dir, "svg_spatial_publication.png")
ggplot2::ggsave(out_png, plot = p, width = 9.5, height = 7.5, dpi = 300)

message(sprintf("Saved custom R visualization: %s", out_png))

if (file.exists(top_scores_csv)) {
  top_df <- read.csv(top_scores_csv, stringsAsFactors = FALSE)
  if (nrow(top_df) > 0) {
    if (is.null(score_column) || !score_column %in% names(top_df)) {
      score_candidates <- names(top_df)[vapply(top_df, is.numeric, logical(1))]
      score_candidates <- setdiff(score_candidates, c("rank"))
      if (length(score_candidates) > 0) {
        score_column <- score_candidates[[1]]
      }
    }

    if (!is.null(score_column) && score_column %in% names(top_df)) {
      bar_df <- head(top_df, 12)
      bar_df$gene <- factor(bar_df$gene, levels = rev(bar_df$gene))

      bar_plot <- ggplot2::ggplot(
        bar_df,
        ggplot2::aes_string(x = "gene", y = score_column)
      ) +
        ggplot2::geom_col(fill = "#d95f02", width = 0.75) +
        ggplot2::coord_flip() +
        ggplot2::theme_bw(base_size = 12) +
        ggplot2::theme(
          panel.grid = ggplot2::element_blank(),
          axis.title.y = ggplot2::element_blank()
        ) +
        ggplot2::labs(
          title = "Top Spatially Variable Genes",
          subtitle = "Publication-style summary of the strongest exported SVG hits",
          y = score_label
        )

      bar_png <- file.path(custom_dir, "svg_top_scores_publication.png")
      ggplot2::ggsave(bar_png, plot = bar_plot, width = 8.6, height = 6.0, dpi = 300)
      message(sprintf("Saved custom R visualization: %s", bar_png))
    }
  }
}
