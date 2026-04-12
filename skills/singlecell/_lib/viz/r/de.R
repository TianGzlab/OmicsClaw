# de.R -- DE volcano plot and expression heatmap renderers
#
# Reads de_top_markers.csv from figure_data/, produces:
# 1. Volcano plot (ggplot2 + ggrepel) with up/down/ns coloring
# 2. Expression heatmap (ComplexHeatmap) with gene x group matrix
#
# Provides: plot_de_volcano(), plot_de_heatmap()
# Requires: common.R sourced first (for theme_omics, omics_palette, ggsave_standard, parse_kv)

`%||%` <- function(a, b) if (!is.null(a)) a else b

# ---- Column detection helper (shared by both renderers) ----
# Handles dual CSV schema: scanpy (names/logfoldchanges/pvals_adj)
#                       vs pseudobulk (gene/log2fc/padj)
.detect_de_columns <- function(df) {
  cols <- colnames(df)

  # Gene column
  if ("names" %in% cols) {
    gene_col <- "names"
  } else if ("gene" %in% cols) {
    gene_col <- "gene"
  } else {
    stop("CSV missing gene column: expected 'names' or 'gene'")
  }

  # Fold change column
  fc_col <- NULL
  fc_is_scores <- FALSE
  if ("logfoldchanges" %in% cols && !all(is.na(df[["logfoldchanges"]]))) {
    fc_col <- "logfoldchanges"
  } else if ("log2fc" %in% cols && !all(is.na(df[["log2fc"]]))) {
    fc_col <- "log2fc"
  } else if ("scores" %in% cols) {
    fc_col <- "scores"
    fc_is_scores <- TRUE
    message("Warning: Using 'scores' as fold-change proxy (log2FC not available)")
  } else {
    stop("CSV missing fold-change column: expected 'logfoldchanges', 'log2fc', or 'scores'")
  }

  # P-value column
  if ("pvals_adj" %in% cols) {
    pval_col <- "pvals_adj"
  } else if ("padj" %in% cols) {
    pval_col <- "padj"
  } else {
    stop("CSV missing adjusted p-value column: expected 'pvals_adj' or 'padj'")
  }

  list(gene = gene_col, fc = fc_col, pval = pval_col, fc_is_scores = fc_is_scores)
}

# ---- Read and validate CSV ----
.read_de_csv <- function(data_dir) {
  csv_path <- file.path(data_dir, "de_top_markers.csv")
  if (!file.exists(csv_path)) {
    cat("ERROR: de_top_markers.csv not found in", data_dir, "\n", file = stderr())
    quit(status = 1)
  }
  df <- read.csv(csv_path, stringsAsFactors = FALSE)
  if (nrow(df) == 0) {
    cat("ERROR: de_top_markers.csv is empty\n", file = stderr())
    quit(status = 1)
  }
  df
}

# ============================================================
# Function 1: Volcano Plot
# ============================================================

