#' Export Enrichment Results
#'
#' Functions to export GSEA and ORA results to CSV files and generate summary reports.


#' Export Results to CSV
#'
#' Saves GSEA and ORA results to CSV files.
#'
#' @param gsea_result enrichResult object from run_gsea()
#' @param ora_up enrichResult object from run_ora() for upregulated genes
#' @param ora_down enrichResult object from run_ora() for downregulated genes
#' @param output_prefix Prefix for output filenames (default: "enrichment")
#' @export
#'
#' @examples
#' export_results(gsea_result, ora_up, ora_down, output_prefix = "my_analysis")

export_results <- function(gsea_result = NULL, ora_up = NULL, ora_down = NULL, output_prefix = "enrichment") {

  message("\n=== Exporting Results ===")

  # GSEA results
  if (!is.null(gsea_result) && nrow(gsea_result@result) > 0) {
    gsea_df <- as.data.frame(gsea_result@result)
    gsea_file <- paste0(output_prefix, "_gsea_results.csv")
    write.csv(gsea_df, gsea_file, row.names = FALSE)
    message(sprintf("  Saved: %s (%d rows)", gsea_file, nrow(gsea_df)))
  }

  # ORA results (up)
  if (!is.null(ora_up) && nrow(ora_up@result) > 0) {
    ora_up_df <- as.data.frame(ora_up@result)
    ora_up_df$direction <- "upregulated"
    ora_up_file <- paste0(output_prefix, "_ora_up_results.csv")
    write.csv(ora_up_df, ora_up_file, row.names = FALSE)
    message(sprintf("  Saved: %s (%d rows)", ora_up_file, nrow(ora_up_df)))
  }

  # ORA results (down)
  if (!is.null(ora_down) && nrow(ora_down@result) > 0) {
    ora_down_df <- as.data.frame(ora_down@result)
    ora_down_df$direction <- "downregulated"
    ora_down_file <- paste0(output_prefix, "_ora_down_results.csv")
    write.csv(ora_down_df, ora_down_file, row.names = FALSE)
    message(sprintf("  Saved: %s (%d rows)", ora_down_file, nrow(ora_down_df)))
  }
}


#' Generate Summary Report
#'
#' Creates a markdown summary of top enrichment findings.
#'
#' @param gsea_result enrichResult object from run_gsea()
#' @param ora_up enrichResult object from run_ora() for upregulated genes
#' @param ora_down enrichResult object from run_ora() for downregulated genes
#' @param output_file Output filename (default: "enrichment_summary.md")
#' @export
#'
#' @examples
#' generate_summary(gsea_result, ora_up, ora_down, output_file = "my_summary.md")

#' Export All Results (export_all wrapper)
#'
#' Comprehensive export function that saves all enrichment results including
#' CSV files, markdown summary, and RDS objects for downstream analysis.
#'
#' This is the recommended function to call for complete result export.
#'
#' @param gsea_result enrichResult object from run_gsea()
#' @param ora_up enrichResult object from run_ora() for upregulated genes (optional)
#' @param ora_down enrichResult object from run_ora() for downregulated genes (optional)
#' @param ranked_genes Named numeric vector of ranked genes (optional, for downstream use)
#' @param output_prefix Prefix for output filenames (default: "enrichment")
#' @export
#'
#' @examples
#' export_all(gsea_result, output_prefix = "my_analysis")
#' export_all(gsea_result, ora_up, ora_down, ranked_genes, output_prefix = "my_analysis")
export_all <- function(gsea_result = NULL, ora_up = NULL, ora_down = NULL,
                       ranked_genes = NULL, output_prefix = "enrichment") {

  message("\n=== Exporting All Results ===")

  # 1. Export CSV files
  export_results(gsea_result, ora_up, ora_down, output_prefix)

  # 2. Save enrichment objects as RDS (CRITICAL for downstream skills)
  if (!is.null(gsea_result)) {
    gsea_rds <- paste0(output_prefix, "_gsea_result.rds")
    saveRDS(gsea_result, gsea_rds)
    message(sprintf("  Saved: %s (enrichResult object)", gsea_rds))
    message(sprintf("    (Load with: gsea_result <- readRDS('%s'))", gsea_rds))
  }

  if (!is.null(ora_up)) {
    ora_up_rds <- paste0(output_prefix, "_ora_up_result.rds")
    saveRDS(ora_up, ora_up_rds)
    message(sprintf("  Saved: %s (enrichResult object)", ora_up_rds))
  }

  if (!is.null(ora_down)) {
    ora_down_rds <- paste0(output_prefix, "_ora_down_result.rds")
    saveRDS(ora_down, ora_down_rds)
    message(sprintf("  Saved: %s (enrichResult object)", ora_down_rds))
  }

  # 3. Save ranked genes for downstream use
  if (!is.null(ranked_genes)) {
    ranked_rds <- paste0(output_prefix, "_ranked_genes.rds")
    saveRDS(ranked_genes, ranked_rds)
    message(sprintf("  Saved: %s (ranked gene list)", ranked_rds))
  }

  # 4. Generate markdown summary
  summary_file <- paste0(output_prefix, "_summary.md")
  generate_summary(gsea_result, ora_up, ora_down, output_file = summary_file)

  cat("\n=== Export Complete ===\n\n")
  cat("✓ All results exported successfully!\n\n")
}


