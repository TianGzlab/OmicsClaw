# enrichment.R -- EnrichmentPlot bar, GSEAPlot mountain, GSEAPlot NES heatmap
# for OmicsClaw R Enhanced plotting
#
# Reads: figure_data/top_terms.csv, gsea_running_scores.csv, enrichment_results.csv
# Provides: plot_enrichment_bar, plot_gsea_mountain, plot_gsea_nes_heatmap
# Registered in: registry.R

# Null-coalescing operator
`%||%` <- function(a, b) if (!is.null(a)) a else b

# ---------------------------------------------------------------------------
# Function 1: plot_enrichment_bar
# ---------------------------------------------------------------------------
#' Enrichment bar plot (EnrichmentPlot equivalent, SK-03).
#'
#' Horizontal bars ranked by -log10(pvalue_adj). Bar fill = NES if available,
#' otherwise a viridis gradient of -log10(padj). A dashed vertical line marks
#' the p = 0.05 significance threshold.
#'
#' @param data_dir Character. Directory containing top_terms.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: group (cell group), top_n (integer).
plot_enrichment_bar <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "top_terms.csv")
    if (!file.exists(csv_path)) {
      cat("ERROR: top_terms.csv not found in", data_dir, "\n", file = stderr())
      quit(status = 1)
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # Need at least pvalue_adj or pvalue
    if (!"pvalue_adj" %in% colnames(df) && !"pvalue" %in% colnames(df)) {
      stop("Neither pvalue_adj nor pvalue column found in top_terms.csv")
    }
    # Fallback: use pvalue if pvalue_adj missing
    if (!"pvalue_adj" %in% colnames(df)) {
      df$pvalue_adj <- df$pvalue
    }

    # Select group
    group_use <- params[["group"]]
    if ("group" %in% colnames(df)) {
      if (is.null(group_use) || !group_use %in% df$group) {
        group_use <- df$group[1]
      }
      df <- df[df$group == group_use, , drop = FALSE]
    } else {
      if (is.null(group_use)) group_use <- "all"
    }

    if (nrow(df) == 0) {
      cat("WARNING: No rows for group '", group_use, "'\n", sep = "", file = stderr())
      quit(status = 0)
    }

    # Compute -log10(padj)
    df$neg_log_padj <- -log10(as.numeric(df$pvalue_adj) + 1e-300)

    # Sort and take top N
    top_n <- as.integer(params[["top_n"]] %||% "20")
    df <- df[order(df$neg_log_padj, decreasing = TRUE), ]
    df <- head(df, top_n)

    # Truncate long term names
    df$term_short <- ifelse(nchar(df$term) > 50,
                            paste0(substr(df$term, 1, 47), "..."),
                            df$term)
    df$term_short <- factor(df$term_short, levels = rev(df$term_short))

    # Color by NES direction if available, otherwise by -log10(padj)
    if ("nes" %in% colnames(df) && !all(is.na(df$nes))) {
      df$nes <- as.numeric(df$nes)
      fill_col <- "nes"
      fill_scale <- scale_fill_gradient2(
        low = "#4575B4", mid = "white", high = "#D73027",
        midpoint = 0, name = "NES"
      )
    } else {
      df$fill_val <- df$neg_log_padj
      fill_col <- "fill_val"
      fill_scale <- scale_fill_viridis_c(option = "plasma", name = "-log10(padj)")
    }

    p <- ggplot(df, aes(x = neg_log_padj, y = term_short, fill = .data[[fill_col]])) +
      geom_bar(stat = "identity", width = 0.7) +
      geom_vline(xintercept = -log10(0.05), linetype = "dashed",
                 color = "grey50", linewidth = 0.4) +
      fill_scale +
      labs(
        title = paste0("Enrichment \u2014 ", group_use),
        x = "-log10(adj. p-value)", y = NULL
      ) +
      theme_omics() +
      theme(axis.text.y = element_text(size = 9))

    ggsave_standard(p, out_path, width = 10,
                    height = max(5, nrow(df) * 0.35 + 1.5))
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---------------------------------------------------------------------------
# Function 2: plot_gsea_mountain
# ---------------------------------------------------------------------------
#' Classic GSEA mountain plot (SK-04).
#'
#' Three-panel layout using patchwork if available:
#'   Panel 1: Running enrichment score line with ES peak marker
#'   Panel 2: Hit barcode (gene positions)
#'   Panel 3: Ranked metric profile
#' Falls back to single running-score panel if patchwork is not installed.
#'
#' @param data_dir Character. Directory containing gsea_running_scores.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: group, term.
plot_gsea_mountain <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "gsea_running_scores.csv")
    if (!file.exists(csv_path)) {
      cat("WARNING: gsea_running_scores.csv not found in ", data_dir,
          " (expected for ORA methods)\n", sep = "", file = stderr())
      quit(status = 0)
    }
    rs <- read.csv(csv_path, stringsAsFactors = FALSE)

    # Filter to requested group + term
    group_use <- params[["group"]] %||% rs$group[1]
    available_terms <- rs$term[rs$group == group_use]
    term_use <- params[["term"]] %||% available_terms[1]
    df <- rs[rs$group == group_use & rs$term == term_use, , drop = FALSE]

    if (nrow(df) == 0) {
      cat("WARNING: No data for group='", group_use, "', term='", term_use, "'\n",
          sep = "", file = stderr())
      quit(status = 0)
    }

    # Ensure numeric columns
    df$rank <- as.numeric(df$rank)
    df$running_score <- as.numeric(df$running_score)

    # Identify hit rows (non-empty gene)
    hit_rows <- df[!is.na(df$gene) & nzchar(df$gene), , drop = FALSE]

    # --- Panel 1: Running enrichment score ---
    # Find ES peak (max absolute score)
    curve_rows <- df[!is.na(df$running_score), , drop = FALSE]
    es_idx <- which.max(abs(curve_rows$running_score))
    es_row <- curve_rows[es_idx, , drop = FALSE]

    p1 <- ggplot(curve_rows, aes(x = rank, y = running_score)) +
      geom_line(color = "#6BB82D", linewidth = 1.2) +
      geom_hline(yintercept = 0, linetype = "dashed", color = "grey50") +
      geom_point(data = es_row, aes(x = rank, y = running_score),
                 color = "#D73027", size = 3) +
      labs(
        title = paste0("GSEA: ", term_use, " (", group_use, ")"),
        x = NULL, y = "Enrichment score"
      ) +
      theme_omics() +
      theme(axis.text.x = element_blank(), axis.ticks.x = element_blank())

    # --- Panel 2: Hit barcode ---
    p2 <- ggplot(hit_rows, aes(x = rank, xend = rank, y = 0, yend = 1)) +
      geom_segment(color = "#333333", linewidth = 0.4, alpha = 0.7) +
      scale_y_continuous(expand = c(0, 0)) +
      labs(x = NULL, y = NULL) +
      theme_omics() +
      theme(
        axis.text = element_blank(),
        axis.ticks = element_blank(),
        axis.line = element_blank(),
        panel.grid.major.y = element_blank()
      )

    # --- Panel 3: Ranked metric ---
    has_metric <- "metric" %in% colnames(df) &&
                  any(!is.na(suppressWarnings(as.numeric(df$metric))))
    if (has_metric) {
      metric_rows <- curve_rows
      metric_rows$metric <- as.numeric(metric_rows$metric)
      metric_rows <- metric_rows[!is.na(metric_rows$metric), , drop = FALSE]
    }

    if (has_metric && nrow(metric_rows) > 0) {
      p3 <- ggplot(metric_rows, aes(x = rank, y = metric)) +
        geom_line(color = "#4575B4", linewidth = 0.5) +
        geom_hline(yintercept = 0, linetype = "dashed", color = "grey50") +
        labs(x = "Gene rank", y = "Ranked metric") +
        theme_omics()
    } else {
      p3 <- NULL
    }

    # Combine panels with patchwork if available
    if (requireNamespace("patchwork", quietly = TRUE)) {
      if (!is.null(p3)) {
        p_combined <- patchwork::wrap_plots(p1, p2, p3,
                                            ncol = 1, heights = c(3, 1, 2))
      } else {
        p_combined <- patchwork::wrap_plots(p1, p2,
                                            ncol = 1, heights = c(3, 1))
      }
    } else {
      # Fallback: just the running score panel
      p_combined <- p1
    }

    ggsave_standard(p_combined, out_path, width = 9, height = 7)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---------------------------------------------------------------------------