#' DE volcano plot (ggplot2 + ggrepel).
#'
#' @param data_dir Character. Path to figure_data directory containing de_top_markers.csv.
#' @param out_path Character. Absolute path for the output PNG.
#' @param params  Named list of extra parameters.
#'   padj_thresh (default 0.05), fc_thresh (default 0.25), n_label (default 5).
plot_de_volcano <- function(data_dir, out_path, params) {
  tryCatch({
    suppressPackageStartupMessages({
      library(ggrepel)
    })

    df <- .read_de_csv(data_dir)
    det <- .detect_de_columns(df)

    # Unify column names for plotting
    df$gene_name <- df[[det$gene]]
    df$fc        <- as.numeric(df[[det$fc]])
    df$pval      <- as.numeric(df[[det$pval]])

    # Remove rows with NA in key columns
    df <- df[!is.na(df$fc) & !is.na(df$pval), ]
    if (nrow(df) == 0) {
      cat("ERROR: No valid rows after removing NA values\n", file = stderr())
      quit(status = 1)
    }

    # Parameters
    padj_thresh <- as.numeric(params[["padj_thresh"]] %||% "0.05")
    fc_thresh   <- as.numeric(params[["fc_thresh"]]   %||% "0.25")
    n_label     <- as.integer(params[["n_label"]]      %||% "5")

    # Derived columns
    df$neg_log10_pval <- -log10(df$pval + 1e-300)
    df$direction <- ifelse(
      df$fc > fc_thresh & df$pval < padj_thresh, "Up",
      ifelse(df$fc < -fc_thresh & df$pval < padj_thresh, "Down", "NS")
    )
    df$direction <- factor(df$direction, levels = c("Up", "Down", "NS"))

    direction_colors <- c("Up" = "#E41A1C", "Down" = "#377EB8", "NS" = "#CCCCCC")

    # Ensure group column exists for faceting
    if ("group" %in% colnames(df)) {
      groups <- unique(df$group)
      n_groups <- length(groups)
    } else {
      df$group <- "All"
      n_groups <- 1
    }

    # Select top genes to label per group per direction
    df$label_score <- abs(df$fc) * df$neg_log10_pval
    label_df <- do.call(rbind, lapply(split(df, df$group), function(gdf) {
      up_genes <- gdf[gdf$direction == "Up", ]
      up_genes <- head(up_genes[order(-up_genes$label_score), ], n_label)
      dn_genes <- gdf[gdf$direction == "Down", ]
      dn_genes <- head(dn_genes[order(-dn_genes$label_score), ], n_label)
      rbind(up_genes, dn_genes)
    }))
    df$label_text <- ifelse(df$gene_name %in% label_df$gene_name &
                            paste(df$gene_name, df$group) %in%
                            paste(label_df$gene_name, label_df$group),
                            df$gene_name, NA_character_)

    # Build plot
    fc_label <- if (det$fc_is_scores) "Score" else "log2FC"
    p <- ggplot(df, aes(x = fc, y = neg_log10_pval, color = direction)) +
      geom_point(size = 0.8, alpha = 0.6) +
      scale_color_manual(values = direction_colors, name = "Direction") +
      geom_hline(yintercept = -log10(padj_thresh), linetype = "dashed",
                 color = "grey40", linewidth = 0.4) +
      geom_vline(xintercept = c(-fc_thresh, fc_thresh), linetype = "dashed",
                 color = "grey40", linewidth = 0.4) +
      geom_text_repel(
        aes(label = label_text),
        size = 2.8, max.overlaps = 20,
        segment.size = 0.3, segment.color = "grey50",
        na.rm = TRUE, show.legend = FALSE
      ) +
      theme_omics() +
      labs(x = fc_label, y = expression(-log[10](p[adj])))

    # Facet if multiple groups
    if (n_groups > 1) {
      p <- p + facet_wrap(~ group, scales = "free")
      ncol_facet <- min(ceiling(sqrt(n_groups)), 5)
      nrow_facet <- ceiling(n_groups / ncol_facet)
      fig_w <- min(4 * ncol_facet, 20)
      fig_h <- min(4 * nrow_facet, 16)
    } else {
      fig_w <- 8
      fig_h <- 6
    }

    ggsave_standard(p, out_path, width = fig_w, height = fig_h)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ============================================================
# Function 2: DE Expression Heatmap
# ============================================================

#' DE expression heatmap (ComplexHeatmap).
#'
#' @param data_dir Character. Path to figure_data directory containing de_top_markers.csv.
#' @param out_path Character. Absolute path for the output PNG.
#' @param params  Named list of extra parameters. n_top (default 5).
plot_de_heatmap <- function(data_dir, out_path, params) {
  tryCatch({
    suppressPackageStartupMessages({
      library(ComplexHeatmap)
      library(circlize)
      library(tidyr)
      library(dplyr)
    })

    df <- .read_de_csv(data_dir)
    det <- .detect_de_columns(df)

    # Unify column names
    df$gene_name <- df[[det$gene]]
    df$fc        <- as.numeric(df[[det$fc]])

    # Remove NA fc rows
    df <- df[!is.na(df$fc), ]
    if (nrow(df) == 0) {
      cat("ERROR: No valid rows after removing NA values\n", file = stderr())
      quit(status = 1)
    }

    # Ensure group column exists
    if (!"group" %in% colnames(df)) {
      cat("ERROR: de_top_markers.csv missing 'group' column\n", file = stderr())
      quit(status = 1)
    }

    n_top <- as.integer(params[["n_top"]] %||% "5")

    # Select top N genes per group by FC descending
    df <- df %>%
      group_by(group) %>%
      slice_max(order_by = fc, n = n_top, with_ties = FALSE) %>%
      ungroup()

    # Preserve group order
    group_order <- unique(df$group)
    df$group <- factor(df$group, levels = group_order)

    # Record which group each gene came from (for row_split)
    gene_origin <- df %>%
      distinct(gene_name, .keep_all = TRUE) %>%
      select(gene_name, group)

    # Pivot to wide: gene x group matrix
    wide <- pivot_wider(
      df,
      id_cols     = "gene_name",
      names_from  = "group",
      values_from = "fc",
      values_fill = 0,
      values_fn   = mean
    )
    wide <- as.data.frame(wide)
    rownames(wide) <- wide$gene_name
    wide$gene_name <- NULL
    mat <- as.matrix(wide)
    storage.mode(mat) <- "double"

    # Reorder columns
    mat <- mat[, as.character(group_order), drop = FALSE]

    # Row split by group of origin
    row_split <- gene_origin$group[match(rownames(mat), gene_origin$gene_name)]
    row_split <- factor(row_split, levels = group_order)

    # Color scale: blue-white-red, clipped at -2/+2
    col_fun <- colorRamp2(c(-2, 0, 2), c("#377EB8", "white", "#E41A1C"))

    # Column annotation with omics_palette colors
    n_groups <- length(group_order)
    group_colors <- omics_palette(n_groups)
    names(group_colors) <- as.character(group_order)
    col_anno <- HeatmapAnnotation(
      `Cell Type` = as.character(group_order),
      col = list(`Cell Type` = group_colors),
      show_legend = TRUE
    )

    # Value column name for legend
    val_name <- if (det$fc_is_scores) "Score" else "log2FC"

    ht <- Heatmap(
      mat,
      name              = val_name,
      col               = col_fun,
      cluster_rows      = FALSE,
      cluster_columns   = FALSE,
      row_split         = row_split,
      top_annotation    = col_anno,
      column_title      = "Cell Type",
      row_title_gp      = gpar(fontsize = 8),
      show_row_names    = TRUE,
      row_names_gp      = gpar(fontsize = 7),
      column_names_gp   = gpar(fontsize = 9),
      border            = TRUE,
      heatmap_legend_param = list(
        title            = val_name,
        legend_direction = "horizontal",
        title_position   = "topcenter"
      )
    )

    # Save
    out_dir <- dirname(out_path)
    if (!dir.exists(out_dir)) {
      dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
    }

    fig_w <- max(6, ncol(mat) * 0.7 + 2)
    fig_h <- max(4, nrow(mat) * 0.18 + 2)
    png(out_path, width = fig_w, height = fig_h, units = "in", res = 200)
    draw(ht, heatmap_legend_side = "bottom")
    dev.off()

    cat("Saved:", out_path, "\n")

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}


# ============================================================
# Function 3: DE Manhattan Plot
# ============================================================

#' DE manhattan plot -- multi-group jittered strip chart.
#'
#' Shows all groups side-by-side as vertical columns with jittered gene
#' points colored by log2FC (blue-white-red gradient). Significant genes
#' get a black outline; top genes per group are labeled.
#'
#' @param data_dir Character. Path to figure_data directory containing de_top_markers.csv.
#' @param out_path Character. Absolute path for the output PNG.
#' @param params  Named list of extra parameters.
#'   padj_thresh (default 0.05), fc_thresh (default 0.25),
#'   n_label (default 3), jitter_width (default 0.4).
plot_de_manhattan <- function(data_dir, out_path, params) {
  tryCatch({
    df <- .read_de_csv(data_dir)
    det <- .detect_de_columns(df)

    # Unify column names
    df$gene_name <- df[[det$gene]]
    df$fc        <- as.numeric(df[[det$fc]])
    df$pval      <- as.numeric(df[[det$pval]])

    # Remove rows with NA in key columns
    df <- df[!is.na(df$fc) & !is.na(df$pval), ]
    if (nrow(df) == 0) {
      cat("ERROR: No valid rows after removing NA values\n", file = stderr())
      quit(status = 1)
    }

    # Parameters
    padj_thresh  <- as.numeric(params[["padj_thresh"]]  %||% "0.05")
    fc_thresh    <- as.numeric(params[["fc_thresh"]]    %||% "0.25")
    n_label      <- as.integer(params[["n_label"]]       %||% "3")
    jitter_width <- as.numeric(params[["jitter_width"]]  %||% "0.4")

    # Ensure group column
    if ("group" %in% colnames(df)) {
      groups <- unique(df$group)
    } else {
      df$group <- "All"
      groups <- "All"
    }
    n_groups <- length(groups)
    df$group <- factor(df$group, levels = groups)

    # Integer x position per group + jitter
    set.seed(42)
    df$x_num  <- as.numeric(df$group)
    df$x_plot <- df$x_num + (stats::runif(nrow(df)) - 0.5) * jitter_width

    # Significance flag
    df$is_sig <- abs(df$fc) > fc_thresh & df$pval < padj_thresh

    # Symmetric FC limits for color scale
    fc_max <- max(abs(df$fc), na.rm = TRUE)
    fc_lim <- c(-fc_max, fc_max)

    # Clip extreme FC for display
    df$fc_clipped <- pmax(pmin(df$fc, fc_max), -fc_max)

    # ---- Label score: top N per group ----
    df$label_score <- abs(df$fc) * (-log10(df$pval + 1e-300))
    label_df <- do.call(rbind, lapply(split(df, df$group), function(gdf) {
      gdf_sig <- gdf[gdf$is_sig, , drop = FALSE]
      if (nrow(gdf_sig) == 0) gdf_sig <- gdf
      head(gdf_sig[order(-gdf_sig$label_score), ], n_label)
    }))

    # ---- Tile data for group color bar at y = 0 ----
    tile_colors <- omics_palette(n_groups)
    names(tile_colors) <- levels(df$group)
    tile_data <- data.frame(
      group = factor(levels(df$group), levels = levels(df$group)),
      x     = seq_len(n_groups),
      y     = 0,
      stringsAsFactors = FALSE
    )

    # ---- Background range columns per group ----
    back_data <- do.call(rbind, lapply(split(df, df$group), function(gdf) {
      data.frame(
        group = gdf$group[1],
        x_num = as.numeric(gdf$group)[1],
        ymin  = min(gdf$fc, na.rm = TRUE) - 0.2,
        ymax  = max(gdf$fc, na.rm = TRUE) + 0.2,
        stringsAsFactors = FALSE
      )
    }))

    # ---- Build plot ----
    fc_label <- if (det$fc_is_scores) "Score" else "Average log2FoldChange"

    p <- ggplot(df, aes(x = x_plot, y = fc))

    # Background columns (white fill behind each group)
    p <- p +
      geom_col(data = back_data,
               aes(x = x_num, y = ymin),
               fill = "white", inherit.aes = FALSE) +
      geom_col(data = back_data,
               aes(x = x_num, y = ymax),
               fill = "white", inherit.aes = FALSE)

    # Significant points: black outline layer
    if (any(df$is_sig)) {
      sig_df <- df[df$is_sig, , drop = FALSE]
      p <- p + geom_point(data = sig_df,
                          aes(x = x_plot, y = fc),
                          color = "black", size = 1.8, alpha = 0.8,
                          inherit.aes = FALSE)
    }

    # All points colored by FC
    p <- p + geom_point(aes(color = fc_clipped), size = 1, alpha = 0.7) +
      scale_color_gradient2(
        low = "#4575B4", mid = "white", high = "#D73027",
        midpoint = 0, limits = fc_lim, name = "log2FC",
        guide = guide_colorbar(frame.colour = "black",
                               ticks.colour = "black")
      )

    # Tile color bar at y = 0
    p <- p +
      geom_tile(data = tile_data,
                aes(x = x, y = y, fill = group),
                color = "black", height = 0.5,
                show.legend = FALSE, inherit.aes = FALSE) +
      scale_fill_manual(values = tile_colors) +
      geom_text(data = tile_data,
                aes(x = x, y = y, label = group),
                inherit.aes = FALSE, size = 3, color = "black")

    # Gene labels
    if (requireNamespace("ggrepel", quietly = TRUE)) {
      p <- p + ggrepel::geom_text_repel(
        data = label_df,
        aes(x = x_plot, y = fc, label = gene_name),
        inherit.aes = FALSE,
        size = 3, max.overlaps = 50,
        min.segment.length = 0,
        segment.colour = "grey40",
        color = "black", bg.color = "white", bg.r = 0.1,
        force = 20
      )
    } else {
      p <- p + geom_text(data = label_df,
                         aes(x = x_plot, y = fc, label = gene_name),
                         inherit.aes = FALSE, size = 2.5,
                         nudge_y = 0.3, color = "black")
    }

    p <- p +
      scale_x_continuous(breaks = seq_len(n_groups),
                         labels = levels(df$group)) +
      scale_y_continuous(n.breaks = 6) +
      labs(x = NULL, y = fc_label) +
      theme_omics() +
      theme(panel.grid = element_blank(),
            panel.border = element_blank(),
            axis.line.x = element_blank(),
            axis.line.y = element_line(),
            axis.text.x = element_blank(),
            axis.ticks.x = element_blank())

    fig_w <- max(7, n_groups * 1.8 + 2)
    fig_h <- 7
    ggsave_standard(p, out_path, width = fig_w, height = fig_h)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
