#' Visualization Functions for Enrichment Results
#'
#' This script contains functions to generate standard plots for GSEA and ORA results.

library(enrichplot)
library(ggplot2)
library(dplyr)

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
  library(svglite)
}

#' Save Plot in Both PNG and SVG Formats
#'
#' Internal helper to save plots with graceful fallback for SVG.
#'
#' @param plot ggplot object
#' @param base_path Base filename (without extension)
#' @param width Width in inches
#' @param height Height in inches
#' @param dpi DPI for PNG output
.save_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
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

#' Generate GSEA Dot Plot (PRIMARY - always generate)
#'
#' Creates a dot plot showing activated vs suppressed pathways from GSEA.
#'
#' @param gsea_result enrichResult object from run_gsea()
#' @param top_n Number of top pathways to show (default: 20)
#' @param output_file Output filename (default: "gsea_dotplot.svg")
#' @return ggplot object
#' @export

generate_gsea_dotplot <- function(gsea_result, top_n = 20, output_file = "gsea_dotplot.svg") {
  if (is.null(gsea_result) || nrow(gsea_result@result) == 0) {
    message("No GSEA results to plot")
    return(NULL)
  }

  p <- dotplot(gsea_result, showCategory = top_n, split = ".sign") +
    facet_grid(~.sign) +
    theme_bw() +
    theme(
      axis.text.y = element_text(size = 8),
      strip.text = element_text(size = 10, face = "bold")
    ) +
    ggtitle("GSEA Results: Activated vs Suppressed Pathways")

  .save_plot(p, output_file, width = 12, height = 8)

  return(p)
}


#' Generate GSEA Running Score Plot
#'
#' Creates running enrichment score plots for top pathways.
#'
#' @param gsea_result enrichResult object from run_gsea()
#' @param top_n Number of top pathways to show (default: 4)
#' @param output_file Output filename (default: "gsea_running_score.svg")
#' @return ggplot object
#' @export

generate_gsea_running_plot <- function(gsea_result, top_n = 4, output_file = "gsea_running_score.svg") {
  if (is.null(gsea_result) || nrow(gsea_result@result) == 0) {
    message("No GSEA results to plot")
    return(NULL)
  }

  # Get top pathways by absolute NES
  top_pathways <- gsea_result@result %>%
    arrange(desc(abs(NES))) %>%
    head(top_n) %>%
    pull(ID)

  p <- gseaplot2(gsea_result, geneSetID = top_pathways, pvalue_table = TRUE)

  .save_plot(p, output_file, width = 10, height = 8)

  return(p)
}


#' Generate ORA Bar Plot
#'
#' Creates a bar plot for over-representation analysis results.
#'
#' @param ora_result enrichResult object from run_ora()
#' @param direction Direction label (e.g., "Upregulated", "Downregulated")
#' @param top_n Number of top pathways to show (default: 15)
#' @param output_file Output filename (default: auto-generated from direction)
#' @return ggplot object
#' @export

generate_ora_barplot <- function(ora_result, direction, top_n = 15, output_file = NULL) {
  if (is.null(ora_result) || nrow(ora_result@result) == 0) {
    message(sprintf("No ORA results to plot for %s genes", direction))
    return(NULL)
  }

  if (is.null(output_file)) {
    output_file <- sprintf("ora_%s_barplot.svg", tolower(direction))
  }

  p <- barplot(ora_result, showCategory = top_n) +
    theme_bw() +
    theme(axis.text.y = element_text(size = 8)) +
    ggtitle(sprintf("ORA: %s Genes", direction))

  .save_plot(p, output_file, width = 10, height = 6)

  return(p)
}


#' Generate All Standard Plots
#'
#' Wrapper function to generate all standard GSEA plots at once.
#'
#' @param gsea_result enrichResult object from run_gsea()
#' @param output_dir Output directory for plots (default: current directory)
#' @export
generate_all_plots <- function(gsea_result, output_dir = ".") {
  if (!is.null(output_dir) && output_dir != ".") {
    dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)
  }

  message("\n=== Generating Plots ===")

  # GSEA dot plot
  dotplot_file <- file.path(output_dir, "gsea_dotplot.svg")
  generate_gsea_dotplot(gsea_result, output_file = dotplot_file)

  # GSEA running score plot
  running_file <- file.path(output_dir, "gsea_running_score.svg")
  generate_gsea_running_plot(gsea_result, output_file = running_file)

  cat("\n✓ All plots generated successfully!\n\n")
}


#' === OPTIONAL PLOTS (generate if requested) ===


#' Generate Enrichment Map
#'
#' Creates a network view of related pathways based on gene overlap.
#'
#' @param gsea_result enrichResult object from run_gsea()
#' @param top_n Number of top pathways to show (default: 30)
#' @param output_file Output filename (default: "gsea_emap.svg")
#' @return ggplot object
#' @export

generate_emap <- function(gsea_result, top_n = 30, output_file = "gsea_emap.svg") {
  if (is.null(gsea_result) || nrow(gsea_result@result) == 0) return(NULL)

  # Need pairwise term similarity
  gsea_sim <- pairwise_termsim(gsea_result)

  p <- emapplot(gsea_sim, showCategory = top_n) +
    ggtitle("Enrichment Map: Pathway Relationships")

  .save_plot(p, output_file, width = 12, height = 10)

  return(p)
}


#' Generate Gene-Concept Network Plot
#'
#' Shows which genes are associated with which pathways.
#'
#' @param result enrichResult object
#' @param ranked_genes Named numeric vector of ranked genes (for fold change coloring)
#' @param top_n Number of top pathways to show (default: 5)
#' @param output_file Output filename (default: "cnetplot.svg")
#' @return ggplot object
#' @export

generate_cnetplot <- function(result, ranked_genes, top_n = 5, output_file = "cnetplot.svg") {
  if (is.null(result) || nrow(result@result) == 0) return(NULL)

  p <- cnetplot(result, showCategory = top_n,
                categorySize = "pvalue",
                foldChange = ranked_genes) +
    ggtitle("Gene-Concept Network")

  .save_plot(p, output_file, width = 12, height = 10)

  return(p)
}


#' Generate Ridge Plot
#'
#' Shows distribution of fold changes within each gene set.
#'
#' @param gsea_result enrichResult object from run_gsea()
#' @param top_n Number of top pathways to show (default: 15)
#' @param output_file Output filename (default: "gsea_ridgeplot.svg")
#' @return ggplot object
#' @export

generate_ridgeplot <- function(gsea_result, top_n = 15, output_file = "gsea_ridgeplot.svg") {
  if (is.null(gsea_result) || nrow(gsea_result@result) == 0) return(NULL)

  p <- ridgeplot(gsea_result, showCategory = top_n) +
    theme_bw() +
    ggtitle("GSEA: Fold Change Distribution by Pathway")

  .save_plot(p, output_file, width = 10, height = 8)

  return(p)
}

