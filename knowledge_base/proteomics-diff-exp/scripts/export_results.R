# Export proteomics DE results and analysis objects
# Generates all output files including RDS for downstream skills

#' Export all proteomics DE results
#'
#' @param fit_deqms DEqMS fit object from basic_workflow.R
#' @param deqms_results DEqMS results data.frame from basic_workflow.R
#' @param protein_matrix Normalized protein intensity matrix
#' @param metadata Sample metadata data.frame
#' @param psm_counts Named vector of PSM counts (optional, extracted from fit if NULL)
#' @param comparison_name Name of the comparison
#' @param output_dir Output directory (default: "results")
#' @param padj_threshold Adjusted p-value threshold (default: 0.05)
#' @param lfc_threshold Log2 fold change threshold (default: 0.58 = 1.5-fold)
#' @export
export_all <- function(fit_deqms, deqms_results, protein_matrix, metadata,
                        psm_counts = NULL, comparison_name = NULL,
                        output_dir = "results",
                        padj_threshold = 0.05, lfc_threshold = 0.58) {

    cat("\n=== Exporting Proteomics DE Results ===\n\n")

    # Create output directory
    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
        cat("Created directory:", output_dir, "\n\n")
    }

    # Infer comparison name if not provided
    if (is.null(comparison_name) && exists("comparison_name", envir = parent.frame())) {
        comparison_name <- get("comparison_name", envir = parent.frame())
    }
    if (is.null(comparison_name)) comparison_name <- "comparison"

    # Get PSM counts from fit if not provided
    if (is.null(psm_counts) && !is.null(fit_deqms$count)) {
        psm_counts <- fit_deqms$count
    }

    # 1. All DEqMS results
    cat("1. Exporting all DEqMS results...\n")
    write.csv(deqms_results,
              file.path(output_dir, "all_results.csv"),
              row.names = FALSE)
    cat("   Saved: all_results.csv (", nrow(deqms_results), " proteins)\n\n")

    # 2. Significant results
    cat("2. Exporting significant results...\n")
    sig <- deqms_results[!is.na(deqms_results$sca.adj.pval) &
                          deqms_results$sca.adj.pval < padj_threshold &
                          abs(deqms_results$logFC) > lfc_threshold, ]
    sig <- sig[order(sig$sca.adj.pval), ]
    write.csv(sig,
              file.path(output_dir, "significant_results.csv"),
              row.names = FALSE)
    n_up <- sum(sig$logFC > 0)
    n_down <- sum(sig$logFC < 0)
    cat("   Saved: significant_results.csv (", nrow(sig), " proteins:",
        n_up, "up,", n_down, "down)\n")
    cat("   Thresholds: sca.adj.pval <", padj_threshold,
        ", |logFC| >", lfc_threshold, "\n\n")

    # 3. Normalized protein matrix
    cat("3. Exporting normalized protein matrix...\n")
    write.csv(protein_matrix,
              file.path(output_dir, "normalized_protein_matrix.csv"),
              row.names = TRUE)
    cat("   Saved: normalized_protein_matrix.csv (",
        nrow(protein_matrix), "x", ncol(protein_matrix), ")\n\n")

    # 4. Analysis object (CRITICAL for downstream skills)
    cat("4. Saving analysis object (RDS)...\n")
    analysis_object <- list(
        fit_deqms = fit_deqms,
        deqms_results = deqms_results,
        protein_matrix = protein_matrix,
        metadata = metadata,
        psm_counts = psm_counts,
        comparison_name = comparison_name,
        thresholds = list(padj = padj_threshold, lfc = lfc_threshold)
    )
    saveRDS(analysis_object, file.path(output_dir, "analysis_object.rds"))
    cat("   Saved: analysis_object.rds\n")
    cat("   (Load with: obj <- readRDS('results/analysis_object.rds'))\n")
    cat("   Contains: fit_deqms, deqms_results, protein_matrix, metadata, psm_counts\n\n")

    # 5. PSM counts
    if (!is.null(psm_counts)) {
        cat("5. Exporting PSM counts...\n")
        psm_df <- data.frame(
            protein = names(psm_counts),
            psm_count = as.integer(psm_counts)
        )
        psm_df <- psm_df[order(psm_df$psm_count, decreasing = TRUE), ]
        write.csv(psm_df,
                  file.path(output_dir, "psm_counts.csv"),
                  row.names = FALSE)
        cat("   Saved: psm_counts.csv (", nrow(psm_df), " proteins)\n\n")
    }

    # 6. Top 100 proteins
    cat("6. Exporting top 100 proteins...\n")
    top100 <- head(deqms_results[order(deqms_results$sca.adj.pval), ], 100)
    write.csv(top100,
              file.path(output_dir, "top100_proteins.csv"),
              row.names = FALSE)
    cat("   Saved: top100_proteins.csv\n\n")

    # 7. Markdown report (always generated)
    cat("7. Generating markdown report...\n")
    .generate_markdown_report(deqms_results, metadata, comparison_name,
                               output_dir, padj_threshold, lfc_threshold)
    cat("   Saved: analysis_report.md\n\n")

    # 8. PDF report (optional)
    cat("8. Generating PDF report...\n")
    tryCatch({
        source("scripts/generate_report.R")
        pdf_path <- generate_report(deqms_results, metadata,
                                     comparison_name = comparison_name,
                                     output_dir = output_dir,
                                     padj_threshold = padj_threshold,
                                     lfc_threshold = lfc_threshold)
        if (!is.null(pdf_path)) {
            cat("   Saved: analysis_report.pdf\n\n")
        }
    }, error = function(e) {
        cat("   PDF generation skipped:", conditionMessage(e), "\n")
        cat("   (Markdown report still available)\n\n")
    })

    # Summary
    cat("\n=== Export Complete ===\n")
    cat("All files saved to:", output_dir, "\n")
    cat("Files:\n")
    output_files <- list.files(output_dir, pattern = "\\.(csv|rds|md|pdf)$")
    for (f in output_files) {
        cat("  -", f, "\n")
    }
    cat("\n")
}


