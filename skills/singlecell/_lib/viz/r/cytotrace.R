# cytotrace.R -- CytoTRACE boxplot renderer for OmicsClaw R Enhanced
# Reads: figure_data/cytotrace_embedding.csv (or annotation_embedding_points.csv fallback)
# Provides: plot_cytotrace_boxplot
# Registered in: registry.R

# ---- Function: plot_cytotrace_boxplot ----

#' Boxplot of CytoTRACE score by cell type, ordered by median potency.
#'
#' Reads cytotrace data from figure_data/. Cell types are ordered by median
#' CytoTRACE score (most stem-like first). Box fill color uses potency
#' categories if available, or a blue-to-red gradient based on median score.
#'
#' @param data_dir Character. Directory containing CSV files.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: group_col (default "cell_type"),
#'   score_col (default "cytotrace_score").
plot_cytotrace_boxplot <- function(data_dir, out_path, params) {
  tryCatch({
    # Try cytotrace_embedding.csv first, fall back to annotation_embedding_points.csv
    csv_path <- file.path(data_dir, "cytotrace_embedding.csv")
    if (!file.exists(csv_path)) {
      csv_path <- file.path(data_dir, "annotation_embedding_points.csv")
    }
    if (!file.exists(csv_path)) {
      stop("No cytotrace data found. Expected cytotrace_embedding.csv or ",
           "annotation_embedding_points.csv in ", data_dir)
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) stop("Empty cytotrace data")

    # Determine column names
    group_col <- params[["group_col"]] %||% "cell_type"
    score_col <- params[["score_col"]] %||% "cytotrace_score"

    if (!group_col %in% colnames(df)) {
      stop("Group column '", group_col, "' not found in ", basename(csv_path))
    }
    if (!score_col %in% colnames(df)) {
      stop("Score column '", score_col, "' not found in ", basename(csv_path))
    }

    df <- df[!is.na(df[[group_col]]) & !is.na(df[[score_col]]), ]
    df[[score_col]] <- as.numeric(df[[score_col]])

    # Compute median score per cell type and order descending (most stem-like first)
    medians <- aggregate(
      as.formula(paste0(score_col, " ~ ", group_col)),
      data = df, FUN = median
    )
    colnames(medians) <- c("group", "median_score")
    medians <- medians[order(-medians$median_score), ]
    type_order <- medians$group
    n_types <- length(type_order)

    df[[group_col]] <- factor(df[[group_col]], levels = type_order)

    # Potency color scheme (from scop CytoTRACEPlot)
    potency_colors <- c(
      "Differentiated" = "#806D9E",
      "Unipotent"      = "#519673",
      "Oligopotent"    = "#FFF799",
      "Multipotent"    = "#F9BD10",
      "Pluripotent"    = "#ED5736",
      "Totipotent"     = "#D70440"
    )

    # Determine fill strategy
    has_potency <- "cytotrace_potency" %in% colnames(df)

    if (has_potency) {
      # Map each cell type to its most frequent potency category
      potency_map <- tapply(df$cytotrace_potency, df[[group_col]], function(x) {
        tbl <- table(x)
        names(tbl)[which.max(tbl)]
      })
      fill_vals <- potency_colors[as.character(potency_map[type_order])]
      names(fill_vals) <- type_order
      # Replace NA fills (unknown potency) with grey
      fill_vals[is.na(fill_vals)] <- "#CCCCCC"

      p <- ggplot(df, aes(x = .data[[group_col]], y = .data[[score_col]])) +
        geom_boxplot(
          aes(fill = .data[[group_col]]),
          outlier.size = 0.3, alpha = 0.7, width = 0.7
        ) +
        scale_fill_manual(values = fill_vals, guide = "none")
    } else {
      # Fill by median score: blue (differentiated) to red (stem-like)
      # Assign a fill column based on median
      med_lookup <- setNames(medians$median_score, medians$group)
      df$median_fill <- med_lookup[as.character(df[[group_col]])]

      p <- ggplot(df, aes(x = .data[[group_col]], y = .data[[score_col]])) +
        geom_boxplot(
          aes(fill = median_fill),
          outlier.size = 0.3, alpha = 0.7, width = 0.7
        ) +
        scale_fill_gradient(
          low = "#2166AC", high = "#B2182B",
          name = "Median score"
        )
    }

    # Add jitter for small datasets
    n_cells <- nrow(df)
    if (n_cells < 5000) {
      p <- p + geom_jitter(width = 0.15, size = 0.2, alpha = 0.1)
    }

    p <- p +
      coord_flip() +
      labs(
        x = "Cell Type",
        y = "CytoTRACE Score",
        title = "CytoTRACE Differentiation Potency"
      ) +
      theme_omics() +
      theme(panel.grid.major.y = element_blank())

    # Dynamic height based on number of cell types
    h <- max(4, n_types * 0.5 + 1.5)
    ggsave_standard(p, out_path, width = 8, height = h)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
