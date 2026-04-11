# communication.R -- CCCHeatmap and CCCNetworkPlot renderers for OmicsClaw R Enhanced
# Reads: figure_data/sender_receiver_summary.csv (or top_interactions.csv fallback)
# Provides: plot_ccc_heatmap, plot_ccc_network
# Registered in: registry.R

# ---- Internal helper: load CCC data ----

#' Load sender-receiver summary from figure_data directory.
#'
#' Tries sender_receiver_summary.csv first; falls back to top_interactions.csv
#' (aggregating by source+target). Returns a data.frame with columns:
#' source, target, score, n_interactions.
#'
#' @param data_dir Character. Directory containing CSV files.
#' @return data.frame
.load_ccc_data <- function(data_dir) {
  primary <- file.path(data_dir, "sender_receiver_summary.csv")
  fallback <- file.path(data_dir, "top_interactions.csv")

  if (file.exists(primary)) {
    df <- read.csv(primary, stringsAsFactors = FALSE)
    if (nrow(df) > 0) {
      df$score <- as.numeric(df$score)
      df$score[is.na(df$score)] <- 0
      if (!"n_interactions" %in% colnames(df)) {
        df$n_interactions <- 1L
      }
      return(df[, c("source", "target", "score", "n_interactions")])
    }
  }

  if (file.exists(fallback)) {
    raw <- read.csv(fallback, stringsAsFactors = FALSE)
    if (nrow(raw) > 0) {
      agg <- aggregate(
        score ~ source + target,
        data = raw,
        FUN = mean
      )
      counts <- aggregate(
        score ~ source + target,
        data = raw,
        FUN = length
      )
      colnames(counts)[3] <- "n_interactions"
      df <- merge(agg, counts, by = c("source", "target"))
      df$score <- as.numeric(df$score)
      df$score[is.na(df$score)] <- 0
      return(df[, c("source", "target", "score", "n_interactions")])
    }
  }

  stop("No CCC data found. Expected sender_receiver_summary.csv or ",
       "top_interactions.csv in ", data_dir)
}

# ---- Function 1: plot_ccc_heatmap ----

