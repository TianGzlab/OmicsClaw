# common.R -- Shared helpers for OmicsClaw R Enhanced plotting
#
# Provides: theme_omics(), omics_palette(), ggsave_standard(), parse_kv()
# Must be sourced first by every other R file in viz/r/.

# ---- Library loading ----
suppressPackageStartupMessages({
  library(ggplot2)
  library(scales)
  library(RColorBrewer)
  library(viridis)
})

# ---- Theme ----

#' Clean publication theme for OmicsClaw R Enhanced plots.
#'
#' Inherits theme_classic(), removes redundant axis ticks (top/right),
#' adds a light grey major-y gridline for readability.
#'
#' @param base_size numeric. Base font size (default 11).
#' @return A ggplot2 theme object.
theme_omics <- function(base_size = 11) {
  theme_classic(base_size = base_size) +
    theme(
      axis.ticks.x.top    = element_blank(),
      axis.ticks.y.right  = element_blank(),
      plot.title           = element_text(face = "bold"),
      legend.position      = "right",
      panel.grid.major.y   = element_line(colour = "#E0E0E0", linewidth = 0.3)
    )
}

# ---- Color palettes ----

#' Color palette helper.
#'
#' @param n integer. Number of colors needed.
#' @param type character. "categorical" or "continuous".
#' @return Character vector of hex color strings.
omics_palette <- function(n, type = "categorical") {
  if (type == "continuous") {
    return(viridis::viridis(n, direction = 1))
  }
  # categorical

if (n <= 8) {
    return(RColorBrewer::brewer.pal(max(n, 3), "Set2")[seq_len(n)])
  }
  scales::hue_pal()(n)
}

# ---- Save helper ----

#' Single exit point for all PNG output.
#'
#' Creates the output directory if needed, then calls ggplot2::ggsave.
#'
#' @param plot A ggplot object.
#' @param path Character. Absolute path for the output PNG.
#' @param width numeric. Width in inches (default 8).
#' @param height numeric. Height in inches (default 6).
#' @param dpi numeric. Resolution (default 200).
ggsave_standard <- function(plot, path, width = 8, height = 6, dpi = 200) {
  out_dir <- dirname(path)
  if (!dir.exists(out_dir)) {
    dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  }
  ggplot2::ggsave(
    filename = path,
    plot     = plot,
    width    = width,
    height   = height,
    dpi      = dpi,
    units    = "in",
    bg       = "white"
  )
  cat("Saved:", path, "\n")
}

# ---- CLI key=value parser ----

#' Parse key=value CLI strings to a named list.
#'
#' @param args_vec Character vector of "key=value" strings.
#' @return A named list.
parse_kv <- function(args_vec) {
  if (is.null(args_vec) || length(args_vec) == 0) return(list())
  # Filter out empty strings
  args_vec <- args_vec[nzchar(args_vec)]
  if (length(args_vec) == 0) return(list())

  result <- list()
  for (item in args_vec) {
    eq_pos <- regexpr("=", item, fixed = TRUE)
    if (eq_pos > 0) {
      key <- substr(item, 1, eq_pos - 1)
      val <- substr(item, eq_pos + 1, nchar(item))
      result[[key]] <- val
    }
  }
  result
}

# ---- Standard error handler template ----
# Paste at top of every plot function:
#
# tryCatch({
#   ... your plotting code ...
# }, error = function(e) {
#   cat("ERROR:", conditionMessage(e), "\n", file = stderr())
#   quit(status = 1)
# })
