# embedding.R -- CellDimPlot and FeatureDimPlot equivalents for OmicsClaw R Enhanced
# Reads: figure_data/annotation_embedding_points.csv
# Provides: plot_embedding_discrete, plot_embedding_feature
# Registered in: registry.R

#' Discrete cell-type scatter plot (CellDimPlot equivalent).
#'
#' Reads annotation_embedding_points.csv, colors cells by a categorical column,
#' adds centroid labels for each group.
#'
#' @param data_dir Character. Directory containing annotation_embedding_points.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: color_by (column name, default "cell_type").
plot_embedding_discrete <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "annotation_embedding_points.csv")
    if (!file.exists(csv_path)) {
      stop("annotation_embedding_points.csv not found in ", data_dir)
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # Determine color column
    color_col <- params[["color_by"]]
    if (is.null(color_col) || !color_col %in% colnames(df)) {
      if ("cell_type" %in% colnames(df)) {
        color_col <- "cell_type"
      } else {
        # First non-coordinate, non-id column
        skip <- c("cell_id", "dim1", "dim2")
        candidates <- setdiff(colnames(df), skip)
        if (length(candidates) == 0) stop("No categorical column found for coloring")
        color_col <- candidates[1]
      }
    }

    df[[color_col]] <- factor(df[[color_col]])
    n_groups <- nlevels(df[[color_col]])
    pal <- omics_palette(n_groups)

    # Compute centroids for labels
    centroids <- aggregate(
      cbind(dim1, dim2) ~ df[[color_col]],
      data = df,
      FUN = mean
    )
    colnames(centroids) <- c("group", "dim1", "dim2")

    p <- ggplot(df, aes(x = dim1, y = dim2, color = .data[[color_col]])) +
      geom_point(size = 0.6, alpha = 0.7) +
      scale_color_manual(values = pal) +
      geom_text(
        aes(x = dim1, y = dim2, label = group),
        data = centroids,
        inherit.aes = FALSE,
        size = 3.5, fontface = "bold", check_overlap = TRUE
      ) +
      labs(
        x     = "UMAP 1",
        y     = "UMAP 2",
        color = color_col,
        title = paste0("Cell embedding \u2014 ", color_col)
      ) +
      theme_omics() +
      theme(legend.key.size = unit(0.4, "cm")) +
      guides(color = guide_legend(override.aes = list(size = 3, alpha = 1)))

    ggsave_standard(p, out_path, width = 8, height = 6)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

#' Continuous feature overlay scatter plot (FeatureDimPlot equivalent).
#'
#' Reads annotation_embedding_points.csv, colors cells by a continuous value
#' using a viridis (magma) gradient.
#'
#' @param data_dir Character. Directory containing annotation_embedding_points.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: feature (column name, default "annotation_score").
plot_embedding_feature <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "annotation_embedding_points.csv")
    if (!file.exists(csv_path)) {
      stop("annotation_embedding_points.csv not found in ", data_dir)
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # Determine feature column
    feature_col <- params[["feature"]]
    if (is.null(feature_col) || !feature_col %in% colnames(df)) {
      if ("annotation_score" %in% colnames(df)) {
        feature_col <- "annotation_score"
      } else {
        stop("No continuous feature column found \u2014 pass feature=<colname>")
      }
    }

    # Convert to numeric, warn on NAs
    df[[feature_col]] <- suppressWarnings(as.numeric(df[[feature_col]]))
    n_na <- sum(is.na(df[[feature_col]]))
    if (n_na > 0) {
      cat("WARNING:", n_na, "NA values in", feature_col, "- shown as grey\n",
          file = stderr())
    }

    p <- ggplot(df, aes(x = dim1, y = dim2, color = .data[[feature_col]])) +
      geom_point(size = 0.6, alpha = 0.8) +
      scale_color_viridis_c(
        option   = "magma",
        name     = feature_col,
        na.value = "#CCCCCC"
      ) +
      labs(
        x     = "UMAP 1",
        y     = "UMAP 2",
        title = paste0(feature_col, " \u2014 embedding overlay")
      ) +
      theme_omics()

    ggsave_standard(p, out_path, width = 8, height = 6)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
