#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: condition_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
volcano_csv <- file.path(figure_data_dir, "pseudobulk_volcano_points.csv")
metrics_csv <- file.path(figure_data_dir, "cluster_de_metrics.csv")
summary_csv <- file.path(figure_data_dir, "condition_run_summary.csv")

if (!file.exists(volcano_csv)) {
  stop(sprintf("Required input not found: %s", volcano_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

volcano_df <- read.csv(volcano_csv, stringsAsFactors = FALSE)
if (nrow(volcano_df) < 1) {
  stop("No volcano rows available in pseudobulk_volcano_points.csv")
}

required_cols <- c(
  "gene",
  "cluster",
  "contrast",
  "log2fc",
  "pvalue_adj",
  "is_significant",
  "is_effect_hit"
)
missing_cols <- setdiff(required_cols, names(volcano_df))
if (length(missing_cols) > 0) {
  stop(sprintf(
    "Missing required columns in pseudobulk_volcano_points.csv: %s",
    paste(missing_cols, collapse = ", ")
  ))
}

if (!"neg_log10_pvalue_adj" %in% names(volcano_df)) {
  volcano_df$neg_log10_pvalue_adj <- -log10(pmax(volcano_df$pvalue_adj, 1e-300))
}

to_flag <- function(x) {
  x_chr <- tolower(trimws(as.character(x)))
  x_chr %in% c("true", "t", "1", "yes")
}

fdr_threshold <- 0.05
log2fc_threshold <- 1.0
if (file.exists(summary_csv)) {
  run_summary <- read.csv(summary_csv, stringsAsFactors = FALSE)
  if (all(c("metric", "value") %in% names(run_summary))) {
    metric_lookup <- setNames(run_summary$value, run_summary$metric)
    if ("fdr_threshold" %in% names(metric_lookup)) {
      parsed <- suppressWarnings(as.numeric(metric_lookup[["fdr_threshold"]]))
      if (!is.na(parsed)) {
        fdr_threshold <- parsed
      }
    }
    if ("log2fc_threshold" %in% names(metric_lookup)) {
      parsed <- suppressWarnings(as.numeric(metric_lookup[["log2fc_threshold"]]))
      if (!is.na(parsed)) {
        log2fc_threshold <- parsed
      }
    }
  }
}

volcano_df$panel <- paste0("Cluster ", volcano_df$cluster, " | ", volcano_df$contrast)
volcano_df$is_effect_hit_flag <- to_flag(volcano_df$is_effect_hit)
volcano_df$is_significant_flag <- to_flag(volcano_df$is_significant)
volcano_df$status <- ifelse(
  volcano_df$is_effect_hit_flag,
  "Effect hit",
  ifelse(volcano_df$is_significant_flag, "Significant", "Other")
)
volcano_df$status <- factor(
  volcano_df$status,
  levels = c("Other", "Significant", "Effect hit")
)

panel_summary <- aggregate(
  effect_hits ~ panel,
  data = transform(volcano_df, effect_hits = as.numeric(is_effect_hit_flag)),
  FUN = function(x) sum(x, na.rm = TRUE)
)
significant_summary <- aggregate(
  significant_hits ~ panel,
  data = transform(volcano_df, significant_hits = as.numeric(is_significant_flag)),
  FUN = function(x) sum(x, na.rm = TRUE)
)
min_padj_summary <- aggregate(
  pvalue_adj ~ panel,
  data = volcano_df,
  FUN = function(x) {
    x <- x[!is.na(x)]
    if (length(x) < 1) {
      return(Inf)
    }
    min(x)
  }
)
panel_summary <- merge(panel_summary, significant_summary, by = "panel", all = TRUE)
panel_summary <- merge(panel_summary, min_padj_summary, by = "panel", all = TRUE)
names(panel_summary) <- c("panel", "effect_hits", "significant_hits", "min_padj")

panel_summary <- panel_summary[order(
  -panel_summary$effect_hits,
  -panel_summary$significant_hits,
  panel_summary$min_padj,
  panel_summary$panel
), , drop = FALSE]
selected_panels <- head(panel_summary$panel, 4)
plot_df <- volcano_df[volcano_df$panel %in% selected_panels, , drop = FALSE]
plot_df$panel <- factor(plot_df$panel, levels = selected_panels)

label_df <- do.call(
  rbind,
  lapply(selected_panels, function(panel_name) {
    panel_df <- plot_df[plot_df$panel == panel_name, , drop = FALSE]
    panel_df <- panel_df[order(
      -panel_df$is_effect_hit_flag,
      -panel_df$is_significant_flag,
      panel_df$pvalue_adj,
      -abs(panel_df$log2fc),
      panel_df$gene
    ), , drop = FALSE]
    head(panel_df, 3)
  })
)

custom_dir <- file.path(output_dir, "figures", "custom")
dir.create(custom_dir, recursive = TRUE, showWarnings = FALSE)

volcano_plot <- ggplot2::ggplot(
  plot_df,
  ggplot2::aes(x = log2fc, y = neg_log10_pvalue_adj, color = status)
) +
  ggplot2::geom_point(size = 1.3, alpha = 0.8) +
  ggplot2::geom_vline(
    xintercept = c(-log2fc_threshold, log2fc_threshold),
    linetype = "dashed",
    linewidth = 0.4,
    color = "#636363"
  ) +
  ggplot2::geom_hline(
    yintercept = -log10(max(fdr_threshold, 1e-300)),
    linetype = "dashed",
    linewidth = 0.4,
    color = "#636363"
  ) +
  ggplot2::facet_wrap(~panel, ncol = 2, scales = "fixed") +
  ggplot2::scale_color_manual(
    values = c(
      "Other" = "#9e9e9e",
      "Significant" = "#4292c6",
      "Effect hit" = "#cb181d"
    )
  ) +
  ggplot2::theme_bw(base_size = 12) +
  ggplot2::theme(
    panel.grid = ggplot2::element_blank(),
    legend.title = ggplot2::element_blank(),
    strip.background = ggplot2::element_rect(fill = "#f0f0f0", color = NA)
  ) +
  ggplot2::labs(
    title = "Spatial Condition Publication View",
    subtitle = "R customization layer consuming OmicsClaw figure_data/",
    x = "Log2 fold change",
    y = "-log10(adj. p-value)"
  )

if (nrow(label_df) > 0) {
  if (requireNamespace("ggrepel", quietly = TRUE)) {
    volcano_plot <- volcano_plot +
      ggrepel::geom_text_repel(
        data = label_df,
        ggplot2::aes(label = gene),
        size = 3.0,
        min.segment.length = 0,
        box.padding = 0.3,
        max.overlaps = Inf,
        show.legend = FALSE
      )
  } else {
    volcano_plot <- volcano_plot +
      ggplot2::geom_text(
        data = label_df,
        ggplot2::aes(label = gene),
        size = 2.8,
        vjust = -0.6,
        show.legend = FALSE
      )
  }
}

volcano_png <- file.path(custom_dir, "condition_volcano_publication.png")
ggplot2::ggsave(volcano_png, plot = volcano_plot, width = 10.0, height = 7.6, dpi = 300)
message(sprintf("Saved custom R visualization: %s", volcano_png))

if (file.exists(metrics_csv)) {
  metrics_df <- read.csv(metrics_csv, stringsAsFactors = FALSE)
  if (all(c("cluster", "n_significant_total", "n_effect_size_hits_total") %in% names(metrics_df))) {
    metrics_df <- metrics_df[order(
      metrics_df$n_effect_size_hits_total,
      metrics_df$n_significant_total,
      metrics_df$cluster
    ), , drop = FALSE]
    metrics_df$cluster <- factor(metrics_df$cluster, levels = metrics_df$cluster)

    burden_plot <- ggplot2::ggplot(metrics_df) +
      ggplot2::geom_col(
        ggplot2::aes(x = cluster, y = n_significant_total),
        fill = "#9ecae1",
        width = 0.72
      ) +
      ggplot2::geom_point(
        ggplot2::aes(x = cluster, y = n_effect_size_hits_total),
        color = "#cb181d",
        size = 2.4
      ) +
      ggplot2::coord_flip() +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(panel.grid = ggplot2::element_blank()) +
      ggplot2::labs(
        title = "Per-Cluster DE Burden",
        subtitle = "Bars show significant hits; red points show effect-size hits",
        x = "Cluster",
        y = "Gene count"
      )

    burden_png <- file.path(custom_dir, "condition_cluster_burden_publication.png")
    ggplot2::ggsave(burden_png, plot = burden_plot, width = 7.8, height = 5.8, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", burden_png))
  }
}
