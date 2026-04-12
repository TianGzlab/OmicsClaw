# communication.R -- CCC renderers for OmicsClaw R Enhanced
# Reads: figure_data/sender_receiver_summary.csv, top_interactions.csv, group_role_summary.csv, pathway_summary.csv
# Provides: plot_ccc_heatmap, plot_ccc_network, plot_ccc_bubble, plot_ccc_stat_bar, plot_ccc_stat_violin, plot_ccc_stat_scatter
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

    # Filter to positive scores and remove self-loops (geom_curve requires distinct endpoints)
    df <- df[df$score > 0 & df$source != df$target, ]

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

# ---- Function 3: plot_ccc_bubble ----

#' Ligand-receptor bubble matrix (CCCHeatmap bubble variant).
#'
#' Reads top_interactions.csv. Shows top L-R pairs as a bubble matrix:
#' rows = ligand-receptor pairs, columns = source->target cell type pairs,
#' size = score, color = -log10(pvalue) or score.
#'
#' @param data_dir Character. Directory containing CCC CSV files.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: top_n (default 30).
plot_ccc_bubble <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "top_interactions.csv")
    if (!file.exists(csv_path)) {
      stop("top_interactions.csv not found in ", data_dir)
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) stop("Empty interactions table")

    top_n <- as.integer(params[["top_n"]] %||% 30)
    df <- df[df$score > 0, ]
    df <- head(df[order(-df$score), ], top_n)

    # Build pair labels
    df$lr_pair <- paste0(df$ligand, " -> ", df$receptor)
    df$cell_pair <- paste0(df$source, " -> ", df$target)

    # Handle pvalue: use -log10(pvalue) for color if available
    if ("pvalue" %in% colnames(df) && !all(is.na(df$pvalue))) {
      df$pvalue <- as.numeric(df$pvalue)
      df$color_val <- -log10(df$pvalue + 1e-300)
      color_name <- "-log10(p)"
    } else {
      df$color_val <- df$score
      color_name <- "Score"
    }

    # Order LR pairs by mean score (descending)
    lr_order <- aggregate(score ~ lr_pair, data = df, FUN = mean)
    lr_order <- lr_order$lr_pair[order(-lr_order$score)]
    df$lr_pair <- factor(df$lr_pair, levels = rev(lr_order))

    # Order cell pairs by frequency
    cp_order <- names(sort(table(df$cell_pair), decreasing = TRUE))
    df$cell_pair <- factor(df$cell_pair, levels = cp_order)

    n_lr <- length(unique(df$lr_pair))
    n_cp <- length(unique(df$cell_pair))

    p <- ggplot(df, aes(x = cell_pair, y = lr_pair)) +
      geom_point(aes(size = score, fill = color_val),
                 shape = 21, color = "black", stroke = 0.3) +
      scale_size_continuous(range = c(2, 7), name = "Score",
                            breaks = scales::breaks_extended(n = 4)) +
      scale_fill_gradientn(
        name = color_name,
        colours = c("#FEE8C8", "#FDBB84", "#E34A33", "#B2182B"),
        guide = guide_colorbar(frame.colour = "black", ticks.colour = "black")
      ) +
      labs(x = "Cell pair (source -> target)",
           y = "Ligand -> Receptor",
           title = "Ligand-receptor interaction bubble matrix") +
      theme_omics() +
      theme(
        axis.text.x = element_text(angle = 45, hjust = 1, size = 8),
        axis.text.y = element_text(size = 7),
        panel.grid.major = element_line(colour = "grey90", linewidth = 0.2)
      )

    w <- max(7, n_cp * 0.8 + 3)
    h <- max(5, n_lr * 0.3 + 2)
    ggsave_standard(p, out_path, width = w, height = h)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 4: plot_ccc_stat_bar ----

