# Plotting Helper Functions for WGCNA
# Provides robust plot saving with PNG + SVG export and graceful fallback

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
    library(svglite)
}

#' Save base R plot to both PNG and SVG formats
#'
#' Helper function for WGCNA plots that use base R graphics.
#' Takes a plotting expression and saves it to both PNG and SVG.
#'
#' @param plot_expr Expression that creates the plot (use substitute() or quote())
#' @param base_path Path without extension (e.g., "output/dendrogram")
#' @param width Plot width in inches (default: 12)
#' @param height Plot height in inches (default: 8)
#' @param dpi Resolution for PNG (default: 300)
#'
#' @examples
#' .save_base_plot(
#'   quote(plotDendroAndColors(net$dendrograms[[1]], colors, "Modules")),
#'   "module_dendrogram",
#'   width = 12,
#'   height = 8
#' )
.save_base_plot <- function(plot_expr, base_path, width = 12, height = 8, dpi = 300) {

    # Remove extension if provided
    base_path <- sub("\\.(svg|png)$", "", base_path)

    # Always save PNG first
    png_path <- paste0(base_path, ".png")
    png(png_path, width = width, height = height, units = "in", res = dpi)
    eval(plot_expr)
    dev.off()
    cat("   Saved:", png_path, "\n")

    # Always try SVG - base R svg() device
    svg_path <- paste0(base_path, ".svg")
    tryCatch({
        svg(svg_path, width = width, height = height)
        eval(plot_expr)
        dev.off()
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        cat("   (SVG export failed)\n")
    })
}

#' Save ggplot object to both PNG and SVG formats
#'
#' Helper function for ggplot-based plots (if any are added to this skill).
#'
#' @param plot ggplot object to save
#' @param base_path Path without extension
#' @param width Plot width in inches
#' @param height Plot height in inches
#' @param dpi Resolution for PNG
.save_ggplot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {

    # Remove extension if provided
    base_path <- sub("\\.(svg|png)$", "", base_path)

    # Always save PNG
    png_path <- paste0(base_path, ".png")
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")

    # Always try SVG - try ggsave first, fall back to svg() device
    svg_path <- paste0(base_path, ".svg")
    tryCatch({
        ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        # If ggsave fails, try base R svg() device directly
        tryCatch({
            svg(svg_path, width = width, height = height)
            print(plot)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e2) {
            cat("   (SVG export failed)\n")
        })
    })
}