#' Sender-receiver interaction heatmap / dot matrix.
#'
#' Builds a ggplot2 heatmap (geom_tile) or dot matrix (geom_point)
#' showing cell-cell communication scores between sender and receiver
#' cell types.
#'
#' @param data_dir Character. Directory containing CCC CSV files.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: plot_type ("heatmap" or "dot", default "heatmap").
plot_ccc_heatmap <- function(data_dir, out_path, params) {
  tryCatch({
    df <- .load_ccc_data(data_dir)
    plot_type <- params[["plot_type"]]
    if (is.null(plot_type) || !plot_type %in% c("heatmap", "dot")) {
      plot_type <- "heatmap"
    }

    # Handle empty data
    if (nrow(df) == 0 || all(df$score == 0)) {
      p <- ggplot() +
        annotate("text", x = 0.5, y = 0.5, label = "No interactions detected",
                 size = 5, color = "grey50") +
        theme_void() +
        labs(title = "Cell-Cell Communication",
             subtitle = "No interactions detected")
      ggsave_standard(p, out_path, width = 6, height = 4)
      return(invisible(NULL))
    }

    # Build complete sender x receiver grid
    all_types <- sort(unique(c(df$source, df$target)))
    n_types <- length(all_types)

    # Order cell types by total outgoing score (descending)
    out_scores <- aggregate(score ~ source, data = df, FUN = sum)
    colnames(out_scores) <- c("cell_type", "total_out")
    type_order <- out_scores$cell_type[order(-out_scores$total_out)]
    # Add any types not in source (only in target)
    type_order <- c(type_order, setdiff(all_types, type_order))

    grid <- expand.grid(source = type_order, target = type_order,
                        stringsAsFactors = FALSE)
    grid <- merge(grid, df, by = c("source", "target"), all.x = TRUE)
    grid$score[is.na(grid$score)] <- 0
    grid$n_interactions[is.na(grid$n_interactions)] <- 0

    grid$source <- factor(grid$source, levels = rev(type_order))
    grid$target <- factor(grid$target, levels = type_order)

    if (plot_type == "heatmap") {
      p <- ggplot(grid, aes(x = target, y = source, fill = score)) +
        geom_tile(color = "white", linewidth = 0.5) +
        geom_text(
          aes(label = ifelse(score > 0, round(score, 2), "")),
          size = 2.5, color = "grey20"
        ) +
        scale_fill_gradient2(
          low = "#377EB8", mid = "white", high = "#E41A1C",
          midpoint = 0, name = "Score"
        ) +
        labs(x = "Receiver", y = "Sender",
             title = "Cell-Cell Communication") +
        theme_omics() +
        theme(axis.text.x = element_text(angle = 45, hjust = 1))
    } else {
      # dot variant
      # Only show non-zero entries for dots
      dot_df <- grid[grid$score > 0, ]
      p <- ggplot(dot_df, aes(x = target, y = source,
                              color = score, size = n_interactions)) +
        geom_point() +
        scale_color_gradient(low = "#DEEBF7", high = "#08306B", name = "Score") +
        scale_size_continuous(range = c(1, 8), name = "n_interactions") +
        scale_x_discrete(drop = FALSE) +
        scale_y_discrete(drop = FALSE) +
        labs(x = "Receiver", y = "Sender",
             title = "Cell-Cell Communication") +
        theme_omics() +
        theme(axis.text.x = element_text(angle = 45, hjust = 1))
    }

    # Dynamic size
    w <- min(14, max(5, n_types * 0.7 + 1.5))
    h <- min(14, max(4, n_types * 0.7 + 1.5))
    ggsave_standard(p, out_path, width = w, height = h)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 2: plot_ccc_network ----

#' Arc network diagram for cell-cell communication.
#'
#' Builds a ggplot2-native arc network using geom_curve (no circlize dependency).
#' Nodes are arranged in a circle; directed arcs connect sender to receiver,
#' with width proportional to interaction score.
#'
#' @param data_dir Character. Directory containing CCC CSV files.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: min_score (numeric, default 0),
#'   top_n (integer, default 20).
plot_ccc_network <- function(data_dir, out_path, params) {
  tryCatch({
    df <- .load_ccc_data(data_dir)

    # Filter to positive scores
    df <- df[df$score > 0, ]

    # Apply min_score filter
    min_score <- as.numeric(params[["min_score"]] %||% 0)
    df <- df[df$score >= min_score, ]

    # Handle empty data
    if (nrow(df) == 0) {
      p <- ggplot() +
        annotate("text", x = 0, y = 0, label = "No interactions detected",
                 size = 5, color = "grey50") +
        coord_equal() +
        theme_void() +
        labs(title = "Cell-Cell Communication Network",
             subtitle = "No interactions detected")
      ggsave_standard(p, out_path, width = 8, height = 8)
      return(invisible(NULL))
    }

    # Keep top N edges by score
    top_n <- as.integer(params[["top_n"]] %||% 20)
    if (nrow(df) > top_n) {
      df <- df[order(-df$score), ][seq_len(top_n), ]
    }

    # Compute node positions in a circle
    all_types <- sort(unique(c(df$source, df$target)))
    n_types <- length(all_types)
    angles <- 2 * pi * (seq_len(n_types) - 1) / n_types
    node_df <- data.frame(
      cell_type = all_types,
      x = cos(angles),
      y = sin(angles),
      stringsAsFactors = FALSE
    )

    # Node sizes: proportional to total incoming + outgoing score
    out_sums <- aggregate(score ~ source, data = df, FUN = sum)
    colnames(out_sums) <- c("cell_type", "out_score")
    in_sums <- aggregate(score ~ target, data = df, FUN = sum)
    colnames(in_sums) <- c("cell_type", "in_score")
    node_df <- merge(node_df, out_sums, by = "cell_type", all.x = TRUE)
    node_df <- merge(node_df, in_sums, by = "cell_type", all.x = TRUE)
    node_df$out_score[is.na(node_df$out_score)] <- 0
    node_df$in_score[is.na(node_df$in_score)] <- 0
    node_df$total_score <- node_df$out_score + node_df$in_score

    # Node colors
    pal <- omics_palette(n_types)
    names(pal) <- all_types

    # Build edge data with coordinates
    edge_df <- df
    edge_df <- merge(edge_df,
                     node_df[, c("cell_type", "x", "y")],
                     by.x = "source", by.y = "cell_type")
    colnames(edge_df)[colnames(edge_df) == "x"] <- "x_from"
    colnames(edge_df)[colnames(edge_df) == "y"] <- "y_from"
    edge_df <- merge(edge_df,
                     node_df[, c("cell_type", "x", "y")],
                     by.x = "target", by.y = "cell_type")
    colnames(edge_df)[colnames(edge_df) == "x"] <- "x_to"
    colnames(edge_df)[colnames(edge_df) == "y"] <- "y_to"

    # Build plot
    p <- ggplot() +
      # Arcs (edges) -- behind nodes
      geom_curve(
        data = edge_df,
        aes(x = x_from, y = y_from, xend = x_to, yend = y_to,
            linewidth = score, color = source),
        curvature = 0.25,
        alpha = 0.6,
        arrow = arrow(length = unit(0.12, "inches"), type = "closed")
      ) +
      scale_linewidth_continuous(range = c(0.3, 3), name = "Score") +
      scale_color_manual(values = pal, name = "Sender") +
      # New scale for node fill
      ggnewscale::new_scale_color() +
      # Nodes -- on top
      geom_point(
        data = node_df,
        aes(x = x, y = y, size = total_score, color = cell_type)
      ) +
      scale_size_continuous(range = c(3, 12), name = "Total Score") +
      scale_color_manual(values = pal, name = "Cell Type") +
      # Labels
      geom_text(
        data = node_df,
        aes(x = x * 1.15, y = y * 1.15, label = cell_type),
        size = 3, check_overlap = TRUE
      ) +
      coord_equal() +
      theme_void() +
      theme(legend.position = "right") +
      labs(title = "Cell-Cell Communication Network")

    ggsave_standard(p, out_path, width = 8, height = 8)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
