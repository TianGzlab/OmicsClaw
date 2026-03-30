#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: preprocess_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
spatial_points_csv <- file.path(figure_data_dir, "preprocess_spatial_points.csv")
umap_points_csv <- file.path(figure_data_dir, "preprocess_umap_points.csv")
cluster_summary_csv <- file.path(figure_data_dir, "cluster_summary.csv")
qc_distribution_csv <- file.path(figure_data_dir, "qc_metric_distributions.csv")

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

cluster_plot_df <- NULL
cluster_basis <- NULL
if (file.exists(spatial_points_csv)) {
  cluster_plot_df <- read.csv(spatial_points_csv, stringsAsFactors = FALSE)
  if (all(c("x", "y", "leiden") %in% names(cluster_plot_df))) {
    cluster_basis <- "spatial"
  } else {
    cluster_plot_df <- NULL
  }
}

if (is.null(cluster_plot_df) && file.exists(umap_points_csv)) {
  cluster_plot_df <- read.csv(umap_points_csv, stringsAsFactors = FALSE)
  if (all(c("umap_1", "umap_2", "leiden") %in% names(cluster_plot_df))) {
    names(cluster_plot_df)[names(cluster_plot_df) == "umap_1"] <- "x"
    names(cluster_plot_df)[names(cluster_plot_df) == "umap_2"] <- "y"
    cluster_basis <- "umap"
  } else {
    cluster_plot_df <- NULL
  }
}

if (!is.null(cluster_plot_df)) {
  cluster_plot_df$leiden <- factor(cluster_plot_df$leiden)
  cluster_plot <- ggplot2::ggplot(
    cluster_plot_df,
    ggplot2::aes(x = x, y = y, color = leiden)
  ) +
    ggplot2::geom_point(size = 0.7, alpha = 0.9) +
    ggplot2::coord_equal() +
    ggplot2::theme_bw(base_size = 12) +
    ggplot2::theme(
      panel.grid = ggplot2::element_blank(),
      legend.title = ggplot2::element_blank()
    ) +
    ggplot2::labs(
      title = "Spatial Preprocess Publication View",
      subtitle = sprintf("Cluster overview from exported %s coordinates", cluster_basis),
      x = if (cluster_basis == "spatial") "X" else "UMAP 1",
      y = if (cluster_basis == "spatial") "Y" else "UMAP 2"
    )

  if (cluster_basis == "spatial") {
    cluster_plot <- cluster_plot + ggplot2::scale_y_reverse()
  }

  cluster_png <- file.path(custom_dir, "preprocess_cluster_publication.png")
  ggplot2::ggsave(cluster_png, plot = cluster_plot, width = 8.4, height = 6.6, dpi = 300)
  message(sprintf("Saved custom R visualization: %s", cluster_png))
}

if (file.exists(qc_distribution_csv)) {
  qc_df <- read.csv(qc_distribution_csv, stringsAsFactors = FALSE)
  metric_cols <- intersect(
    c("n_genes_by_counts", "total_counts", "pct_counts_mt"),
    names(qc_df)
  )

  if (length(metric_cols) > 0) {
    long_df <- do.call(
      rbind,
      lapply(metric_cols, function(metric_name) {
        data.frame(
          metric = metric_name,
          value = qc_df[[metric_name]],
          stringsAsFactors = FALSE
        )
      })
    )

    qc_plot <- ggplot2::ggplot(
      long_df,
      ggplot2::aes(x = value)
    ) +
      ggplot2::geom_histogram(bins = 30, fill = "#9ecae1", color = "white") +
      ggplot2::facet_wrap(~metric, scales = "free_x", ncol = 3) +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(panel.grid = ggplot2::element_blank()) +
      ggplot2::labs(
        title = "QC Distribution Overview",
        subtitle = "R customization layer consuming OmicsClaw figure_data/",
        x = "Metric value",
        y = "Cells or spots"
      )

    qc_png <- file.path(custom_dir, "preprocess_qc_publication.png")
    ggplot2::ggsave(qc_png, plot = qc_plot, width = 11.0, height = 4.8, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", qc_png))
  }
}

if (file.exists(cluster_summary_csv)) {
  cluster_summary <- read.csv(cluster_summary_csv, stringsAsFactors = FALSE)
  if (nrow(cluster_summary) > 0 && all(c("cluster", "n_cells") %in% names(cluster_summary))) {
    cluster_summary$cluster <- factor(
      cluster_summary$cluster,
      levels = cluster_summary$cluster[order(cluster_summary$n_cells)]
    )

    summary_plot <- ggplot2::ggplot(
      cluster_summary,
      ggplot2::aes(x = cluster, y = n_cells)
    ) +
      ggplot2::geom_col(fill = "#3182bd", width = 0.75) +
      ggplot2::coord_flip() +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(panel.grid = ggplot2::element_blank()) +
      ggplot2::labs(
        title = "Cluster Size Summary",
        x = "Leiden cluster",
        y = "Number of cells or spots"
      )

    summary_png <- file.path(custom_dir, "preprocess_cluster_sizes_publication.png")
    ggplot2::ggsave(summary_png, plot = summary_plot, width = 7.2, height = 5.4, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", summary_png))
  }
}
