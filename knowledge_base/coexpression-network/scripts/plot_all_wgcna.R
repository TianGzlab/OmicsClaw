# Generate all WGCNA visualizations
# This script consolidates all plotting steps into a single function

library(WGCNA)

#' Generate all WGCNA plots
#'
#' @param results Results object from run_wgcna_analysis()
#' @param output_dir Directory to save plots (default: current directory)
#' @param output_prefix Prefix for output files (default: "wgcna")
plot_all_wgcna <- function(results, output_dir = ".", output_prefix = "wgcna") {

  cat("\n=== Generating WGCNA Visualizations ===\n\n")

  # Create output directory if needed
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }

  # Plot 1: Module dendrogram
  cat("Generating module dendrogram...\n")
  source("scripts/plot_module_dendrogram.R")
  plot_module_dendrogram(
    results$network$net,
    results$module_colors,
    output_file = file.path(output_dir, paste0(output_prefix, "_module_dendrogram"))
  )

  # Plot 2: Eigengene heatmap
  cat("Generating eigengene heatmap...\n")
  source("scripts/plot_eigengene_heatmap.R")
  plot_eigengene_heatmap(
    results$trait_results$MEs,
    results$meta,
    output_file = file.path(output_dir, paste0(output_prefix, "_eigengene_heatmap"))
  )

  # Plot 3: Module-trait correlation heatmap (if available)
  if (!is.null(results$trait_results)) {
    cat("Generating module-trait correlation heatmap...\n")
    tryCatch({
      # Use built-in WGCNA function for trait correlation plot
      trait_data <- results$meta[, sapply(results$meta, is.numeric), drop = FALSE]
      if (ncol(trait_data) > 0) {
        MEs <- results$trait_results$MEs
        moduleTraitCor <- cor(MEs, trait_data, use = "p")
        moduleTraitPvalue <- corPvalueStudent(moduleTraitCor, nrow(trait_data))

        # Save PNG
        png(file.path(output_dir, paste0(output_prefix, "_module_trait_correlation.png")),
            width = 10, height = 8, units = "in", res = 300)
        textMatrix <- paste(signif(moduleTraitCor, 2), "\n(",
                           signif(moduleTraitPvalue, 1), ")", sep = "")
        dim(textMatrix) <- dim(moduleTraitCor)
        labeledHeatmap(Matrix = moduleTraitCor,
                      xLabels = colnames(trait_data),
                      yLabels = names(MEs),
                      ySymbols = names(MEs),
                      colorLabels = FALSE,
                      colors = blueWhiteRed(50),
                      textMatrix = textMatrix,
                      setStdMargins = FALSE,
                      cex.text = 0.5,
                      zlim = c(-1, 1),
                      main = "Module-Trait Relationships")
        dev.off()
        cat("   Saved:", file.path(output_dir, paste0(output_prefix, "_module_trait_correlation.png")), "\n")

        # Try SVG
        tryCatch({
          svg(file.path(output_dir, paste0(output_prefix, "_module_trait_correlation.svg")),
              width = 10, height = 8)
          labeledHeatmap(Matrix = moduleTraitCor,
                        xLabels = colnames(trait_data),
                        yLabels = names(MEs),
                        ySymbols = names(MEs),
                        colorLabels = FALSE,
                        colors = blueWhiteRed(50),
                        textMatrix = textMatrix,
                        setStdMargins = FALSE,
                        cex.text = 0.5,
                        zlim = c(-1, 1),
                        main = "Module-Trait Relationships")
          dev.off()
          cat("   Saved:", file.path(output_dir, paste0(output_prefix, "_module_trait_correlation.svg")), "\n")
        }, error = function(e) {
          cat("   (SVG export failed)\n")
        })
      }
    }, error = function(e) {
      cat("   (Module-trait correlation plot skipped:", e$message, ")\n")
    })
  }

  # Plot 4: Hub genes barplot
  cat("Generating hub genes barplot...\n")
  source("scripts/plot_hub_genes.R")
  plot_hub_genes(
    results$hub_results$hub_genes,
    output_file = file.path(output_dir, paste0(output_prefix, "_hub_genes_barplot"))
  )

  cat("\n✓ All WGCNA plots generated successfully!\n\n")
}

