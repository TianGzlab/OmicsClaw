#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 1) {
  stop("Usage: de_publication_template.R <analysis_output_dir>")
}

output_dir <- normalizePath(args[[1]], mustWork = TRUE)
figure_data_dir <- file.path(output_dir, "figure_data")
plot_points_csv <- file.path(figure_data_dir, "de_plot_points.csv")
top_hits_csv <- file.path(figure_data_dir, "top_de_hits.csv")
run_summary_csv <- file.path(figure_data_dir, "de_run_summary.csv")

if (!file.exists(plot_points_csv)) {
  stop(sprintf("Required input not found: %s", plot_points_csv))
}

if (!requireNamespace("ggplot2", quietly = TRUE)) {
  stop("Package 'ggplot2' is required for this template.")
}

to_flag <- function(x) {
  x_chr <- tolower(trimws(as.character(x)))
  x_chr %in% c("true", "t", "1", "yes")
}

plot_df <- read.csv(plot_points_csv, stringsAsFactors = FALSE)
if (nrow(plot_df) < 1) {
  stop("No rows available in de_plot_points.csv")
}

required_cols <- c(
  "gene",
  "group",
  "comparison",
  "log2fc",
  "pvalue_adj",
  "is_significant",
  "is_effect_hit"
)
missing_cols <- setdiff(required_cols, names(plot_df))
if (length(missing_cols) > 0) {
  stop(sprintf(
    "Missing required columns in de_plot_points.csv: %s",
    paste(missing_cols, collapse = ", ")
  ))
}

if (!"neg_log10_pvalue_adj" %in% names(plot_df)) {
  plot_df$neg_log10_pvalue_adj <- -log10(pmax(plot_df$pvalue_adj, 1e-300))
}
plot_df$is_significant_flag <- to_flag(plot_df$is_significant)
plot_df$is_effect_hit_flag <- to_flag(plot_df$is_effect_hit)

fdr_threshold <- 0.05
log2fc_threshold <- 1.0
if (file.exists(run_summary_csv)) {
  run_summary <- read.csv(run_summary_csv, stringsAsFactors = FALSE)
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

plot_df$panel <- ifelse(
  nzchar(plot_df$comparison),
  plot_df$comparison,
  paste0("Group ", plot_df$group)
)
plot_df$status <- ifelse(
  plot_df$is_effect_hit_flag,
  "Effect hit",
  ifelse(plot_df$is_significant_flag, "Significant", "Other")
)
plot_df$status <- factor(
  plot_df$status,
  levels = c("Other", "Significant", "Effect hit")
)

effect_summary <- aggregate(
  effect_hits ~ panel,
  data = transform(plot_df, effect_hits = as.numeric(is_effect_hit_flag)),
  FUN = function(x) sum(x, na.rm = TRUE)
)
significant_summary <- aggregate(
  significant_hits ~ panel,
  data = transform(plot_df, significant_hits = as.numeric(is_significant_flag)),
  FUN = function(x) sum(x, na.rm = TRUE)
)
min_padj_summary <- aggregate(
  pvalue_adj ~ panel,
  data = plot_df,
  FUN = function(x) {
    x <- x[!is.na(x)]
    if (length(x) < 1) {
      return(Inf)
    }
    min(x)
  }
)
panel_summary <- merge(effect_summary, significant_summary, by = "panel", all = TRUE)
panel_summary <- merge(panel_summary, min_padj_summary, by = "panel", all = TRUE)
names(panel_summary) <- c("panel", "effect_hits", "significant_hits", "min_padj")
panel_summary <- panel_summary[order(
  -panel_summary$effect_hits,
  -panel_summary$significant_hits,
  panel_summary$min_padj,
  panel_summary$panel
), , drop = FALSE]

selected_panels <- head(panel_summary$panel, 4)
volcano_df <- plot_df[plot_df$panel %in% selected_panels, , drop = FALSE]
volcano_df$panel <- factor(volcano_df$panel, levels = selected_panels)

label_df <- do.call(
  rbind,
  lapply(selected_panels, function(panel_name) {
    panel_df <- volcano_df[volcano_df$panel == panel_name, , drop = FALSE]
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
  volcano_df,
  ggplot2::aes(x = log2fc, y = neg_log10_pvalue_adj, color = status)
) +
  ggplot2::geom_point(size = 1.2, alpha = 0.8) +
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
    title = "Spatial DE Publication View",
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

volcano_png <- file.path(custom_dir, "de_volcano_publication.png")
ggplot2::ggsave(volcano_png, plot = volcano_plot, width = 10.0, height = 7.6, dpi = 300)
message(sprintf("Saved custom R visualization: %s", volcano_png))

if (file.exists(top_hits_csv)) {
  top_hits_df <- read.csv(top_hits_csv, stringsAsFactors = FALSE)
  if (nrow(top_hits_df) > 0 && all(c("gene", "group", "log2fc") %in% names(top_hits_df))) {
    bar_df <- head(top_hits_df, 12)
    bar_df$label <- paste0(bar_df$group, ":", bar_df$gene)
    bar_df$label <- factor(bar_df$label, levels = rev(bar_df$label))
    bar_df$fill_group <- ifelse(bar_df$log2fc >= 0, "Up", "Down")

    bar_plot <- ggplot2::ggplot(
      bar_df,
      ggplot2::aes(x = label, y = log2fc, fill = fill_group)
    ) +
      ggplot2::geom_col(width = 0.75) +
      ggplot2::coord_flip() +
      ggplot2::scale_fill_manual(values = c("Up" = "#cb181d", "Down" = "#3182bd")) +
      ggplot2::theme_bw(base_size = 12) +
      ggplot2::theme(
        panel.grid = ggplot2::element_blank(),
        legend.title = ggplot2::element_blank()
      ) +
      ggplot2::labs(
        title = "Top DE Hits",
        subtitle = "Publication-style view of the strongest exported hits",
        x = NULL,
        y = "Log2 fold change"
      )

    bar_png <- file.path(custom_dir, "de_top_hits_publication.png")
    ggplot2::ggsave(bar_png, plot = bar_plot, width = 8.8, height = 6.2, dpi = 300)
    message(sprintf("Saved custom R visualization: %s", bar_png))
  }
}
