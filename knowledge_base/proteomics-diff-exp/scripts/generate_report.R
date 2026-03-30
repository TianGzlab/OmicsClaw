# Generate PDF analysis report for proteomics DE analysis
# Uses rmarkdown with PDF output (optional dependency)

#' Generate PDF analysis report
#'
#' @param deqms_results DEqMS results data.frame
#' @param metadata Sample metadata data.frame
#' @param comparison_name Name of the comparison (e.g., "miR372-ctrl")
#' @param output_dir Directory containing plots and for output
#' @param n_proteins Total number of proteins tested
#' @return Path to generated PDF, or NULL if generation failed
#' @export
generate_report <- function(deqms_results, metadata,
                             comparison_name = "Treatment vs Control",
                             output_dir = "results",
                             n_proteins = NULL,
                             padj_threshold = 0.05,
                             lfc_threshold = 0.58) {

    # Check rmarkdown availability
    if (!requireNamespace("rmarkdown", quietly = TRUE)) {
        cat("   rmarkdown not installed - skipping PDF report\n")
        cat("   Install with: install.packages('rmarkdown')\n")
        return(NULL)
    }

    # Check for LaTeX
    has_latex <- FALSE
    if (requireNamespace("tinytex", quietly = TRUE)) {
        has_latex <- tinytex::is_tinytex() || nchar(Sys.which("xelatex")) > 0
    }
    if (!has_latex) {
        has_latex <- nchar(Sys.which("pdflatex")) > 0 || nchar(Sys.which("xelatex")) > 0
    }

    if (!has_latex) {
        cat("   No LaTeX installation found - skipping PDF report\n")
        cat("   Install with: tinytex::install_tinytex()\n")
        return(NULL)
    }

    cat("   Generating PDF report...\n")

    # Compute summary stats
    if (is.null(n_proteins)) n_proteins <- nrow(deqms_results)
    n_sig <- sum(deqms_results$sca.adj.pval < padj_threshold &
                  abs(deqms_results$logFC) > lfc_threshold, na.rm = TRUE)
    n_up <- sum(deqms_results$sca.adj.pval < padj_threshold &
                 deqms_results$logFC > lfc_threshold, na.rm = TRUE)
    n_down <- sum(deqms_results$sca.adj.pval < padj_threshold &
                   deqms_results$logFC < -lfc_threshold, na.rm = TRUE)
    n_samples <- nrow(metadata)
    conditions <- paste(levels(metadata$condition), collapse = ", ")

    # Top 20 proteins table
    top20 <- head(deqms_results[order(deqms_results$sca.adj.pval), ], 20)
    top20_table <- data.frame(
        Protein = top20$protein,
        logFC = sprintf("%.3f", top20$logFC),
        `DEqMS.adj.pval` = sprintf("%.2e", top20$sca.adj.pval),
        `limma.adj.pval` = sprintf("%.2e", top20$adj.P.Val),
        PSM.count = top20$count,
        check.names = FALSE
    )

    # Find available plot files
    plot_files <- list.files(output_dir, pattern = "\\.png$", full.names = TRUE)

    # Build Rmd content
    rmd_content <- paste0(
'---
title: "Proteomics Differential Expression Report"
subtitle: "limma + DEqMS Analysis"
date: "', format(Sys.Date(), "%B %d, %Y"), '"
output:
  pdf_document:
    toc: true
    toc_depth: 2
    number_sections: true
---

