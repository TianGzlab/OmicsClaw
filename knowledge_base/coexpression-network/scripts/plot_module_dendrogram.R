# Create module dendrogram with colors

library(WGCNA)

#' Create module dendrogram with colors (PNG + SVG)
#'
#' @param net Network object from blockwiseModules
#' @param module_colors Module color assignments
#' @param output_file Output file path (without extension, or will be stripped)
plot_module_dendrogram <- function(net, module_colors, output_file = "module_dendrogram") {

  # Remove extension if provided
  output_file <- sub("\\.(svg|png)$", "", output_file)

  # Save PNG (always)
  png_path <- paste0(output_file, ".png")
  png(png_path, width = 12, height = 8, units = "in", res = 300)
  plotDendroAndColors(
    net$dendrograms[[1]],
    module_colors[net$blockGenes[[1]]],
    "Module colors",
    dendroLabels = FALSE,
    hang = 0.03,
    addGuide = TRUE,
    guideHang = 0.05,
    main = "Gene Dendrogram and Module Colors"
  )
  dev.off()
  cat("   Saved:", png_path, "\n")

  # Try SVG with fallback
  svg_path <- paste0(output_file, ".svg")
  tryCatch({
    svg(svg_path, width = 12, height = 8)
    plotDendroAndColors(
      net$dendrograms[[1]],
      module_colors[net$blockGenes[[1]]],
      "Module colors",
      dendroLabels = FALSE,
      hang = 0.03,
      addGuide = TRUE,
      guideHang = 0.05,
      main = "Gene Dendrogram and Module Colors"
    )
    dev.off()
    cat("   Saved:", svg_path, "\n")
  }, error = function(e) {
    cat("   (SVG export failed)\n")
  })
}

