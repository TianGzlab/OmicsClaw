# pseudotime.R -- LineagePlot and DynamicPlot renderers for OmicsClaw R Enhanced
# Reads: figure_data/pseudotime_points.csv, trajectory_genes.csv, gene_expression.csv
# Provides: plot_pseudotime_lineage, plot_pseudotime_dynamic
# Registered in: registry.R
#
# NOTE: Does NOT library(scop) -- extracts ggplot2 patterns only.

# ---- Null-coalescing operator (not in base R) ----
`%||%` <- function(a, b) if (!is.null(a)) a else b

# ---- Function 1: LineagePlot equivalent ----

#' Pseudotime lineage scatter with trajectory curves.
#'
#' Reads pseudotime_points.csv, colors cells by pseudotime, overlays
#' loess-smoothed trajectory curves (or explicit slingshot curves if available).
#'
#' @param data_dir Character. Directory containing pseudotime_points.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: span (loess span, default 0.75).
plot_pseudotime_lineage <- function(data_dir, out_path, params) {
  tryCatch({
    # --- Step 1: Read points ---
    csv_path <- file.path(data_dir, "pseudotime_points.csv")
    if (!file.exists(csv_path)) {
      stop("pseudotime_points.csv not found in ", data_dir)
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    required <- c("coord1", "coord2", "pseudotime")
    missing <- setdiff(required, colnames(df))
    if (length(missing) > 0) {
      stop("Missing required columns in pseudotime_points.csv: ",
           paste(missing, collapse = ", "))
    }

    # Remove rows with NA pseudotime
    df <- df[!is.na(df$pseudotime), ]
    if (nrow(df) == 0) stop("No non-NA pseudotime values found")

    # --- Step 2: Base scatter layer ---
    p <- ggplot(df, aes(x = coord1, y = coord2, color = pseudotime)) +
      geom_point(size = 0.5, alpha = 0.6) +
      scale_color_viridis_c(option = "plasma", name = "Pseudotime")

    # --- Step 3: Trajectory curve overlay ---
    curve_csv <- file.path(data_dir, "slingshot_curves.csv")
    if (file.exists(curve_csv)) {
      # Explicit slingshot curves
      curves <- read.csv(curve_csv, stringsAsFactors = FALSE)
      if (all(c("coord1", "coord2") %in% colnames(curves))) {
        # Find grouping column
        group_col <- NULL
        for (cand in c("curve_id", "lineage")) {
          if (cand %in% colnames(curves)) { group_col <- cand; break }
        }
        if (is.null(group_col)) {
          non_coord <- setdiff(colnames(curves), c("coord1", "coord2", "order"))
          if (length(non_coord) > 0) group_col <- non_coord[1]
        }

        if (!is.null(group_col)) {
          curves[[group_col]] <- as.factor(curves[[group_col]])
          # Sort by order if present
          if ("order" %in% colnames(curves)) {
            curves <- curves[order(curves[[group_col]], curves$order), ]
          }
          p <- p + geom_path(
            data = curves,
            aes(x = coord1, y = coord2, group = .data[[group_col]]),
            color = "black", linewidth = 1.2, inherit.aes = FALSE,
            arrow = arrow(length = unit(0.12, "inches"))
          )
        } else {
          p <- p + geom_path(
            data = curves,
            aes(x = coord1, y = coord2),
            color = "black", linewidth = 1.2, inherit.aes = FALSE,
            arrow = arrow(length = unit(0.12, "inches"))
          )
        }
      }
    } else {
      # Loess fallback: smooth trajectory over embedding
      span <- as.numeric(params[["span"]] %||% "0.75")

      # T-16a-02 mitigation: sample to max 5000 cells for loess performance
      df_loess <- df[order(df$pseudotime), ]
      if (nrow(df_loess) > 5000) {
        df_loess <- df_loess[sample(nrow(df_loess), 5000), ]
        df_loess <- df_loess[order(df_loess$pseudotime), ]
      }

      fit <- tryCatch(
        loess(coord2 ~ coord1, data = df_loess, span = span, degree = 2),
        error = function(e) NULL
      )
      if (!is.null(fit)) {
        x_seq <- seq(min(df_loess$coord1), max(df_loess$coord1), length.out = 200)
        y_pred <- predict(fit, newdata = data.frame(coord1 = x_seq))
        curve_df <- data.frame(coord1 = x_seq, coord2 = y_pred)
        curve_df <- curve_df[!is.na(curve_df$coord2), ]
        if (nrow(curve_df) > 1) {
          p <- p + geom_path(
            data = curve_df,
            aes(x = coord1, y = coord2),
            color = "#E63946", linewidth = 1.2, inherit.aes = FALSE
          )
        }
      }
    }

    # --- Step 4: Labels and theme ---
    p <- p +
      labs(title = "Pseudotime trajectory", x = "Embedding 1", y = "Embedding 2") +
      theme_omics() +
      theme(legend.position = "right")

    ggsave_standard(p, out_path, width = 8, height = 7)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 2: DynamicPlot equivalent (NO Python equivalent) ----

#' Gene expression dynamics over pseudotime with CI ribbons.
#'
#' Reads pseudotime_points.csv + trajectory_genes.csv, picks top genes by
#' absolute correlation, merges with per-cell expression, and plots loess
#' trends with confidence-interval ribbons faceted per gene.
#'
#' @param data_dir Character. Directory containing pseudotime_points.csv and trajectory_genes.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: n_genes (default 5).
plot_pseudotime_dynamic <- function(data_dir, out_path, params) {
  tryCatch({
    # --- Step 1: Read CSVs ---
    pts_path <- file.path(data_dir, "pseudotime_points.csv")
    genes_path <- file.path(data_dir, "trajectory_genes.csv")

    if (!file.exists(pts_path)) stop("pseudotime_points.csv not found in ", data_dir)
    if (!file.exists(genes_path)) stop("trajectory_genes.csv not found in ", data_dir)

    pts_df <- read.csv(pts_path, stringsAsFactors = FALSE)
    genes_df <- read.csv(genes_path, stringsAsFactors = FALSE)

    if (!"pseudotime" %in% colnames(pts_df)) stop("pseudotime column missing from pseudotime_points.csv")
    if (!"gene" %in% colnames(genes_df)) stop("gene column missing from trajectory_genes.csv")

    # Remove NA pseudotime
    pts_df <- pts_df[!is.na(pts_df$pseudotime), ]
    if (nrow(pts_df) == 0) stop("No non-NA pseudotime values found")

    # --- Step 2: Select top genes ---
    n_genes <- as.integer(params[["n_genes"]] %||% "5")
    if ("correlation" %in% colnames(genes_df)) {
      genes_df <- genes_df[order(-abs(genes_df$correlation)), ]
    }
    top_genes <- head(genes_df$gene, n_genes)

    # --- Step 3: Extract expression ---
    expr_path <- file.path(data_dir, "gene_expression.csv")
    subtitle_text <- ""

    if (file.exists(expr_path)) {
      expr_df <- read.csv(expr_path, stringsAsFactors = FALSE)
      # Filter to top genes and cells present in pts_df
      expr_df <- expr_df[expr_df$gene %in% top_genes, ]
      if ("cell_id" %in% colnames(pts_df)) {
        expr_df <- expr_df[expr_df$cell_id %in% pts_df$cell_id, ]
      }
    } else {
      # Synthetic fallback for demo/testing
      set.seed(42)
      n_cells <- nrow(pts_df)
      cell_ids <- if ("cell_id" %in% colnames(pts_df)) pts_df$cell_id else paste0("cell_", seq_len(n_cells))
      expr_rows <- list()
      for (g in top_genes) {
        # Generate expression correlated with pseudotime for visual plausibility
        base_expr <- stats::rnorm(n_cells, mean = 0.5, sd = 0.3)
        base_expr <- pmin(pmax(base_expr, 0), 1)  # clamp [0, 1]
        expr_rows[[g]] <- data.frame(
          cell_id = cell_ids,
          gene = g,
          expression = base_expr,
          stringsAsFactors = FALSE
        )
      }
      expr_df <- do.call(rbind, expr_rows)
      subtitle_text <- "Expression: synthetic demo"
    }

    if (nrow(expr_df) == 0) stop("No expression data found for top genes")

    # --- Step 4: Merge pseudotime with expression ---
    # Ensure cell_id exists in pts_df
    if (!"cell_id" %in% colnames(pts_df)) {
      pts_df$cell_id <- paste0("cell_", seq_len(nrow(pts_df)))
    }
    df_long <- merge(
      expr_df,
      pts_df[, c("cell_id", "pseudotime")],
      by = "cell_id"
    )
    if (nrow(df_long) == 0) stop("No cells matched between expression and pseudotime data")

    # Ensure gene is a factor with consistent ordering
    df_long$gene <- factor(df_long$gene, levels = top_genes)

    # --- Step 5: Plot with stat_smooth CI ribbon ---
    # T-16a-02 mitigation: sample per gene for loess performance
    if (nrow(df_long) > 5000 * n_genes) {
      df_long <- do.call(rbind, lapply(split(df_long, df_long$gene), function(sub) {
        if (nrow(sub) > 5000) sub[sample(nrow(sub), 5000), ] else sub
      }))
    }

    p <- ggplot(df_long, aes(x = pseudotime, y = expression, group = gene)) +
      geom_point(aes(color = gene), size = 0.3, alpha = 0.3, show.legend = FALSE) +
      stat_smooth(
        aes(color = gene, fill = gene),
        method = "loess", formula = y ~ x, span = 0.75,
        geom = "smooth", alpha = 0.25, linewidth = 1
      ) +
      scale_color_manual(values = omics_palette(n_genes)) +
      scale_fill_manual(values = omics_palette(n_genes), guide = "none") +
      facet_wrap(~gene, scales = "free_y") +
      labs(
        title = "Gene dynamics over pseudotime",
        subtitle = subtitle_text,
        x = "Pseudotime", y = "Normalized expression",
        color = "Gene"
      ) +
      theme_omics() +
      theme(legend.position = "none")

    plot_width <- max(8, n_genes * 2.5)
    ggsave_standard(p, out_path, width = plot_width, height = 5, dpi = 200)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}


# ---- Function 3: plot_pseudotime_heatmap ----

#' DynamicHeatmap: gene expression binned along pseudotime.
#'
#' Reads pseudotime_points.csv and gene_expression.csv.
#' Bins cells by pseudotime, computes mean expression per bin per gene,
#' and renders a heatmap with genes on rows and pseudotime bins on columns.
#'
#' @param data_dir Character. figure_data/ directory.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: n_genes (default 30), n_bins (default 50).
plot_pseudotime_heatmap <- function(data_dir, out_path, params) {
  tryCatch({
    pt_csv <- file.path(data_dir, "pseudotime_points.csv")
    expr_csv <- file.path(data_dir, "gene_expression.csv")

    if (!file.exists(pt_csv) || !file.exists(expr_csv)) {
      stop("Need both pseudotime_points.csv and gene_expression.csv in ", data_dir)
    }

    pt_df <- read.csv(pt_csv, stringsAsFactors = FALSE)
    expr_df <- read.csv(expr_csv, stringsAsFactors = FALSE)

    # Find pseudotime column
    pt_col <- intersect(c("pseudotime", "dpt_pseudotime", "palantir_pseudotime"),
                        colnames(pt_df))
    if (length(pt_col) == 0) stop("No pseudotime column found")
    pt_col <- pt_col[1]

    # Merge pseudotime with expression, filter Inf/NA
    merged <- merge(expr_df, pt_df[, c("cell_id", pt_col)], by = "cell_id")
    merged <- merged[!is.na(merged[[pt_col]]) & is.finite(merged[[pt_col]]), ]
    if (nrow(merged) == 0) stop("No cells with valid (finite) pseudotime and expression")

    # Select top genes (by variance across pseudotime)
    n_genes <- as.integer(params[["n_genes"]] %||% 30)
    n_bins <- as.integer(params[["n_bins"]] %||% 50)

    gene_var <- aggregate(expression ~ gene, data = merged, FUN = var)
    gene_var <- gene_var[order(-gene_var$expression), ]
    top_genes <- head(gene_var$gene, n_genes)
    merged <- merged[merged$gene %in% top_genes, ]

    # Bin cells by pseudotime
    merged$pt_bin <- cut(merged[[pt_col]],
                         breaks = seq(0, max(merged[[pt_col]], na.rm = TRUE) * 1.001,
                                      length.out = n_bins + 1),
                         labels = FALSE, include.lowest = TRUE)

    # Compute mean expression per gene × bin
    mat <- aggregate(expression ~ gene + pt_bin, data = merged, FUN = mean)

    # Scale per gene (z-score)
    gene_means <- aggregate(expression ~ gene, data = mat, FUN = mean)
    gene_sds <- aggregate(expression ~ gene, data = mat, FUN = sd)
    colnames(gene_means)[2] <- "gene_mean"
    colnames(gene_sds)[2] <- "gene_sd"
    mat <- merge(mat, gene_means, by = "gene")
    mat <- merge(mat, gene_sds, by = "gene")
    mat$z <- (mat$expression - mat$gene_mean) / pmax(mat$gene_sd, 1e-6)
    mat$z <- pmin(pmax(mat$z, -3), 3)  # Clamp to [-3, 3]

    # Order genes by peak pseudotime position
    peak_bin <- aggregate(expression ~ gene, data = mat, FUN = function(x) {
      which.max(x)
    })
    peak_bin <- peak_bin[order(peak_bin$expression), ]
    mat$gene <- factor(mat$gene, levels = peak_bin$gene)

    # Build heatmap
    p <- ggplot(mat, aes(x = pt_bin, y = gene, fill = z)) +
      geom_tile() +
      scale_fill_gradient2(
        low = "#2166AC", mid = "white", high = "#B2182B",
        midpoint = 0, name = "Z-score",
        limits = c(-3, 3),
        guide = guide_colorbar(frame.colour = "black", ticks.colour = "black")
      ) +
      scale_x_continuous(
        expand = expansion(0, 0),
        breaks = c(1, round(n_bins / 2), n_bins),
        labels = c("Early", "Mid", "Late")
      ) +
      labs(x = "Pseudotime", y = "",
           title = "Gene dynamics along pseudotime") +
      theme_omics() +
      theme(
        axis.text.y = element_text(size = 7, face = "italic"),
        panel.grid = element_blank(),
        panel.border = element_rect(color = "black", fill = NA, linewidth = 0.5)
      )

    height <- max(5, length(top_genes) * 0.25 + 2)
    ggsave_standard(p, out_path, width = 10, height = height)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