# ---- Internal: Markdown report ----
.generate_markdown_report <- function(deqms_results, metadata,
                                       comparison_name, output_dir,
                                       padj_threshold, lfc_threshold) {

    n_total <- nrow(deqms_results)
    sig <- deqms_results[!is.na(deqms_results$sca.adj.pval) &
                          deqms_results$sca.adj.pval < padj_threshold &
                          abs(deqms_results$logFC) > lfc_threshold, ]
    n_sig <- nrow(sig)
    n_up <- sum(sig$logFC > 0)
    n_down <- sum(sig$logFC < 0)

    top10 <- head(deqms_results[order(deqms_results$sca.adj.pval), ], 10)

    lines <- c(
        "# Proteomics Differential Expression Report",
        "",
        paste("**Date:**", format(Sys.Date(), "%B %d, %Y")),
        paste("**Comparison:**", comparison_name),
        "",
        "## Summary",
        "",
        paste("- Total proteins tested:", format(n_total, big.mark = ",")),
        paste("- Significant proteins:", n_sig),
        paste("  - Upregulated:", n_up),
        paste("  - Downregulated:", n_down),
        paste("- Samples:", nrow(metadata)),
        paste("- Conditions:", paste(levels(metadata$condition), collapse = ", ")),
        "",
        "## Methods",
        "",
        "Analysis performed using limma + DEqMS pipeline:",
        "1. PSM-to-protein aggregation (medianSweeping)",
        "2. Missing value filtering (>50% per condition)",
        "3. MinProb imputation",
        "4. Median centering normalization",
        "5. limma linear model (lmFit + contrasts.fit + eBayes)",
        "6. DEqMS PSM-count-aware variance correction (spectraCounteBayes)",
        "",
        "## Top 10 Differentially Expressed Proteins",
        "",
        "| Protein | logFC | DEqMS adj.pval | limma adj.pval | PSM count |",
        "|---------|-------|----------------|----------------|-----------|"
    )

    for (i in seq_len(nrow(top10))) {
        lines <- c(lines, sprintf("| %s | %.3f | %.2e | %.2e | %d |",
            top10$protein[i], top10$logFC[i],
            top10$sca.adj.pval[i], top10$adj.P.Val[i],
            top10$count[i]))
    }

    lines <- c(lines, "",
        "## References",
        "",
        "1. Zhu Y, et al. DEqMS: A Method for Accurate Variance Estimation in Differential Protein Expression Analysis. *MCP*. 2020;19(6):1047-1057.",
        "2. Ritchie ME, et al. limma powers differential expression analyses. *NAR*. 2015;43(7):e47.",
        ""
    )

    writeLines(lines, file.path(output_dir, "analysis_report.md"))
}