generate_summary <- function(gsea_result = NULL, ora_up = NULL, ora_down = NULL,
                             output_file = "enrichment_summary.md") {

  lines <- c("# Functional Enrichment Analysis Summary\n")

  # GSEA Summary
  lines <- c(lines, "## GSEA Results (Primary Analysis)\n")
  if (!is.null(gsea_result) && nrow(gsea_result@result) > 0) {
    sig_gsea <- gsea_result@result[gsea_result@result$p.adjust < 0.05, ]

    # Activated pathways (positive NES)
    activated <- sig_gsea[sig_gsea$NES > 0, ]
    if (nrow(activated) > 0) {
      lines <- c(lines, "### Activated Pathways (NES > 0)\n")
      top_act <- head(activated[order(-activated$NES), ], 10)
      for (i in 1:nrow(top_act)) {
        lines <- c(lines, sprintf("- **%s**: NES=%.2f, FDR=%.2e",
                                  top_act$Description[i], top_act$NES[i], top_act$p.adjust[i]))
      }
      lines <- c(lines, "")
    }

    # Suppressed pathways (negative NES)
    suppressed <- sig_gsea[sig_gsea$NES < 0, ]
    if (nrow(suppressed) > 0) {
      lines <- c(lines, "### Suppressed Pathways (NES < 0)\n")
      top_sup <- head(suppressed[order(suppressed$NES), ], 10)
      for (i in 1:nrow(top_sup)) {
        lines <- c(lines, sprintf("- **%s**: NES=%.2f, FDR=%.2e",
                                  top_sup$Description[i], top_sup$NES[i], top_sup$p.adjust[i]))
      }
      lines <- c(lines, "")
    }
  } else {
    lines <- c(lines, "No significant GSEA results (FDR < 0.05)\n")
  }

  # ORA Summary
  lines <- c(lines, "## ORA Results (Secondary Analysis)\n")

  if (!is.null(ora_up) && nrow(ora_up@result) > 0) {
    sig_up <- ora_up@result[ora_up@result$p.adjust < 0.05, ]
    lines <- c(lines, sprintf("### Upregulated Genes (%d significant pathways)\n", nrow(sig_up)))
    if (nrow(sig_up) > 0) {
      top_up <- head(sig_up[order(sig_up$p.adjust), ], 5)
      for (i in 1:nrow(top_up)) {
        lines <- c(lines, sprintf("- %s (FDR=%.2e)", top_up$Description[i], top_up$p.adjust[i]))
      }
    }
    lines <- c(lines, "")
  }

  if (!is.null(ora_down) && nrow(ora_down@result) > 0) {
    sig_down <- ora_down@result[ora_down@result$p.adjust < 0.05, ]
    lines <- c(lines, sprintf("### Downregulated Genes (%d significant pathways)\n", nrow(sig_down)))
    if (nrow(sig_down) > 0) {
      top_down <- head(sig_down[order(sig_down$p.adjust), ], 5)
      for (i in 1:nrow(top_down)) {
        lines <- c(lines, sprintf("- %s (FDR=%.2e)", top_down$Description[i], top_down$p.adjust[i]))
      }
    }
  }

  writeLines(lines, output_file)
  message(sprintf("  Saved: %s", output_file))
}

