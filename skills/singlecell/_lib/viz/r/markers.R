# markers.R -- GroupHeatmap-equivalent renderer for sc-markers output
#
# Reads markers_top.csv from figure_data/, pivots to gene x cluster matrix,
# renders a ComplexHeatmap with blue-white-red diverging color scale.
#
# Provides: plot_marker_heatmap()
# Requires: common.R sourced first (for ggsave_standard, parse_kv, etc.)

`%||%` <- function(a, b) if (!is.null(a)) a else b

#' Grouped marker heatmap (ComplexHeatmap).
#'
#' @param data_dir Character. Path to figure_data directory containing markers_top.csv.
#' @param out_path Character. Absolute path for the output PNG.
#' @param params  Named list of extra parameters (e.g. n_top=5).
plot_marker_heatmap <- function(data_dir, out_path, params) {
  tryCatch({
    suppressPackageStartupMessages({
      library(ComplexHeatmap)
      library(circlize)
      library(tidyr)
      library(dplyr)
    })

    csv_path <- file.path(data_dir, "markers_top.csv")
    if (!file.exists(csv_path)) {
      cat("ERROR: markers_top.csv not found in", data_dir, "\n", file = stderr())
      quit(status = 1)
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) {
      cat("ERROR: markers_top.csv is empty\n", file = stderr())
      quit(status = 1)
    }

    # Validate required columns
    required <- c("group", "names")
    missing_cols <- setdiff(required, colnames(df))
    if (length(missing_cols) > 0) {
      cat("ERROR: markers_top.csv missing columns:",
          paste(missing_cols, collapse = ", "),
          ". Expected: group, names, logfoldchanges|scores\n",
          file = stderr())
      quit(status = 1)
    }

    # Determine value column: prefer logfoldchanges, fall back to scores
    if ("logfoldchanges" %in% colnames(df) && !all(is.na(df$logfoldchanges))) {
      val_col <- "logfoldchanges"
    } else if ("scores" %in% colnames(df)) {
      val_col <- "scores"
    } else {
      cat("ERROR: markers_top.csv has neither logfoldchanges nor scores column\n",
          file = stderr())
      quit(status = 1)
    }

    # Remove rows where value is NA
    df <- df[!is.na(df[[val_col]]), ]
    if (nrow(df) == 0) {
      cat("ERROR: All values in", val_col, "are NA\n", file = stderr())
      quit(status = 1)
    }

    # Limit to top N genes per cluster
    n_top <- as.integer(params[["n_top"]] %||% 10)
    df <- df %>%
      group_by(group) %>%
      slice_max(order_by = .data[[val_col]], n = n_top, with_ties = FALSE) %>%
      ungroup()

    # Preserve cluster order from data
    cluster_order <- unique(df$group)
    df$group <- factor(df$group, levels = cluster_order)

    # Pivot to wide matrix: genes as rows, clusters as columns.
    # Use NA fill (not 0) so genes absent from a cluster are visually distinct
    # from genes with zero logFC — only the source-cluster column carries a value.
    wide <- pivot_wider(
      df,
      id_cols     = "names",
      names_from  = "group",
      values_from = all_of(val_col),
      values_fill = NA_real_,
      values_fn   = mean
    )
    wide <- as.data.frame(wide)
    rownames(wide) <- wide$names
    wide$names <- NULL
    mat <- as.matrix(wide)
    # Ensure numeric
    storage.mode(mat) <- "double"

    # Reorder columns to match cluster_order
    mat <- mat[, as.character(cluster_order), drop = FALSE]

    # Column split factor for per-cluster slicing
    col_split <- factor(colnames(mat), levels = colnames(mat))

    # Color scale: white-to-red for positive logFC values (marker genes are
    # upregulated by definition in one-vs-rest tests). NA cells rendered gray.
    mat_max <- max(mat, na.rm = TRUE)
    mat_min <- min(mat[!is.na(mat)], na.rm = TRUE)
    if (mat_min < 0) {
      # Mixed direction: diverging blue-white-red
      col_fun <- colorRamp2(c(mat_min, 0, mat_max), c("#2166AC", "white", "#D6604D"))
    } else {
      # All positive (typical one-vs-rest markers): white-to-red
      col_fun <- colorRamp2(c(0, mat_max), c("white", "#D6604D"))
    }

    # Build heatmap — NA cells shown in light gray to highlight the diagonal
    # pattern where each gene's logFC is only filled in its source cluster
    ht <- Heatmap(
      mat,
      name                 = val_col,
      col                  = col_fun,
      na_col               = "#E8E8E8",
      column_split         = col_split,
      cluster_rows         = FALSE,
      cluster_columns      = FALSE,
      cluster_row_slices   = FALSE,
      cluster_column_slices = FALSE,
      show_row_names       = TRUE,
      show_column_names    = FALSE,
      row_names_side       = "left",
      row_names_gp         = gpar(fontsize = 8),
      column_title_gp      = gpar(fontsize = 9, fontface = "bold"),
      border               = TRUE,
      heatmap_legend_param = list(
        title            = val_col,
        legend_direction = "horizontal",
        title_position   = "topcenter"
      )
    )

    # Save -- ComplexHeatmap uses base R graphics, not ggplot2
    out_dir <- dirname(out_path)
    if (!dir.exists(out_dir)) {
      dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
    }

    fig_height <- max(4, nrow(mat) * 0.18)
    png(out_path, width = 10, height = fig_height, units = "in", res = 200)
    draw(ht, heatmap_legend_side = "bottom")
    dev.off()

    cat("Saved:", out_path, "\n")

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
