# Export all WGCNA results

library(WGCNA)

#' Export all WGCNA results (including RDS objects for downstream skills)
#'
#' @param results Results object from run_wgcna_analysis()
#' @param output_dir Directory to save results (default: "wgcna_results")
#' @param output_prefix Prefix for output files (default: "wgcna")
export_all <- function(results, output_dir = "wgcna_results", output_prefix = "wgcna") {

  cat("\n=== Exporting WGCNA Results ===\n\n")

  # Create output directory if needed
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }

  # Extract components from results
  gene_info <- results$hub_results$gene_info
  hub_genes <- results$hub_results$hub_genes
  trait_results <- results$trait_results

  # 1. Export gene-module assignments
  csv_path <- file.path(output_dir, paste0(output_prefix, "_gene_modules.csv"))
  write.csv(gene_info, csv_path, row.names = FALSE)
  cat("  Saved:", csv_path, "\n")

  # 2. Export hub genes
  hub_df <- do.call(rbind, lapply(names(hub_genes), function(mod) {
    df <- hub_genes[[mod]]
    df$module <- mod
    df
  }))
  csv_path <- file.path(output_dir, paste0(output_prefix, "_hub_genes.csv"))
  write.csv(hub_df, csv_path, row.names = FALSE)
  cat("  Saved:", csv_path, "\n")

  # 3. Export module-trait correlations
  csv_path <- file.path(output_dir, paste0(output_prefix, "_module_trait_cor.csv"))
  write.csv(trait_results$results, csv_path, row.names = FALSE)
  cat("  Saved:", csv_path, "\n")

  # 4. Export module eigengenes
  csv_path <- file.path(output_dir, paste0(output_prefix, "_eigengenes.csv"))
  write.csv(trait_results$MEs, csv_path)
  cat("  Saved:", csv_path, "\n")

  # 5. Save analysis objects as RDS for downstream skills (CRITICAL)
  cat("\n  Saving analysis objects for downstream use:\n")

  rds_path <- file.path(output_dir, paste0(output_prefix, "_network.rds"))
  saveRDS(results$network, rds_path)
  cat("    • wgcna_network.rds\n")
  cat("      (Load with: net <- readRDS('", basename(rds_path), "'))\n", sep = "")

  rds_path <- file.path(output_dir, paste0(output_prefix, "_module_colors.rds"))
  saveRDS(results$module_colors, rds_path)
  cat("    • wgcna_module_colors.rds\n")
  cat("      (Load with: colors <- readRDS('", basename(rds_path), "'))\n", sep = "")

  rds_path <- file.path(output_dir, paste0(output_prefix, "_expression_matrix.rds"))
  saveRDS(results$datExpr, rds_path)
  cat("    • wgcna_expression_matrix.rds\n")
  cat("      (Load with: expr <- readRDS('", basename(rds_path), "'))\n", sep = "")

  rds_path <- file.path(output_dir, paste0(output_prefix, "_full_results.rds"))
  saveRDS(results, rds_path)
  cat("    • wgcna_full_results.rds (complete results object)\n")
  cat("      (Load with: results <- readRDS('", basename(rds_path), "'))\n", sep = "")

  # 6. Create summary report
  cat("\n  Creating summary report...\n")
  summary_lines <- c(
    "# WGCNA Co-expression Network Analysis Summary\n",
    paste("**Total genes analyzed:**", nrow(gene_info)),
    paste("**Total samples:**", nrow(trait_results$MEs)),
    paste("**Number of modules:**", length(unique(gene_info$module)) - 1, "(excluding grey)\n"),
    "## Module Sizes"
  )

  module_sizes <- table(gene_info$module)
  for (mod in names(sort(module_sizes, decreasing = TRUE))) {
    if (mod != "grey") {
      summary_lines <- c(summary_lines, paste("-", mod, ":", module_sizes[mod], "genes"))
    }
  }

  summary_lines <- c(summary_lines, "\n## Top Hub Genes per Module")
  for (mod in names(hub_genes)) {
    top_hubs <- head(hub_genes[[mod]]$gene, 5)
    summary_lines <- c(summary_lines, paste("-", mod, ":", paste(top_hubs, collapse = ", ")))
  }

  report_path <- file.path(output_dir, paste0(output_prefix, "_report.md"))
  writeLines(summary_lines, report_path)
  cat("  Saved:", report_path, "\n")

  cat("\n=== Export Complete ===\n\n")
}

# Keep old function name for backwards compatibility
export_wgcna_results <- function(gene_info, hub_genes, trait_results,
                                  output_prefix = "wgcna") {
  .Deprecated("export_all", msg = "export_wgcna_results() is deprecated. Use export_all() instead.")

  # Create minimal results object for compatibility
  results <- list(
    hub_results = list(gene_info = gene_info, hub_genes = hub_genes),
    trait_results = trait_results,
    datExpr = NULL,
    network = NULL,
    module_colors = NULL
  )

  export_all(results, output_dir = ".", output_prefix = output_prefix)
}