# Function 3: plot_gsea_nes_heatmap
# ---------------------------------------------------------------------------
#' NES heatmap across cell groups (SK-05).
#'
#' Tile heatmap: terms as rows, groups as columns, diverging blue-white-red
#' color scale for NES values. Cell text shows NES rounded to 2 decimals.
#'
#' @param data_dir Character. Directory containing enrichment_results.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: padj_cutoff (numeric), top_n (integer).
plot_gsea_nes_heatmap <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "enrichment_results.csv")
    if (!file.exists(csv_path)) {
      cat("ERROR: enrichment_results.csv not found in", data_dir, "\n",
          file = stderr())
      quit(status = 1)
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # Filter to rows with non-NA NES
    if (!"nes" %in% colnames(df)) {
      cat("WARNING: No 'nes' column in enrichment_results.csv\n", file = stderr())
      quit(status = 0)
    }
    df$nes <- as.numeric(df$nes)
    df <- df[!is.na(df$nes), , drop = FALSE]
    if (nrow(df) == 0) {
      cat("WARNING: No non-NA NES values in enrichment_results.csv\n", file = stderr())
      quit(status = 0)
    }

    # Filter significant terms
    padj_cutoff <- as.numeric(params[["padj_cutoff"]] %||% "0.05")
    if ("pvalue_adj" %in% colnames(df) && !all(is.na(df$pvalue_adj))) {
      df_sig <- df[as.numeric(df$pvalue_adj) <= padj_cutoff, , drop = FALSE]
    } else if ("pvalue" %in% colnames(df) && !all(is.na(df$pvalue))) {
      df_sig <- df[as.numeric(df$pvalue) < 0.05, , drop = FALSE]
    } else {
      df_sig <- df
    }
    if (nrow(df_sig) == 0) df_sig <- df  # fall back to all if none significant

    # Select top N terms ranked by max(abs(nes)) across groups
    top_n <- as.integer(params[["top_n"]] %||% "25")
    term_max_nes <- aggregate(nes ~ term, data = df_sig, FUN = function(x) max(abs(x)))
    term_max_nes <- term_max_nes[order(term_max_nes$nes, decreasing = TRUE), ]
    top_terms <- head(term_max_nes$term, top_n)
    df_sig <- df_sig[df_sig$term %in% top_terms, , drop = FALSE]

    # Pivot to wide matrix (base R)
    term_group <- unique(df_sig[, c("term", "group", "nes"), drop = FALSE])
    groups <- unique(term_group$group)
    terms <- unique(term_group$term)
    # Order terms by max abs NES (same order as top_terms)
    terms <- top_terms[top_terms %in% terms]

    mat <- matrix(NA, nrow = length(terms), ncol = length(groups),
                  dimnames = list(terms, groups))
    for (i in seq_len(nrow(term_group))) {
      t_name <- term_group$term[i]
      g_name <- term_group$group[i]
      if (t_name %in% terms && g_name %in% groups) {
        mat[t_name, g_name] <- term_group$nes[i]
      }
    }

    # To long format for ggplot2
    df_long <- as.data.frame(as.table(mat))
    colnames(df_long) <- c("term", "group", "nes")
    df_long$nes <- as.numeric(df_long$nes)

    # Truncate long term names
    df_long$term_short <- ifelse(nchar(as.character(df_long$term)) > 50,
                                 paste0(substr(as.character(df_long$term), 1, 47), "..."),
                                 as.character(df_long$term))
    # Maintain order
    term_short_levels <- ifelse(nchar(terms) > 50,
                                paste0(substr(terms, 1, 47), "..."), terms)
    df_long$term_short <- factor(df_long$term_short,
                                 levels = rev(term_short_levels))

    p <- ggplot(df_long, aes(x = group, y = term_short, fill = nes)) +
      geom_tile(color = "white", linewidth = 0.3) +
      scale_fill_gradient2(
        low = "#4575B4", mid = "white", high = "#D73027",
        midpoint = 0, name = "NES", na.value = "#CCCCCC"
      ) +
      geom_text(aes(label = ifelse(is.na(nes), "", sprintf("%.2f", nes))),
                size = 2.5, color = "black") +
      labs(title = "GSEA NES across cell groups", x = NULL, y = NULL) +
      theme_omics() +
      theme(
        axis.text.x = element_text(angle = 45, hjust = 1, size = 9),
        axis.text.y = element_text(size = 8),
        panel.grid.major.y = element_blank()
      )

    height <- max(5, length(terms) * 0.3 + 2)
    width <- max(6, length(groups) * 1.2 + 3)
    ggsave_standard(p, out_path, width = width, height = height)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}


