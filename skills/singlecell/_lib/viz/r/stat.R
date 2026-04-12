# stat.R -- FeatureStatPlot and CellStatPlot renderers for OmicsClaw R Enhanced
# Reads: figure_data/ CSVs with expression or count data
# Provides: plot_feature_violin, plot_feature_boxplot, plot_cell_barplot
# Registered in: registry.R

# ---- Function 1: plot_feature_violin ----

#' Violin + jitter plot for gene expression across groups.
#'
#' Reads markers_top.csv or de_top_markers.csv from figure_data/.
#' Shows top N genes × groups as faceted violin plots.
#'
#' @param data_dir Character. figure_data/ directory.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: n_genes (default 6), group_col.
plot_feature_violin <- function(data_dir, out_path, params) {
  tryCatch({
    # Try multiple CSV sources
    candidates <- c("gene_expression.csv", "markers_top.csv", "de_top_markers.csv")
    csv_path <- NULL
    for (f in candidates) {
      p <- file.path(data_dir, f)
      if (file.exists(p)) { csv_path <- p; break }
    }
    if (is.null(csv_path)) {
      stop("No expression CSV found. Expected: ", paste(candidates, collapse=", "))
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # Detect format: long (cell_id, gene, expression) vs wide summary
    if (all(c("cell_id", "gene", "expression") %in% colnames(df))) {
      # Long format from pseudotime/pathway-scoring
      n_genes <- as.integer(params[["n_genes"]] %||% 6)
      top_genes <- head(unique(df$gene), n_genes)
      df <- df[df$gene %in% top_genes, ]
      df$gene <- factor(df$gene, levels = top_genes)

      # Try to get group info from embedding CSV
      embed_csv <- file.path(data_dir, "annotation_embedding_points.csv")
      if (!file.exists(embed_csv)) {
        embed_csv <- file.path(data_dir, "pseudotime_points.csv")
      }
      if (file.exists(embed_csv)) {
        embed <- read.csv(embed_csv, stringsAsFactors = FALSE)
        group_col <- intersect(c("cell_type", "group", "cluster", "leiden", "louvain"),
                               colnames(embed))
        if (length(group_col) > 0) {
          embed_merge <- embed[, c("cell_id", group_col[1]), drop = FALSE]
          colnames(embed_merge)[2] <- "group"
          df <- merge(df, embed_merge, by = "cell_id", all.x = TRUE)
        } else {
          df$group <- "All"
        }
      } else {
        df$group <- "All"
      }

      p <- ggplot(df, aes(x = group, y = expression, fill = group)) +
        geom_violin(scale = "width", trim = TRUE, alpha = 0.7, linewidth = 0.3) +
        geom_jitter(width = 0.15, size = 0.3, alpha = 0.3, color = "grey30") +
        stat_summary(fun = median, geom = "point", shape = 21,
                     size = 2, fill = "white", color = "black") +
        facet_wrap(~ gene, scales = "free_y", ncol = 3) +
        scale_fill_manual(values = omics_palette(length(unique(df$group)))) +
        labs(x = "", y = "Expression", title = "Feature expression by group") +
        theme_omics() +
        theme(axis.text.x = element_text(angle = 45, hjust = 1),
              legend.position = "none",
              strip.text = element_text(face = "italic"))

      n_genes_actual <- length(unique(df$gene))
      n_rows <- ceiling(n_genes_actual / 3)
      ggsave_standard(p, out_path, width = 10, height = max(4, n_rows * 3))

    } else if (all(c("group", "names", "scores") %in% colnames(df))) {
      # Summary format from markers/DE — create a dotplot instead
      n_genes <- as.integer(params[["n_genes"]] %||% 5)
      # Take top N per group
      groups <- unique(df$group)
      top_df <- do.call(rbind, lapply(groups, function(g) {
        sub <- df[df$group == g, ]
        head(sub[order(-abs(sub$scores)), ], n_genes)
      }))
      top_df$names <- factor(top_df$names, levels = rev(unique(top_df$names)))
      top_df$group <- factor(top_df$group, levels = groups)
      top_df$neg_log10_padj <- pmin(-log10(top_df$pvals_adj + 1e-300), 50)

      p <- ggplot(top_df, aes(x = group, y = names)) +
        geom_point(aes(size = neg_log10_padj, fill = scores),
                   shape = 21, color = "black", stroke = 0.3) +
        scale_fill_gradient2(low = "#2166AC", mid = "white", high = "#B2182B",
                             midpoint = 0, name = "Score") +
        scale_size_continuous(range = c(2, 7), name = "-log10(padj)") +
        labs(x = "", y = "", title = "Top marker genes") +
        theme_omics() +
        theme(axis.text.x = element_text(angle = 45, hjust = 1))

      n_uniq <- length(unique(top_df$names))
      ggsave_standard(p, out_path,
                      width = max(5, length(groups) * 0.8 + 3),
                      height = max(4, n_uniq * 0.3 + 2))
    } else {
      stop("Unrecognized CSV format. Columns: ", paste(colnames(df), collapse=", "))
    }

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 2: plot_feature_boxplot ----

#' Boxplot variant of feature expression.
#'
#' Same data sources as plot_feature_violin but renders as boxplots.
#'
#' @param data_dir Character. figure_data/ directory.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: n_genes (default 6).
plot_feature_boxplot <- function(data_dir, out_path, params) {
  tryCatch({
    candidates <- c("gene_expression.csv", "markers_top.csv", "de_top_markers.csv")
    csv_path <- NULL
    for (f in candidates) {
      p <- file.path(data_dir, f)
      if (file.exists(p)) { csv_path <- p; break }
    }
    if (is.null(csv_path)) {
      stop("No expression CSV found. Expected: ", paste(candidates, collapse=", "))
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    if (all(c("cell_id", "gene", "expression") %in% colnames(df))) {
      n_genes <- as.integer(params[["n_genes"]] %||% 6)
      top_genes <- head(unique(df$gene), n_genes)
      df <- df[df$gene %in% top_genes, ]
      df$gene <- factor(df$gene, levels = top_genes)

      # Try group info
      embed_csv <- file.path(data_dir, "annotation_embedding_points.csv")
      if (!file.exists(embed_csv)) embed_csv <- file.path(data_dir, "pseudotime_points.csv")
      if (file.exists(embed_csv)) {
        embed <- read.csv(embed_csv, stringsAsFactors = FALSE)
        group_col <- intersect(c("cell_type", "group", "cluster", "leiden", "louvain"),
                               colnames(embed))
        if (length(group_col) > 0) {
          embed_merge <- embed[, c("cell_id", group_col[1]), drop = FALSE]
          colnames(embed_merge)[2] <- "group"
          df <- merge(df, embed_merge, by = "cell_id", all.x = TRUE)
        } else {
          df$group <- "All"
        }
      } else {
        df$group <- "All"
      }

      p <- ggplot(df, aes(x = group, y = expression, fill = group)) +
        geom_boxplot(outlier.size = 0.3, outlier.alpha = 0.3, linewidth = 0.4) +
        stat_summary(fun = mean, geom = "point", shape = 23,
                     size = 2, fill = "red", color = "black") +
        facet_wrap(~ gene, scales = "free_y", ncol = 3) +
        scale_fill_manual(values = omics_palette(length(unique(df$group)))) +
        labs(x = "", y = "Expression", title = "Feature expression by group") +
        theme_omics() +
        theme(axis.text.x = element_text(angle = 45, hjust = 1),
              legend.position = "none",
              strip.text = element_text(face = "italic"))

      n_genes_actual <- length(unique(df$gene))
      n_rows <- ceiling(n_genes_actual / 3)
      ggsave_standard(p, out_path, width = 10, height = max(4, n_rows * 3))
    } else {
      # Fallback to violin for summary data
      plot_feature_violin(data_dir, out_path, params)
    }

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 3: plot_cell_barplot ----

#' Stacked or dodged bar chart for cell-type composition.
#'
#' Reads cell_type_counts.csv, sample_by_celltype_counts.csv,
#' or annotation_summary.csv from figure_data/.
#'
#' @param data_dir Character. figure_data/ directory.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: position ("stack" or "dodge", default "stack").
plot_cell_barplot <- function(data_dir, out_path, params) {
  tryCatch({
    position <- params[["position"]] %||% "stack"

    # Try multiple CSV sources
    ct_csv <- file.path(data_dir, "cell_type_counts.csv")
    sample_csv <- file.path(data_dir, "sample_by_celltype_proportions.csv")
    annot_csv <- file.path(data_dir, "annotation_summary.csv")

    if (file.exists(sample_csv)) {
      # Multi-sample: rows = samples, cols = cell types
      df <- read.csv(sample_csv, stringsAsFactors = FALSE, check.names = FALSE)
      id_col <- colnames(df)[1]
      long_df <- reshape(df, direction = "long",
                         varying = colnames(df)[-1],
                         v.names = "proportion",
                         timevar = "cell_type",
                         times = colnames(df)[-1],
                         idvar = id_col)
      long_df$sample <- long_df[[id_col]]
      n_types <- length(unique(long_df$cell_type))
      pal <- omics_palette(n_types)

      p <- ggplot(long_df, aes(x = sample, y = proportion, fill = cell_type)) +
        geom_col(position = position, color = "white", linewidth = 0.2) +
        scale_fill_manual(values = pal, name = "Cell type") +
        scale_y_continuous(labels = scales::percent_format(scale = 100),
                           expand = expansion(0, 0)) +
        labs(x = "", y = "Proportion", title = "Cell-type composition") +
        theme_omics() +
        theme(axis.text.x = element_text(angle = 45, hjust = 1))

      ggsave_standard(p, out_path,
                      width = max(6, length(unique(long_df$sample)) * 0.8 + 3),
                      height = 6)

    } else if (file.exists(ct_csv)) {
      # Single sample: cell_type, n_cells, proportion_pct
      df <- read.csv(ct_csv, stringsAsFactors = FALSE)
      df <- df[order(-df$n_cells), ]
      df$cell_type <- factor(df$cell_type, levels = df$cell_type)
      n_types <- nrow(df)
      pal <- omics_palette(n_types)

      p <- ggplot(df, aes(x = cell_type, y = n_cells, fill = cell_type)) +
        geom_col(color = "black", linewidth = 0.3) +
        geom_text(aes(label = paste0(round(proportion_pct, 1), "%")),
                  vjust = -0.3, size = 3) +
        scale_fill_manual(values = pal) +
        scale_y_continuous(expand = expansion(mult = c(0, 0.1))) +
        labs(x = "", y = "Number of cells",
             title = "Cell-type composition") +
        theme_omics() +
        theme(axis.text.x = element_text(angle = 45, hjust = 1),
              legend.position = "none")

      ggsave_standard(p, out_path, width = max(6, n_types * 0.7 + 2), height = 5)

    } else if (file.exists(annot_csv)) {
      df <- read.csv(annot_csv, stringsAsFactors = FALSE)
      # Try to find cell_type and count columns
      ct_col <- intersect(c("cell_type", "annotation", "label"), colnames(df))[1]
      n_col <- intersect(c("n_cells", "count", "n"), colnames(df))[1]
      if (!is.na(ct_col) && !is.na(n_col)) {
        df <- df[order(-df[[n_col]]), ]
        df[[ct_col]] <- factor(df[[ct_col]], levels = df[[ct_col]])
        pal <- omics_palette(nrow(df))

        p <- ggplot(df, aes(x = .data[[ct_col]], y = .data[[n_col]],
                            fill = .data[[ct_col]])) +
          geom_col(color = "black", linewidth = 0.3) +
          scale_fill_manual(values = pal) +
          scale_y_continuous(expand = expansion(mult = c(0, 0.1))) +
          labs(x = "", y = "Count", title = "Cell-type composition") +
          theme_omics() +
          theme(axis.text.x = element_text(angle = 45, hjust = 1),
                legend.position = "none")

        ggsave_standard(p, out_path, width = max(6, nrow(df) * 0.7 + 2), height = 5)
      } else {
        stop("annotation_summary.csv missing expected columns")
      }
    } else {
      stop("No composition CSV found in ", data_dir)
    }

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 4: plot_cell_proportion ----

#' Proportion pie/donut for cell-type composition.
#'
#' @param data_dir Character. figure_data/ directory.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: style ("pie" or "donut", default "donut").
plot_cell_proportion <- function(data_dir, out_path, params) {
  tryCatch({
    style <- params[["style"]] %||% "donut"

    ct_csv <- file.path(data_dir, "cell_type_counts.csv")
    if (!file.exists(ct_csv)) {
      stop("cell_type_counts.csv not found in ", data_dir)
    }

    df <- read.csv(ct_csv, stringsAsFactors = FALSE)
    df <- df[order(-df$n_cells), ]
    df$cell_type <- factor(df$cell_type, levels = rev(df$cell_type))
    n_types <- nrow(df)
    pal <- omics_palette(n_types)

    # Compute label positions
    df$prop <- df$n_cells / sum(df$n_cells)
    df$ymax <- cumsum(df$prop)
    df$ymin <- c(0, head(df$ymax, -1))
    df$ymid <- (df$ymin + df$ymax) / 2
    df$label <- paste0(rev(levels(df$cell_type)), "\n",
                       round(df$prop * 100, 1), "%")

    p <- ggplot(df, aes(ymax = ymax, ymin = ymin, xmax = 4, xmin = 3,
                        fill = cell_type)) +
      geom_rect(color = "white", linewidth = 0.5) +
      geom_text(aes(x = 4.5, y = ymid, label = label),
                size = 2.8, hjust = 0) +
      scale_fill_manual(values = rev(pal)) +
      coord_polar(theta = "y") +
      theme_void() +
      theme(legend.position = "none",
            plot.title = element_text(hjust = 0.5, face = "bold")) +
      labs(title = "Cell-type composition")

    if (style == "donut") {
      p <- p + xlim(c(1.5, 5.5))
    } else {
      p <- p + xlim(c(0, 5.5))
    }

    ggsave_standard(p, out_path, width = 8, height = 7)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 5: plot_proportion_test ----

#' Pointrange plot for proportion test results with FDR annotation.
#'
#' Reads proportion_test_results.csv from figure_data/.
#' Shows observed log2 fold difference per cell type with bootstrap CI
#' and significance coloring based on FDR threshold.
#'
#' Adapted from scop ProportionTestPlot.R pattern.
#'
#' @param data_dir Character. figure_data/ directory.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: FDR_threshold (default 0.05),
#'   fold_threshold (default 1.5, used as log2(fold_threshold)).
plot_proportion_test <- function(data_dir, out_path, params) {
  tryCatch({
    # ---- 1. Read CSV ----
    csv_path <- file.path(data_dir, "proportion_test_results.csv")
    if (!file.exists(csv_path)) {
      stop("proportion_test_results.csv not found in ", data_dir)
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) stop("proportion_test_results.csv is empty")

    # ---- 2. Validate required columns ----
    required_cols <- c("clusters", "obs_log2FD", "boot_CI_2.5", "boot_CI_97.5", "FDR")
    missing_cols <- setdiff(required_cols, colnames(df))
    if (length(missing_cols) > 0) {
      stop("Missing required columns: ", paste(missing_cols, collapse = ", "),
           ". Available: ", paste(colnames(df), collapse = ", "))
    }

    # ---- 3. Compute significance ----
    FDR_threshold <- as.numeric(params[["FDR_threshold"]] %||% 0.05)
    fold_threshold <- as.numeric(params[["fold_threshold"]] %||% 1.5)
    log2FD_threshold <- log2(fold_threshold)

    df$significance <- ifelse(
      df$FDR < FDR_threshold & abs(df$obs_log2FD) > log2FD_threshold,
      "Significant", "n.s."
    )
    df$significance <- factor(df$significance,
                              levels = c("Significant", "n.s."))

    # Order clusters by obs_log2FD (descending)
    cluster_order <- df$clusters[order(df$obs_log2FD, decreasing = TRUE)]
    # Handle duplicate cluster names (from multiple comparisons)
    cluster_order <- unique(cluster_order)
    df$clusters <- factor(df$clusters, levels = cluster_order)

    # ---- 4. Build plot ----
    p <- ggplot(df, aes(x = clusters, y = obs_log2FD)) +
      geom_pointrange(
        aes(ymin = boot_CI_2.5, ymax = boot_CI_97.5, color = significance),
        size = 0.8
      ) +
      geom_hline(yintercept = log2FD_threshold,
                 linetype = "dashed", color = "grey50") +
      geom_hline(yintercept = -log2FD_threshold,
                 linetype = "dashed", color = "grey50") +
      geom_hline(yintercept = 0, color = "black") +
      scale_color_manual(
        name = "Significance",
        values = c("Significant" = "#E41A1C", "n.s." = "grey60")
      ) +
      coord_flip() +
      labs(x = "Cell Type", y = "log2(Fold Difference)",
           title = "Proportion Test") +
      theme_omics() +
      theme(legend.position = "bottom")

    # Add subtitle if comparison info is available
    if ("comparison" %in% colnames(df)) {
      comparisons <- unique(df$comparison)
      if (length(comparisons) == 1) {
        p <- p + labs(subtitle = comparisons[1])
      }
    } else if (all(c("group1", "group2") %in% colnames(df))) {
      g1 <- unique(df$group1)[1]
      g2 <- unique(df$group2)[1]
      p <- p + labs(subtitle = paste0(g2, " vs ", g1))
    }

    # Dynamic sizing
    n_clusters <- length(unique(df$clusters))
    plot_width <- max(6, n_clusters * 0.5 + 2)
    ggsave_standard(p, out_path, width = 7, height = plot_width)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
