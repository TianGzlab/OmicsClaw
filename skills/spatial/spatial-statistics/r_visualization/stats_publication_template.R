#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: stats_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
summary_csv <- file.path(figure_data_dir, "analysis_summary.csv")
top_results_csv <- file.path(figure_data_dir, "top_results.csv")
analysis_results_csv <- file.path(figure_data_dir, "analysis_results.csv")

if (!file.exists(summary_csv)) {
  stop(sprintf("Required input not found: %s", summary_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

summary_df <- read.csv(summary_csv, stringsAsFactors = FALSE)
analysis_type <- "spatial_statistics"
if (all(c("metric", "value") %in% names(summary_df))) {
  metric_lookup <- setNames(summary_df$value, summary_df$metric)
  if ("analysis_type" %in% names(metric_lookup) && nzchar(metric_lookup[["analysis_type"]])) {
    analysis_type <- metric_lookup[["analysis_type"]]
  }
}

custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

pick_label_column <- function(df) {
  for (candidate in c("gene", "cluster", "cluster_a", "gene_a")) {
    if (candidate %in% names(df)) {
      return(candidate)
    }
  }
  return(NULL)
}

pick_value_column <- function(df) {
  numeric_cols <- names(df)[vapply(df, is.numeric, logical(1))]
  numeric_cols <- setdiff(numeric_cols, c("rank"))
  if (length(numeric_cols) < 1) {
    return(NULL)
  }
  numeric_cols[[1]]
}

plot_df <- NULL
if (file.exists(top_results_csv)) {
  plot_df <- read.csv(top_results_csv, stringsAsFactors = FALSE)
} else if (file.exists(analysis_results_csv)) {
  plot_df <- read.csv(analysis_results_csv, stringsAsFactors = FALSE)
}

if (!is.null(plot_df) && nrow(plot_df) > 0) {
  label_col <- pick_label_column(plot_df)
  value_col <- pick_value_column(plot_df)
  if (!is.null(label_col) && !is.null(value_col)) {
    bar_df <- head(plot_df, 12)
    if ("cluster_a" %in% names(bar_df) && "cluster_b" %in% names(bar_df)) {
      bar_df$label <- paste(bar_df$cluster_a, bar_df$cluster_b, sep = " | ")
    } else {
      bar_df$label <- as.character(bar_df[[label_col]])
    }
    bar_df$label <- factor(bar_df$label, levels = rev(bar_df$label))

    p <- ggplot2::ggplot(bar_df, ggplot2::aes_string(x = "label", y = value_col)) +
      ggplot2::geom_col(fill = "#3182bd", width = 0.75) +
      ggplot2::coord_flip() +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(
        panel.grid = ggplot2::element_blank(),
        axis.title.y = ggplot2::element_blank()
      ) +
      ggplot2::labs(
        title = "Spatial Statistics Publication View",
        subtitle = sprintf("Top exported results for %s", analysis_type),
        y = value_col
      )

    out_png <- file.path(custom_dir, "statistics_top_results_publication.png")
    ggplot2::ggsave(out_png, plot = p, width = 8.8, height = 6.2, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", out_png))
  } else {
    message("No suitable label/value columns found in exported statistics tables; no custom plot written.")
  }
} else {
  message("No top_results.csv or analysis_results.csv available; no custom plot written.")
}
