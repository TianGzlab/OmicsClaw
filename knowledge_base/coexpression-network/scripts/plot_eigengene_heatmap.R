# Create module eigengene heatmap using ComplexHeatmap

library(WGCNA)
library(ComplexHeatmap)
library(circlize)

#' Create module eigengene heatmap (PNG + SVG)
#'
#' @param MEs Module eigengenes
#' @param meta Sample metadata
#' @param output_file Output file path (without extension, or will be stripped)
plot_eigengene_heatmap <- function(MEs, meta, output_file = "eigengene_heatmap") {

  # Remove extension if provided
  output_file <- sub("\\.(svg|png)$", "", output_file)

  # Prepare annotation from metadata (factor/character columns only)
  annotation_df <- meta[, sapply(meta, function(x) is.factor(x) || is.character(x)), drop = FALSE]

  # Create HeatmapAnnotation if annotation columns exist
  if (ncol(annotation_df) > 0) {
    ha <- HeatmapAnnotation(
      df = annotation_df,
      show_annotation_name = TRUE,
      annotation_name_side = "left"
    )
  } else {
    ha <- NULL
  }

  # Create color function for heatmap
  col_fun <- colorRamp2(c(min(MEs), 0, max(MEs)), c("blue", "white", "red"))

  # Create heatmap
  ht <- Heatmap(
    t(MEs),
    name = "Eigengene",
    col = col_fun,
    top_annotation = ha,
    show_column_names = FALSE,
    cluster_columns = TRUE,
    cluster_rows = TRUE,
    column_title = "Module Eigengene Expression",
    row_names_side = "left",
    heatmap_legend_param = list(title = "Expression")
  )

  # Save PNG (always)
  png_path <- paste0(output_file, ".png")
  png(png_path, width = 12, height = 8, units = "in", res = 300)
  draw(ht)
  dev.off()
  cat("   Saved:", png_path, "\n")

  # Try SVG with fallback
  svg_path <- paste0(output_file, ".svg")
  tryCatch({
    svg(svg_path, width = 12, height = 8)
    draw(ht)
    dev.off()
    cat("   Saved:", svg_path, "\n")
  }, error = function(e) {
    cat("   (SVG export failed)\n")
  })
}

