# Create hub gene network visualization

library(WGCNA)
library(ggplot2)
library(ggprism)

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
  library(svglite)
}

#' Save plot in both PNG and SVG formats with graceful fallback
#'
#' @param plot ggplot object
#' @param base_path Base file path (without extension)
#' @param width Width in inches
#' @param height Height in inches
#' @param dpi Resolution for PNG
.save_plot <- function(plot, base_path, width = 12, height = 8, dpi = 300) {
  # Always save PNG
  png_path <- sub("\\.(svg|png)$", ".png", base_path)
  ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
  cat("   Saved:", png_path, "\n")

  # Always try SVG - try ggsave first, fall back to svg() device
  svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
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

#' Create hub gene network visualization
#'
#' @param hub_genes List of hub genes per module
#' @param output_file Output file path (without extension, or will be stripped)
plot_hub_genes <- function(hub_genes, output_file = "hub_genes_barplot") {

  # Combine hub genes from all modules
  hub_df <- do.call(rbind, lapply(names(hub_genes), function(mod) {
    df <- hub_genes[[mod]][1:min(5, nrow(hub_genes[[mod]])), ]
    df$module <- mod
    df
  }))

  # Create plot with ggprism theme
  p <- ggplot(hub_df, aes(x = reorder(gene, kWithin), y = kWithin, fill = module)) +
    geom_bar(stat = "identity") +
    coord_flip() +
    facet_wrap(~module, scales = "free_y") +
    labs(x = "Gene", y = "Intramodular Connectivity",
         title = "Top Hub Genes per Module") +
    theme_prism(base_size = 12) +
    theme(legend.position = "none")

  # Save to both PNG and SVG
  plot_height <- max(8, nrow(hub_df) * 0.3)
  .save_plot(p, output_file, width = 12, height = plot_height, dpi = 300)
}

