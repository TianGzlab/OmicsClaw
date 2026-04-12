# density.R -- Cell density ridgeline renderer for OmicsClaw R Enhanced
# Reads: figure_data/ CSVs with embedding or pseudotime data
# Provides: plot_cell_density
# Registered in: registry.R

# ---- Function: plot_cell_density ----

#' Ridgeline density plot for cell density grouped by cell type or along a feature.
#'
#' Reads pseudotime_points.csv or annotation_embedding_points.csv from figure_data/.
#' Uses ggridges::geom_density_ridges for ridgeline layout.
#' Falls back to geom_density if no grouping column is found.
#'
#' @param data_dir Character. figure_data/ directory.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: feature (column name for x-axis),
#'   group_by (categorical column for y-axis grouping), flip (bool).
plot_cell_density <- function(data_dir, out_path, params) {
  tryCatch({
    # ---- 1. Read CSV ----
    csv_candidates <- c(
      "pseudotime_points.csv",
      "annotation_embedding_points.csv",
      "embedding_points.csv",
      "cytotrace_embedding.csv"
    )
    csv_path <- NULL
    for (f in csv_candidates) {
      p <- file.path(data_dir, f)
      if (file.exists(p)) { csv_path <- p; break }
    }
    if (is.null(csv_path)) {
      stop("No density-compatible CSV found. Expected: ",
           paste(csv_candidates, collapse = ", "))
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) stop("CSV is empty: ", csv_path)

    # ---- 2. Detect feature column (numeric x-axis) ----
    feature_col <- params[["feature"]] %||% NULL
    if (is.null(feature_col) || !feature_col %in% colnames(df)) {
      auto_features <- c("pseudotime", "cytotrace_score", "dpt_pseudotime",
                         "velocity_pseudotime", "dim1")
      feature_col <- intersect(auto_features, colnames(df))
      if (length(feature_col) == 0) {
        stop("No numeric feature column found for density. ",
             "Columns available: ", paste(colnames(df), collapse = ", "))
      }
      feature_col <- feature_col[1]
    }
    # Ensure numeric
    df[[feature_col]] <- as.numeric(df[[feature_col]])
    df <- df[is.finite(df[[feature_col]]), ]
    if (nrow(df) == 0) stop("No finite values in feature column: ", feature_col)

    # ---- 3. Detect group column (categorical y-axis) ----
    group_col <- params[["group_by"]] %||% NULL
    if (is.null(group_col) || !group_col %in% colnames(df)) {
      auto_groups <- c("cell_type", "group", "cluster", "leiden", "louvain")
      group_col <- intersect(auto_groups, colnames(df))
      if (length(group_col) > 0) {
        group_col <- group_col[1]
      } else {
        group_col <- NULL
      }
    }

    # ---- 4. Build plot ----
    flip <- as.logical(params[["flip"]] %||% "FALSE")
    if (is.na(flip)) flip <- FALSE

    .has_ggridges <- requireNamespace("ggridges", quietly = TRUE)

    if (!is.null(group_col)) {
      df[[group_col]] <- factor(df[[group_col]])
      n_groups <- length(unique(df[[group_col]]))
      pal <- omics_palette(n_groups)

      if (.has_ggridges) {
        # Ridgeline plot
        p <- ggplot(df, aes(x = .data[[feature_col]],
                            y = .data[[group_col]],
                            fill = .data[[group_col]])) +
          ggridges::geom_density_ridges(scale = 1.2, alpha = 0.7,
                                        rel_min_height = 0.01) +
          scale_fill_manual(values = pal) +
          scale_y_discrete(expand = c(0, 0)) +
          labs(x = feature_col, y = "", title = paste("Cell density along", feature_col)) +
          theme_omics() +
          theme(legend.position = "none")
      } else {
        # Fallback: overlapping density curves
        p <- ggplot(df, aes(x = .data[[feature_col]],
                            fill = .data[[group_col]],
                            color = .data[[group_col]])) +
          geom_density(alpha = 0.4) +
          scale_fill_manual(values = pal) +
          scale_color_manual(values = pal) +
          labs(x = feature_col, y = "Density",
               title = paste("Cell density along", feature_col)) +
          theme_omics()
      }

      if (isTRUE(flip)) p <- p + coord_flip()

      plot_height <- max(4, n_groups * 0.6 + 1.5)
      ggsave_standard(p, out_path, width = 8, height = plot_height)

    } else {
      # No grouping: single density curve
      p <- ggplot(df, aes(x = .data[[feature_col]])) +
        geom_density(fill = omics_palette(1), alpha = 0.6, color = "black") +
        labs(x = feature_col, y = "Density",
             title = paste("Cell density along", feature_col)) +
        theme_omics()

      if (isTRUE(flip)) p <- p + coord_flip()

      ggsave_standard(p, out_path, width = 8, height = 5)
    }

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