#' Horizontal bar chart of top signaling interactions or pathways.
#'
#' Reads top_interactions.csv (or pathway_summary.csv when grouping by pathway).
#' Aggregates by pathway or source->target pair and plots horizontal bars
#' ordered by score descending.
#'
#' @param data_dir Character. Directory containing CCC CSV files.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: top_n (default 15),
#'   group_by ("pathway" or "pair", default auto-detect).
plot_ccc_stat_bar <- function(data_dir, out_path, params) {
  tryCatch({
    top_n <- as.integer(params[["top_n"]] %||% 15)
    group_by <- params[["group_by"]] %||% NULL

    # Auto-detect: if pathway_summary.csv exists and group_by is "pathway", use it
    pathway_csv <- file.path(data_dir, "pathway_summary.csv")
    interactions_csv <- file.path(data_dir, "top_interactions.csv")

    if (!is.null(group_by) && group_by == "pathway" && file.exists(pathway_csv)) {
      df <- read.csv(pathway_csv, stringsAsFactors = FALSE)
      if (nrow(df) == 0) stop("Empty pathway_summary.csv")
      df$score <- as.numeric(df$mean_score)
      df$label <- df$pathway
      plot_title <- "Top signaling pathways"
    } else if (file.exists(interactions_csv)) {
      raw <- read.csv(interactions_csv, stringsAsFactors = FALSE)
      if (nrow(raw) == 0) stop("Empty top_interactions.csv")
      raw$score <- as.numeric(raw$score)

      # Auto-detect group_by
      if (is.null(group_by)) {
        group_by <- if ("pathway" %in% colnames(raw)) "pathway" else "pair"
      }

      if (group_by == "pathway" && "pathway" %in% colnames(raw)) {
        df <- aggregate(score ~ pathway, data = raw, FUN = sum)
        df$label <- df$pathway
        plot_title <- "Top signaling pathways"
      } else {
        raw$pair <- paste0(raw$source, " -> ", raw$target)
        df <- aggregate(score ~ pair, data = raw, FUN = sum)
        df$label <- df$pair
        plot_title <- "Top signaling interactions"
      }
    } else {
      stop("No CCC data found. Expected top_interactions.csv or ",
           "pathway_summary.csv in ", data_dir)
    }

    # Order by score descending and keep top_n
    df <- df[order(-df$score), ]
    df <- head(df, top_n)
    df$label <- factor(df$label, levels = rev(df$label))

    n_bars <- nrow(df)
    pal <- omics_palette(n_bars)

    p <- ggplot(df, aes(x = label, y = score, fill = label)) +
      geom_bar(stat = "identity", width = 0.7) +
      coord_flip() +
      scale_fill_manual(values = pal, guide = "none") +
      labs(x = "", y = "Aggregated score", title = plot_title) +
      theme_omics() +
      theme(panel.grid.major.y = element_blank())

    h <- max(4, n_bars * 0.35 + 1.5)
    ggsave_standard(p, out_path, width = 8, height = h)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 5: plot_ccc_stat_violin ----

#' Violin plot of interaction score distributions across cell type pairs.
#'
#' Reads top_interactions.csv. Shows violin + jitter of scores faceted by
#' source or target cell type.
#'
#' @param data_dir Character. Directory containing CCC CSV files.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: facet_by ("source" or "target", default "source"),
#'   top_n (default 20).
plot_ccc_stat_violin <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "top_interactions.csv")
    if (!file.exists(csv_path)) {
      stop("top_interactions.csv not found in ", data_dir)
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) stop("Empty top_interactions.csv")

    facet_by <- params[["facet_by"]] %||% "source"
    if (!facet_by %in% c("source", "target")) facet_by <- "source"
    top_n <- as.integer(params[["top_n"]] %||% 20)

    df$score <- as.numeric(df$score)
    df <- df[!is.na(df$score) & df$score > 0, ]

    # Keep top_n interactions by score
    if (nrow(df) > top_n) {
      df <- df[order(-df$score), ][seq_len(top_n), ]
    }

    # Determine x-axis and facet variables
    if (facet_by == "source") {
      x_var <- "target"
      facet_var <- "source"
    } else {
      x_var <- "source"
      facet_var <- "target"
    }

    n_facets <- length(unique(df[[facet_var]]))
    pal <- omics_palette(n_facets)
    names(pal) <- sort(unique(df[[facet_var]]))

    p <- ggplot(df, aes(x = .data[[x_var]], y = score, fill = .data[[facet_var]])) +
      geom_violin(trim = TRUE, alpha = 0.7, scale = "width") +
      geom_jitter(width = 0.15, size = 0.5, alpha = 0.3) +
      scale_fill_manual(values = pal, name = facet_by) +
      labs(
        x = x_var,
        y = "Interaction score",
        title = paste0("Score distribution by ", facet_by)
      ) +
      theme_omics() +
      theme(axis.text.x = element_text(angle = 45, hjust = 1))

    # Add faceting only if more than 1 unique facet level
    if (n_facets > 1) {
      p <- p + facet_wrap(as.formula(paste0("~ ", facet_var)),
                          scales = "free_x")
    }

    w <- max(6, n_facets * 3 + 1)
    h <- 5
    ggsave_standard(p, out_path, width = min(w, 16), height = h)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}

# ---- Function 6: plot_ccc_stat_scatter ----

#' Outgoing vs incoming signaling strength scatter plot.
#'
#' Reads group_role_summary.csv. Each point is a cell type, positioned by
#' outgoing (x) and incoming (y) signaling strength. Quadrant lines drawn
#' at median values.
#'
#' @param data_dir Character. Directory containing CCC CSV files.
#' @param out_path Character. Output PNG path.
#' @param params Named list. (currently no user-facing params)
plot_ccc_stat_scatter <- function(data_dir, out_path, params) {
  tryCatch({
    role_csv <- file.path(data_dir, "group_role_summary.csv")
    sr_csv <- file.path(data_dir, "sender_receiver_summary.csv")

    if (file.exists(role_csv)) {
      df <- read.csv(role_csv, stringsAsFactors = FALSE)
      if (nrow(df) == 0) stop("Empty group_role_summary.csv")
    } else if (file.exists(sr_csv)) {
      # Fallback: compute from sender_receiver_summary.csv
      raw <- read.csv(sr_csv, stringsAsFactors = FALSE)
      if (nrow(raw) == 0) stop("Empty sender_receiver_summary.csv")
      raw$score <- as.numeric(raw$score)
      out_agg <- aggregate(score ~ source, data = raw, FUN = sum)
      colnames(out_agg) <- c("cell_type", "outgoing_score")
      in_agg <- aggregate(score ~ target, data = raw, FUN = sum)
      colnames(in_agg) <- c("cell_type", "incoming_score")
      df <- merge(out_agg, in_agg, by = "cell_type", all = TRUE)
      df$outgoing_score[is.na(df$outgoing_score)] <- 0
      df$incoming_score[is.na(df$incoming_score)] <- 0
    } else {
      stop("No role data found. Expected group_role_summary.csv or ",
           "sender_receiver_summary.csv in ", data_dir)
    }

    df$outgoing_score <- as.numeric(df$outgoing_score)
    df$incoming_score <- as.numeric(df$incoming_score)

    n_types <- nrow(df)
    pal <- omics_palette(n_types)

    med_out <- median(df$outgoing_score, na.rm = TRUE)
    med_in <- median(df$incoming_score, na.rm = TRUE)

    p <- ggplot(df, aes(x = outgoing_score, y = incoming_score, color = cell_type)) +
      geom_point(size = 4) +
      geom_text(aes(label = cell_type),
                check_overlap = TRUE, vjust = -0.8, size = 3) +
      geom_hline(yintercept = med_in, linetype = "dashed", color = "grey60") +
      geom_vline(xintercept = med_out, linetype = "dashed", color = "grey60") +
      scale_color_manual(values = pal, guide = "none") +
      labs(
        x = "Outgoing signaling strength",
        y = "Incoming signaling strength",
        title = "Cell type signaling role"
      ) +
      theme_omics()

    ggsave_standard(p, out_path, width = 7, height = 6)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
