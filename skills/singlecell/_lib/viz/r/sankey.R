# sankey.R -- Cell type Sankey/alluvial renderer for OmicsClaw R Enhanced
# Reads: figure_data/ CSVs with categorical columns for cell transitions
# Provides: plot_cell_sankey
# Registered in: registry.R

# ---- Function: plot_cell_sankey ----

#' Alluvial/Sankey diagram showing cell type transitions between two categories.
#'
#' Reads annotation_embedding_points.csv or cell_type_transitions.csv from figure_data/.
#' Uses ggalluvial for alluvial flow layout.
#' Falls back to stacked bar chart if ggalluvial is not installed.
#'
#' @param data_dir Character. figure_data/ directory.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: left_col (default "cluster"),
#'   right_col (default "cell_type"), title.
plot_cell_sankey <- function(data_dir, out_path, params) {
  tryCatch({
    # ---- 1. Read CSV ----
    csv_candidates <- c(
      "cell_type_transitions.csv",
      "annotation_embedding_points.csv",
      "embedding_points.csv"
    )
    csv_path <- NULL
    for (f in csv_candidates) {
      p <- file.path(data_dir, f)
      if (file.exists(p)) { csv_path <- p; break }
    }
    if (is.null(csv_path)) {
      stop("No Sankey-compatible CSV found. Expected: ",
           paste(csv_candidates, collapse = ", "))
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) stop("CSV is empty: ", csv_path)

    # ---- 2. Determine left/right columns ----
    # For cell_type_transitions.csv: use "from" and "to"
    # For annotation_embedding_points.csv: use left_col and right_col params
    if (all(c("from", "to") %in% colnames(df))) {
      left_col <- "from"
      right_col <- "to"
    } else {
      left_col <- params[["left_col"]] %||% NULL
      right_col <- params[["right_col"]] %||% NULL

      # Auto-detect if not specified
      if (is.null(left_col) || !left_col %in% colnames(df)) {
        auto_left <- c("cluster", "leiden", "louvain", "batch", "sample")
        left_col <- intersect(auto_left, colnames(df))
        if (length(left_col) == 0) {
          stop("Cannot auto-detect left column. ",
               "Columns available: ", paste(colnames(df), collapse = ", "))
        }
        left_col <- left_col[1]
      }
      if (is.null(right_col) || !right_col %in% colnames(df)) {
        auto_right <- c("cell_type", "annotation", "group")
        right_col <- intersect(auto_right, colnames(df))
        if (length(right_col) == 0) {
          stop("Cannot auto-detect right column. ",
               "Columns available: ", paste(colnames(df), collapse = ", "))
        }
        right_col <- right_col[1]
      }
    }

    # Validate columns exist
    if (!left_col %in% colnames(df)) stop("Column '", left_col, "' not found in CSV")
    if (!right_col %in% colnames(df)) stop("Column '", right_col, "' not found in CSV")
    if (left_col == right_col) stop("left_col and right_col must be different")

    # ---- 3. Build frequency table ----
    freq_df <- as.data.frame(table(df[[left_col]], df[[right_col]]),
                             stringsAsFactors = FALSE)
    colnames(freq_df) <- c("Left", "Right", "Freq")
    freq_df <- freq_df[freq_df$Freq > 0, ]

    if (nrow(freq_df) == 0) {
      stop("No non-zero frequency pairs between '", left_col, "' and '", right_col, "'")
    }

    n_right <- length(unique(freq_df$Right))
    pal <- omics_palette(n_right)
    plot_title <- params[["title"]] %||% paste("Cell type mapping:", left_col, "->", right_col)

    # ---- 4. Build plot ----
    .has_ggalluvial <- requireNamespace("ggalluvial", quietly = TRUE)

    if (.has_ggalluvial) {
      # Alluvial/Sankey diagram
      p <- ggplot(freq_df, aes(axis1 = Left, axis2 = Right, y = Freq)) +
        ggalluvial::geom_alluvium(aes(fill = Right), width = 1/6, alpha = 0.7) +
        ggalluvial::geom_stratum(width = 1/6, fill = "grey90", color = "black") +
        geom_text(stat = ggalluvial::StatStratum,
                  aes(label = after_stat(stratum)), size = 3) +
        scale_x_discrete(limits = c(left_col, right_col),
                         expand = c(0.1, 0.1)) +
        scale_fill_manual(values = pal, name = right_col) +
        labs(title = plot_title, y = "Number of cells") +
        theme_omics() +
        theme(legend.position = "right",
              panel.grid.major.y = element_blank())

    } else {
      # Fallback: stacked bar chart
      cat("NOTE: ggalluvial not installed, using stacked bar fallback\n",
          file = stderr())

      # Aggregate: for each Left, show Right proportions
      p <- ggplot(freq_df, aes(x = Left, y = Freq, fill = Right)) +
        geom_col(position = "stack", color = "white", linewidth = 0.2) +
        scale_fill_manual(values = pal, name = right_col) +
        scale_y_continuous(expand = expansion(mult = c(0, 0.05))) +
        labs(x = left_col, y = "Number of cells", title = plot_title) +
        theme_omics() +
        theme(axis.text.x = element_text(angle = 45, hjust = 1))
    }

    # Dynamic sizing
    n_strata <- length(unique(freq_df$Left)) + length(unique(freq_df$Right))
    plot_width <- max(7, n_strata * 0.4 + 3)
    plot_height <- max(5, max(length(unique(freq_df$Left)),
                              length(unique(freq_df$Right))) * 0.5 + 2)

    ggsave_standard(p, out_path, width = plot_width, height = plot_height)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