# ---------------------------------------------------------------------------
# Function 4: plot_enrichment_dotplot
# ---------------------------------------------------------------------------
#' Enrichment dotplot (size = gene count, color = -log10 padj).
#'
#' Reads enrichment_results.csv or top_terms.csv. Shows top terms per group
#' as a bubble chart: x = gene ratio, y = term, size = overlap count.
#'
#' @param data_dir Character. Directory containing enrichment CSVs.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: top_n (default 8), group.
plot_enrichment_dotplot <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "enrichment_results.csv")
    if (!file.exists(csv_path)) {
      csv_path <- file.path(data_dir, "top_terms.csv")
    }
    if (!file.exists(csv_path)) {
      stop("No enrichment CSV found in ", data_dir)
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    top_n <- as.integer(params[["top_n"]] %||% 8)

    # Standardize column names
    if ("pvalue_adj" %in% colnames(df) && !"p.adjust" %in% colnames(df)) {
      df$p.adjust <- df$pvalue_adj
    }
    if ("gene_count" %in% colnames(df) && !"Count" %in% colnames(df)) {
      df$Count <- df$gene_count
    }
    if ("overlap" %in% colnames(df) && !"GeneRatio" %in% colnames(df)) {
      # Parse overlap like "5/9"
      df$GeneRatio <- sapply(df$overlap, function(x) {
        sp <- strsplit(as.character(x), "/")[[1]]
        if (length(sp) == 2) as.numeric(sp[1]) / as.numeric(sp[2]) else NA
      })
      if (!"Count" %in% colnames(df)) {
        df$Count <- sapply(df$overlap, function(x) {
          sp <- strsplit(as.character(x), "/")[[1]]
          if (length(sp) >= 1) as.numeric(sp[1]) else NA
        })
      }
    }

    # Filter significant and take top N
    df <- df[!is.na(df$p.adjust) & df$p.adjust < 1, ]
    if (nrow(df) == 0) {
      cat("WARNING: No significant terms found\n", file = stderr())
      return(invisible(NULL))
    }

    # Select group if specified, otherwise use first or all
    if ("group" %in% colnames(df)) {
      group_use <- params[["group"]] %||% unique(df$group)[1]
      df <- df[df$group == group_use, ]
    }

    df <- head(df[order(df$p.adjust), ], top_n)
    df$neg_log10_padj <- -log10(df$p.adjust + 1e-300)
    df$term <- factor(df$term, levels = rev(df$term))

    has_ratio <- "GeneRatio" %in% colnames(df) && !all(is.na(df$GeneRatio))

    if (has_ratio) {
      p <- ggplot(df, aes(x = GeneRatio, y = term)) +
        geom_point(aes(size = Count, fill = neg_log10_padj),
                   shape = 21, color = "black", stroke = 0.3) +
        scale_fill_gradientn(
          name = "-log10(padj)",
          colours = c("#FEE8C8", "#FDBB84", "#E34A33"),
          guide = guide_colorbar(frame.colour = "black", ticks.colour = "black")
        ) +
        scale_size_continuous(range = c(3, 8), name = "Gene count",
                              breaks = scales::breaks_extended(n = 4)) +
        labs(x = "Gene ratio", y = "", title = "Enrichment dotplot") +
        theme_omics() +
        theme(panel.grid.major.x = element_line(colour = "grey85", linetype = 2))
    } else {
      p <- ggplot(df, aes(x = neg_log10_padj, y = term)) +
        geom_point(aes(size = Count, fill = neg_log10_padj),
                   shape = 21, color = "black", stroke = 0.3) +
        scale_fill_gradientn(
          name = "-log10(padj)",
          colours = c("#FEE8C8", "#FDBB84", "#E34A33"),
          guide = guide_colorbar(frame.colour = "black", ticks.colour = "black")
        ) +
        scale_size_continuous(range = c(3, 8), name = "Gene count") +
        labs(x = "-log10(adj. p-value)", y = "", title = "Enrichment dotplot") +
        theme_omics() +
        theme(panel.grid.major.x = element_line(colour = "grey85", linetype = 2))
    }

    height <- max(4, nrow(df) * 0.4 + 2)
    ggsave_standard(p, out_path, width = 8, height = height)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}


