# velocity.R -- Velocity magnitude grid overlay for OmicsClaw R Enhanced
# Reads: figure_data/velocity_cells.csv
# Provides: plot_velocity
# Registered in: registry.R
#
# NOTE: velocity_cells.csv contains per-cell UMAP + velocity_magnitude but NOT
# UMAP-space direction vectors. This renderer produces a grid-binned magnitude
# heatmap overlay, NOT actual stream/arrow plots.

#' Velocity magnitude grid overlay on UMAP scatter.
#'
#' Reads velocity_cells.csv, bins cells into a uniform grid over UMAP space,
#' and draws magnitude-colored dots sized by cell count per bin.
#'
#' @param data_dir Character. Directory containing velocity_cells.csv.
#' @param out_path Character. Absolute path for output PNG.
#' @param params Named list. Optional: plot_type ("grid"|"scatter", default "grid"),
#'   color_by (column name, default "velocity_magnitude"), n_bins (integer, default 20).
plot_velocity <- function(data_dir, out_path, params) {
  tryCatch({
    suppressPackageStartupMessages(library(dplyr))

    # ---- Step 1: Load data ----
    csv_path <- file.path(data_dir, "velocity_cells.csv")
    if (!file.exists(csv_path)) stop("velocity_cells.csv not found in ", data_dir)
    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) stop("velocity_cells.csv is empty")

    # ---- Step 2: Detect available columns ----
    has_umap <- all(c("umap_1", "umap_2") %in% colnames(df))
    has_mag  <- "velocity_magnitude" %in% colnames(df)
    has_lt   <- "latent_time" %in% colnames(df)

    # ---- Step 3: Determine color_by column ----
    color_by <- params[["color_by"]]
    if (is.null(color_by) || !color_by %in% colnames(df)) {
      if (has_mag) {
        color_by <- "velocity_magnitude"
      } else {
        # First numeric column as fallback
        num_cols <- colnames(df)[sapply(df, is.numeric)]
        if (length(num_cols) == 0) stop("No numeric column found for coloring")
        color_by <- num_cols[1]
      }
    }
    df[[color_by]] <- suppressWarnings(as.numeric(df[[color_by]]))
    # Replace NA with 0 for magnitude; keep NA for latent_time (shown as grey)
    if (color_by == "velocity_magnitude") {
      df[[color_by]][is.na(df[[color_by]])] <- 0
    }

    # ---- Step 4: Plot mode ----
    plot_type <- params[["plot_type"]]
    if (is.null(plot_type)) {
      plot_type <- if (has_umap) "grid" else "scatter"
    }

    n_bins_raw <- params[["n_bins"]]
    n_bins <- if (is.null(n_bins_raw)) 20L else as.integer(n_bins_raw)
    if (length(n_bins) == 0 || is.na(n_bins) || n_bins < 2) n_bins <- 20L

    # ---- Scatter fallback (no UMAP) ----
    if (!has_umap || plot_type == "scatter") {
      p <- ggplot(df, aes(x = seq_len(nrow(df)), y = .data[[color_by]])) +
        geom_point(alpha = 0.3, size = 0.5, color = "#666666") +
        geom_smooth(method = "loess", se = FALSE, color = "#E41A1C",
                    formula = y ~ x) +
        labs(
          x        = "Cell index",
          y        = color_by,
          title    = "Velocity magnitude distribution",
          subtitle = "UMAP coordinates not available -- showing magnitude distribution"
        ) +
        theme_omics()
      ggsave_standard(p, out_path, width = 8, height = 4)
      return(invisible(NULL))
    }

    # ---- Grid mode ----
    df$bin_x <- cut(df$umap_1, breaks = n_bins, labels = FALSE)
    df$bin_y <- cut(df$umap_2, breaks = n_bins, labels = FALSE)

    bin_df <- df %>%
      group_by(bin_x, bin_y) %>%
      summarise(
        x   = mean(umap_1, na.rm = TRUE),
        y   = mean(umap_2, na.rm = TRUE),
        mag = mean(.data[[color_by]], na.rm = TRUE),
        n   = n(),
        .groups = "drop"
      )
    # Remove bins with NA mag
    bin_df <- bin_df[!is.na(bin_df$mag), ]

    # Percentile-clip mag at 1st and 99th to avoid outlier dominance
    if (nrow(bin_df) > 2) {
      q_lo <- quantile(bin_df$mag, 0.01, na.rm = TRUE)
      q_hi <- quantile(bin_df$mag, 0.99, na.rm = TRUE)
      bin_df$mag <- pmax(pmin(bin_df$mag, q_hi), q_lo)
    }

    # Build plot
    p <- ggplot() +
      # Base layer: all cells as light grey scatter
      geom_point(
        data  = df,
        aes(x = umap_1, y = umap_2),
        color = "#CCCCCC",
        size  = 0.3,
        alpha = 0.10
      ) +
      # Grid layer: binned magnitude dots
      geom_point(
        data  = bin_df,
        aes(x = x, y = y, color = mag, size = n),
        alpha = 0.85
      ) +
      scale_color_viridis_c(
        option   = "plasma",
        name     = color_by,
        na.value = "#CCCCCC"
      ) +
      scale_size_continuous(range = c(1, 5), guide = "none") +
      labs(
        x        = "UMAP 1",
        y        = "UMAP 2",
        title    = "RNA Velocity -- grid summary",
        subtitle = paste0(color_by, " per ", n_bins, "x", n_bins, " grid bins")
      ) +
      theme_omics()

    ggsave_standard(p, out_path, width = 8, height = 6)
  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
