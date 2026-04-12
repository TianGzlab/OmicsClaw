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
    # Try multiple CSV sources for embedding coordinates
    candidates <- c("annotation_embedding_points.csv", "pseudotime_points.csv",
                     "embedding_points.csv", "cytotrace_embedding.csv",
                     "umap_points.csv")
    csv_path <- NULL
    for (f in candidates) {
      p <- file.path(data_dir, f)
      if (file.exists(p)) { csv_path <- p; break }
    }
    if (is.null(csv_path)) {
      stop("No embedding CSV found. Expected: ", paste(candidates, collapse=", "))
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # Normalize coordinate column names to dim1/dim2
    if (!"dim1" %in% colnames(df) && "coord1" %in% colnames(df)) {
      colnames(df)[colnames(df) == "coord1"] <- "dim1"
      colnames(df)[colnames(df) == "coord2"] <- "dim2"
    }
    if (!"dim1" %in% colnames(df) && "UMAP_1" %in% colnames(df)) {
      colnames(df)[colnames(df) == "UMAP_1"] <- "dim1"
      colnames(df)[colnames(df) == "UMAP_2"] <- "dim2"
    }
    if (!"dim1" %in% colnames(df) && "UMAP1" %in% colnames(df)) {
      colnames(df)[colnames(df) == "UMAP1"] <- "dim1"
      colnames(df)[colnames(df) == "UMAP2"] <- "dim2"
    }

    # Determine color column
    color_col <- params[["color_by"]]
    if (is.null(color_col) || !color_col %in% colnames(df)) {
      if ("cell_type" %in% colnames(df)) {
        color_col <- "cell_type"
      } else {
        # Skip coordinates, IDs, and metadata columns that are not group labels
        skip <- c("cell_id", "dim1", "dim2", "coord1", "coord2",
                  "UMAP_1", "UMAP_2", "UMAP1", "UMAP2", "embedding_key")
        candidates <- setdiff(colnames(df), skip)
        if (length(candidates) == 0) stop("No categorical column found for coloring")
        # Prefer known cluster column names
        preferred <- c("leiden", "louvain", "cluster", "seurat_clusters",
                       "cell_type", "group", "condition", "sample")
        hit <- intersect(preferred, candidates)
        color_col <- if (length(hit) > 0) hit[1] else candidates[1]
      }
    }

    df[[color_col]] <- factor(df[[color_col]])
    n_groups <- nlevels(df[[color_col]])
    pal <- omics_palette(n_groups)

    # Compute centroids for labels — use the column name directly in the formula
    # NOTE: aggregate(formula) with df[[col]] creates a literal column name like
    # "df[[color_col]]"; instead use reformulate() to build the formula correctly.
    centroids <- aggregate(
      reformulate(color_col, response = "cbind(dim1, dim2)"),
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
    candidates <- c("annotation_embedding_points.csv", "pseudotime_points.csv",
                     "embedding_points.csv", "cytotrace_embedding.csv",
                     "umap_points.csv")
    csv_path <- NULL
    for (f in candidates) {
      p <- file.path(data_dir, f)
      if (file.exists(p)) { csv_path <- p; break }
    }
    if (is.null(csv_path)) {
      stop("No embedding CSV found. Expected: ", paste(candidates, collapse=", "))
    }
    df <- read.csv(csv_path, stringsAsFactors = FALSE)

    # Normalize coordinate column names
    if (!"dim1" %in% colnames(df) && "coord1" %in% colnames(df)) {
      colnames(df)[colnames(df) == "coord1"] <- "dim1"
      colnames(df)[colnames(df) == "coord2"] <- "dim2"
    }
    if (!"dim1" %in% colnames(df) && "UMAP_1" %in% colnames(df)) {
      colnames(df)[colnames(df) == "UMAP_1"] <- "dim1"
      colnames(df)[colnames(df) == "UMAP_2"] <- "dim2"
    }
    if (!"dim1" %in% colnames(df) && "UMAP1" %in% colnames(df)) {
      colnames(df)[colnames(df) == "UMAP1"] <- "dim1"
      colnames(df)[colnames(df) == "UMAP2"] <- "dim2"
    }

    # Determine feature column — try multiple common names
    feature_col <- params[["feature"]]
    if (is.null(feature_col) || !feature_col %in% colnames(df)) {
      feature_candidates <- c("annotation_score", "pseudotime", "dpt_pseudotime",
                              "score", "doublet_score", "velocity_magnitude")
      feature_col <- intersect(feature_candidates, colnames(df))
      if (length(feature_col) == 0) {
        # Try any numeric column that isn't a coordinate
        skip <- c("cell_id", "dim1", "dim2", "coord1", "coord2", "UMAP_1", "UMAP_2")
        num_cols <- setdiff(colnames(df), skip)
        if (length(num_cols) > 0) {
          num_cols <- num_cols[sapply(df[num_cols], function(x) is.numeric(x) || all(grepl("^[0-9.eE+-]+$", x[!is.na(x)])))]
        }
        if (length(num_cols) > 0) feature_col <- num_cols[1]
        else stop("No continuous feature column found \u2014 pass feature=<colname>")
      } else {
        feature_col <- feature_col[1]
      }
    }

    # Convert to numeric, filter Inf, warn on NAs
    df[[feature_col]] <- suppressWarnings(as.numeric(df[[feature_col]]))
    df[[feature_col]][!is.finite(df[[feature_col]])] <- NA
    n_na <- sum(is.na(df[[feature_col]]))
    if (n_na > 0) {
      cat("WARNING:", n_na, "NA/Inf values in", feature_col, "- shown as grey\n",
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