# ---------------------------------------------------------------------------
# Function 5: plot_enrichment_lollipop
# ---------------------------------------------------------------------------
#' Enrichment lollipop plot (stem = fold enrichment, dot = gene ratio).
#'
#' @param data_dir Character. Directory containing enrichment CSVs.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: top_n (default 10), group.
plot_enrichment_lollipop <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "enrichment_results.csv")
    if (!file.exists(csv_path)) {
      csv_path <- file.path(data_dir, "top_terms.csv")
    }
    if (!file.exists(csv_path)) {
      stop("No enrichment CSV found in ", data_dir)
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    top_n <- as.integer(params[["top_n"]] %||% 10)

    # Standardize columns
    if ("pvalue_adj" %in% colnames(df) && !"p.adjust" %in% colnames(df)) {
      df$p.adjust <- df$pvalue_adj
    }
    if ("score" %in% colnames(df) && !"odds_ratio" %in% colnames(df)) {
      df$odds_ratio <- df$score
    }

    df <- df[!is.na(df$p.adjust) & df$p.adjust < 1, ]
    if (nrow(df) == 0) {
      cat("WARNING: No significant terms\n", file = stderr())
      return(invisible(NULL))
    }

    if ("group" %in% colnames(df)) {
      group_use <- params[["group"]] %||% unique(df$group)[1]
      df <- df[df$group == group_use, ]
    }

    # Use odds_ratio or score as the stem length
    metric_col <- intersect(c("odds_ratio", "score", "nes"), colnames(df))
    if (length(metric_col) == 0) {
      df$metric <- -log10(df$p.adjust + 1e-300)
      metric_name <- "-log10(padj)"
    } else {
      df$metric <- as.numeric(df[[metric_col[1]]])
      metric_name <- metric_col[1]
    }

    df <- head(df[order(-abs(df$metric)), ], top_n)
    df$neg_log10_padj <- -log10(df$p.adjust + 1e-300)
    df$term <- factor(df$term, levels = df$term[order(df$metric)])

    p <- ggplot(df, aes(x = term, y = metric)) +
      geom_segment(aes(y = 0, xend = term, yend = metric),
                   color = "grey40", linewidth = 1.5) +
      geom_segment(aes(y = 0, xend = term, yend = metric, color = neg_log10_padj),
                   linewidth = 1) +
      geom_point(aes(fill = neg_log10_padj), size = 4,
                 shape = 21, color = "black", stroke = 0.3) +
      scale_fill_gradientn(
        name = "-log10(padj)",
        colours = c("#FEE8C8", "#FDBB84", "#E34A33"),
        aesthetics = c("colour", "fill"),
        guide = guide_colorbar(frame.colour = "black", ticks.colour = "black")
      ) +
      coord_flip() +
      labs(x = "", y = metric_name, title = "Enrichment lollipop") +
      theme_omics() +
      theme(panel.grid.major.y = element_blank(),
            panel.grid.major.x = element_line(colour = "grey85", linetype = 2))

    height <- max(4, nrow(df) * 0.35 + 2)
    ggsave_standard(p, out_path, width = 8, height = height)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}


# ---------------------------------------------------------------------------
# Function 6: plot_enrichment_network
# ---------------------------------------------------------------------------
#' Enrichment gene-term network graph (bipartite network).
#'
#' Visualises the relationship between enriched terms and their associated
#' genes as a bipartite graph. Term nodes are sized by gene count and colored
#' by -log10(padj). Gene nodes are small grey labels.
#'
#' Requires the igraph package; exits gracefully (status 0) if unavailable.
#'
#' @param data_dir Character. Directory containing enrichment_results.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: top_n (default 10), group, padj_cutoff (default 0.05).
plot_enrichment_network <- function(data_dir, out_path, params) {
  tryCatch({
    # ---- igraph guard ----
    if (!requireNamespace("igraph", quietly = TRUE)) {
      cat("WARNING: igraph not installed -- skipping enrichment network\n",
          file = stderr())
      quit(status = 0)
    }

    # ---- Read CSV ----
    csv_path <- file.path(data_dir, "enrichment_results.csv")
    if (!file.exists(csv_path)) {
      csv_path <- file.path(data_dir, "top_terms.csv")
    }
    if (!file.exists(csv_path)) {
      cat("ERROR: No enrichment CSV found in ", data_dir, "\n",
          sep = "", file = stderr())
      quit(status = 1)
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # ---- Parameters ----
    top_n       <- as.integer(params[["top_n"]] %||% "10")
    padj_cutoff <- as.numeric(params[["padj_cutoff"]] %||% "0.05")
    group_use   <- params[["group"]]

    # ---- Filter group ----
    if ("group" %in% colnames(df)) {
      if (is.null(group_use) || !group_use %in% df$group) {
        group_use <- df$group[1]
      }
      df <- df[df$group == group_use, , drop = FALSE]
    }

    # ---- Standardize p-value column ----
    if (!"pvalue_adj" %in% colnames(df) && "pvalue" %in% colnames(df)) {
      df$pvalue_adj <- df$pvalue
    }
    if ("pvalue_adj" %in% colnames(df)) {
      df$pvalue_adj <- as.numeric(df$pvalue_adj)
      df <- df[!is.na(df$pvalue_adj) & df$pvalue_adj < padj_cutoff, , drop = FALSE]
    }

    if (nrow(df) == 0) {
      cat("WARNING: No significant terms to plot\n", file = stderr())
      quit(status = 0)
    }

    # ---- Detect gene column ----
    gene_col <- NULL
    for (cand in c("genes", "geneID", "leading_edge")) {
      if (cand %in% colnames(df) && !all(is.na(df[[cand]]))) {
        gene_col <- cand
        break
      }
    }
    if (is.null(gene_col)) {
      cat("WARNING: No gene column found (genes/geneID/leading_edge) -- skipping network\n",
          file = stderr())
      quit(status = 0)
    }

    # ---- Sort and take top N ----
    df$neg_log_padj <- -log10(df$pvalue_adj + 1e-300)
    df <- df[order(df$neg_log_padj, decreasing = TRUE), ]
    df <- head(df, top_n)

    # ---- Parse gene lists ----
    df$gene_list <- lapply(df[[gene_col]], function(x) {
      genes <- unlist(strsplit(as.character(x), "[/,;]"))
      trimws(genes[nzchar(trimws(genes))])
    })
    df$gene_count <- sapply(df$gene_list, length)
    df <- df[df$gene_count > 0, , drop = FALSE]
    if (nrow(df) == 0) {
      cat("WARNING: No terms with parseable genes\n", file = stderr())
      quit(status = 0)
    }

    # ---- Truncate long term names ----
    df$term_short <- ifelse(nchar(df$term) > 45,
                            paste0(substr(df$term, 1, 42), "..."),
                            df$term)

    # ---- Build bipartite graph ----
    edges_list <- lapply(seq_len(nrow(df)), function(i) {
      data.frame(from = df$term_short[i],
                 to   = df$gene_list[[i]],
                 stringsAsFactors = FALSE)
    })
    edges <- do.call(rbind, edges_list)

    all_genes <- unique(edges$to)
    nodes_term <- data.frame(
      name  = df$term_short,
      class = "term",
      metric = df$neg_log_padj,
      node_size = df$gene_count,
      stringsAsFactors = FALSE
    )
    nodes_gene <- data.frame(
      name  = all_genes,
      class = "gene",
      metric = 0,
      node_size = 1,
      stringsAsFactors = FALSE
    )
    nodes <- rbind(nodes_term, nodes_gene)

    graph <- igraph::graph_from_data_frame(d = edges,
                                           vertices = nodes,
                                           directed = FALSE)
    layout <- igraph::layout_with_fr(graph)
    df_nodes <- nodes
    df_nodes$dim1 <- layout[, 1]
    df_nodes$dim2 <- layout[, 2]

    # ---- Build edge coordinates ----
    rownames(df_nodes) <- df_nodes$name
    df_edges <- edges
    df_edges$from_dim1 <- df_nodes[df_edges$from, "dim1"]
    df_edges$from_dim2 <- df_nodes[df_edges$from, "dim2"]
    df_edges$to_dim1   <- df_nodes[df_edges$to, "dim1"]
    df_edges$to_dim2   <- df_nodes[df_edges$to, "dim2"]

    term_nodes <- df_nodes[df_nodes$class == "term", , drop = FALSE]
    gene_nodes <- df_nodes[df_nodes$class == "gene", , drop = FALSE]

    # ---- Plot ----
    p <- ggplot() +
      geom_segment(data = df_edges,
                   aes(x = from_dim1, y = from_dim2,
                       xend = to_dim1, yend = to_dim2),
                   color = "grey70", alpha = 0.5, linewidth = 0.3) +
      geom_point(data = term_nodes,
                 aes(x = dim1, y = dim2,
                     size = node_size, fill = metric),
                 shape = 21, color = "black", stroke = 0.5) +
      scale_fill_viridis_c(option = "plasma", name = "-log10(padj)") +
      scale_size_continuous(range = c(4, 12), name = "Gene count") +
      geom_point(data = gene_nodes,
                 aes(x = dim1, y = dim2),
                 size = 1.5, color = "grey30", shape = 16)

    # Label gene nodes
    if (requireNamespace("ggrepel", quietly = TRUE)) {
      p <- p + ggrepel::geom_text_repel(
        data = gene_nodes,
        aes(x = dim1, y = dim2, label = name),
        size = 2.2, color = "grey30", max.overlaps = 30,
        segment.size = 0.2, segment.color = "grey60"
      )
    } else {
      p <- p + geom_text(data = gene_nodes,
                         aes(x = dim1, y = dim2, label = name),
                         size = 2.2, color = "grey30", nudge_y = 0.3)
    }

    # Label term nodes
    if (requireNamespace("ggrepel", quietly = TRUE)) {
      p <- p + ggrepel::geom_text_repel(
        data = term_nodes,
        aes(x = dim1, y = dim2, label = name),
        size = 3, fontface = "bold", max.overlaps = 20,
        segment.size = 0.3, segment.color = "grey50",
        point.size = NA, force = 5
      )
    } else {
      p <- p + geom_text(data = term_nodes,
                         aes(x = dim1, y = dim2, label = name),
                         size = 3, fontface = "bold", nudge_y = 0.5)
    }

    p <- p +
      labs(title = paste0("Enrichment Network"),
           x = NULL, y = NULL) +
      theme_omics() +
      theme(axis.text = element_blank(),
            axis.ticks = element_blank(),
            axis.line = element_blank(),
            panel.grid.major.y = element_blank())

    ggsave_standard(p, out_path, width = 10, height = 9)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}


# ---------------------------------------------------------------------------
# Function 7: plot_enrichment_enrichmap
# ---------------------------------------------------------------------------
#' Enrichment term similarity map (clustered term network).
#'
#' Clusters enriched terms by gene overlap (Jaccard similarity) and displays
#' them as a network. Edges represent shared genes, node size = gene count,
#' node color = cluster membership. Top terms per cluster are labeled.
#'
#' Requires the igraph package; exits gracefully (status 0) if unavailable.
#'
#' @param data_dir Character. Directory containing enrichment_results.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: top_n (default 50), group,
#'   min_similarity (default 0.1), padj_cutoff (default 0.05).
plot_enrichment_enrichmap <- function(data_dir, out_path, params) {
  tryCatch({
    # ---- igraph guard ----
    if (!requireNamespace("igraph", quietly = TRUE)) {
      cat("WARNING: igraph not installed -- skipping enrichmap\n",
          file = stderr())
      quit(status = 0)
    }

    # ---- Read CSV ----
    csv_path <- file.path(data_dir, "enrichment_results.csv")
    if (!file.exists(csv_path)) {
      csv_path <- file.path(data_dir, "top_terms.csv")
    }
    if (!file.exists(csv_path)) {
      cat("ERROR: No enrichment CSV found in ", data_dir, "\n",
          sep = "", file = stderr())
      quit(status = 1)
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # ---- Parameters ----
    top_n          <- as.integer(params[["top_n"]] %||% "50")
    padj_cutoff    <- as.numeric(params[["padj_cutoff"]] %||% "0.05")
    min_similarity <- as.numeric(params[["min_similarity"]] %||% "0.1")
    group_use      <- params[["group"]]

    # ---- Filter group ----
    if ("group" %in% colnames(df)) {
      if (is.null(group_use) || !group_use %in% df$group) {
        group_use <- df$group[1]
      }
      df <- df[df$group == group_use, , drop = FALSE]
    }

    # ---- Standardize p-value column ----
    if (!"pvalue_adj" %in% colnames(df) && "pvalue" %in% colnames(df)) {
      df$pvalue_adj <- df$pvalue
    }
    if ("pvalue_adj" %in% colnames(df)) {
      df$pvalue_adj <- as.numeric(df$pvalue_adj)
      df <- df[!is.na(df$pvalue_adj) & df$pvalue_adj < padj_cutoff, , drop = FALSE]
    }

    if (nrow(df) == 0) {
      cat("WARNING: No significant terms to plot\n", file = stderr())
      quit(status = 0)
    }

    # ---- Detect gene column ----
    gene_col <- NULL
    for (cand in c("genes", "geneID", "leading_edge")) {
      if (cand %in% colnames(df) && !all(is.na(df[[cand]]))) {
        gene_col <- cand
        break
      }
    }
    if (is.null(gene_col)) {
      cat("WARNING: No gene column found -- skipping enrichmap\n",
          file = stderr())
      quit(status = 0)
    }

    # ---- Sort and take top N ----
    df$neg_log_padj <- -log10(df$pvalue_adj + 1e-300)
    df <- df[order(df$neg_log_padj, decreasing = TRUE), ]
    df <- head(df, top_n)

    # ---- Parse gene lists ----
    df$gene_list <- lapply(df[[gene_col]], function(x) {
      genes <- unlist(strsplit(as.character(x), "[/,;]"))
      trimws(genes[nzchar(trimws(genes))])
    })
    df$gene_count <- sapply(df$gene_list, length)
    df <- df[df$gene_count > 0, , drop = FALSE]

    if (nrow(df) < 2) {
      cat("WARNING: Need at least 2 terms for enrichmap\n", file = stderr())
      quit(status = 0)
    }

    # ---- Truncate long term names ----
    df$term_short <- ifelse(nchar(df$term) > 45,
                            paste0(substr(df$term, 1, 42), "..."),
                            df$term)
    # Ensure uniqueness
    if (anyDuplicated(df$term_short)) {
      df$term_short <- make.unique(df$term_short, sep = " ")
    }

    # ---- Build term-term similarity (Jaccard) ----
    n_terms <- nrow(df)
    edge_from <- character(0)
    edge_to   <- character(0)
    edge_wt   <- numeric(0)
    for (i in seq_len(n_terms - 1)) {
      for (j in (i + 1):n_terms) {
        inter <- length(intersect(df$gene_list[[i]], df$gene_list[[j]]))
        union_n <- length(union(df$gene_list[[i]], df$gene_list[[j]]))
        if (union_n > 0) {
          jacc <- inter / union_n
          if (jacc >= min_similarity) {
            edge_from <- c(edge_from, df$term_short[i])
            edge_to   <- c(edge_to,   df$term_short[j])
            edge_wt   <- c(edge_wt,   jacc)
          }
        }
      }
    }

    # ---- Build graph ----
    nodes <- data.frame(
      name       = df$term_short,
      gene_count = df$gene_count,
      metric     = df$neg_log_padj,
      stringsAsFactors = FALSE
    )

    if (length(edge_from) == 0) {
      # No edges above threshold -- still render nodes without edges
      edges <- data.frame(from = character(0), to = character(0),
                          weight = numeric(0), stringsAsFactors = FALSE)
      graph <- igraph::graph_from_data_frame(d = edges, vertices = nodes,
                                             directed = FALSE)
    } else {
      edges <- data.frame(from = edge_from, to = edge_to,
                          weight = edge_wt, stringsAsFactors = FALSE)
      graph <- igraph::graph_from_data_frame(d = edges, vertices = nodes,
                                             directed = FALSE)
    }

    layout <- igraph::layout_with_fr(graph)
    nodes$dim1 <- layout[, 1]
    nodes$dim2 <- layout[, 2]

    # ---- Cluster ----
    if (igraph::ecount(graph) > 0) {
      clusters <- igraph::cluster_fast_greedy(graph)
      nodes$cluster <- factor(paste0("C", clusters$membership))
    } else {
      nodes$cluster <- factor(paste0("C", seq_len(nrow(nodes))))
    }

    # ---- Select top 3 labels per cluster ----
    label_nodes <- do.call(rbind, lapply(split(nodes, nodes$cluster), function(cl) {
      cl <- cl[order(-cl$metric), ]
      head(cl, 3)
    }))

    nodes$label <- ifelse(nodes$name %in% label_nodes$name, nodes$name, NA)

    # ---- Edge coordinates ----
    rownames(nodes) <- nodes$name
    if (nrow(edges) > 0) {
      df_edges <- edges
      df_edges$from_dim1 <- nodes[df_edges$from, "dim1"]
      df_edges$from_dim2 <- nodes[df_edges$from, "dim2"]
      df_edges$to_dim1   <- nodes[df_edges$to, "dim1"]
      df_edges$to_dim2   <- nodes[df_edges$to, "dim2"]
      df_edges$alpha_val <- scales::rescale(df_edges$weight, to = c(0.15, 0.7))
    } else {
      df_edges <- NULL
    }

    # ---- Plot ----
    n_clusters <- length(unique(nodes$cluster))
    cluster_colors <- omics_palette(max(n_clusters, 3))[seq_len(n_clusters)]

    p <- ggplot()

    if (!is.null(df_edges) && nrow(df_edges) > 0) {
      p <- p + geom_segment(data = df_edges,
                            aes(x = from_dim1, y = from_dim2,
                                xend = to_dim1, yend = to_dim2,
                                alpha = alpha_val),
                            color = "grey50", linewidth = 0.4,
                            show.legend = FALSE) +
        scale_alpha_identity()
    }

    p <- p +
      geom_point(data = nodes,
                 aes(x = dim1, y = dim2,
                     size = gene_count, fill = cluster),
                 shape = 21, color = "black", stroke = 0.4) +
      scale_fill_manual(values = cluster_colors, name = "Cluster") +
      scale_size_continuous(range = c(3, 10), name = "Gene count")

    # Labels
    if (requireNamespace("ggrepel", quietly = TRUE)) {
      p <- p + ggrepel::geom_text_repel(
        data = nodes[!is.na(nodes$label), , drop = FALSE],
        aes(x = dim1, y = dim2, label = label),
        size = 2.8, max.overlaps = 30,
        segment.size = 0.25, segment.color = "grey50",
        fontface = "bold"
      )
    } else {
      p <- p + geom_text(
        data = nodes[!is.na(nodes$label), , drop = FALSE],
        aes(x = dim1, y = dim2, label = label),
        size = 2.8, fontface = "bold", nudge_y = 0.3
      )
    }

    p <- p +
      labs(title = "Enrichment Map (term similarity)",
           x = NULL, y = NULL) +
      theme_omics() +
      theme(axis.text = element_blank(),
            axis.ticks = element_blank(),
            axis.line = element_blank(),
            panel.grid.major.y = element_blank())

    fig_size <- max(8, sqrt(nrow(nodes)) * 1.5 + 4)
    ggsave_standard(p, out_path, width = fig_size, height = fig_size)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
