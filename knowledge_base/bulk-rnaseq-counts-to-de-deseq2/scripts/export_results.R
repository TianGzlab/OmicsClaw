# Export DESeq2 results and normalized data
# Functions for saving results tables and transformed counts

library(DESeq2)

#' Export all DESeq2 results to CSV
#'
#' @param res DESeqResults object
#' @param output_file Output file path (CSV)
#'
#' @export
export_results <- function(res, output_file = "deseq2_results.csv") {
    write.csv(as.data.frame(res), file = output_file, row.names = TRUE)
    cat("All results saved to:", output_file, "\n")
    cat("  Total genes:", nrow(res), "\n")
}

#' Export significant genes only
#'
#' @param res DESeqResults object
#' @param padj_threshold Adjusted p-value threshold (default: 0.05)
#' @param lfc_threshold Log2 fold change threshold (default: 0, no filtering)
#' @param output_file Output file path (CSV)
#'
#' @export
export_significant <- function(res, padj_threshold = 0.05, lfc_threshold = 0,
                                output_file = "deseq2_significant.csv") {
    sig <- subset(res, padj < padj_threshold & abs(log2FoldChange) > lfc_threshold)

    write.csv(as.data.frame(sig), file = output_file, row.names = TRUE)

    cat("Significant genes saved to:", output_file, "\n")
    cat("  Threshold: padj <", padj_threshold, ", |log2FC| >", lfc_threshold, "\n")
    cat("  Total significant:", nrow(sig), "\n")
    cat("    Upregulated:", sum(sig$log2FoldChange > 0, na.rm = TRUE), "\n")
    cat("    Downregulated:", sum(sig$log2FoldChange < 0, na.rm = TRUE), "\n")
}

#' Export normalized counts
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param output_file Output file path (CSV)
#'
#' @export
export_normalized_counts <- function(dds, output_file = "normalized_counts.csv") {
    norm_counts <- counts(dds, normalized = TRUE)
    write.csv(norm_counts, file = output_file, row.names = TRUE)
    cat("Normalized counts saved to:", output_file, "\n")
}

#' Export variance-stabilized counts
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param output_file Output file path (CSV)
#' @param use_vst Use VST (TRUE) or rlog (FALSE)
#'
#' @export
export_transformed_counts <- function(dds, output_file = "vst_transformed.csv",
                                      use_vst = TRUE) {
    if (use_vst) {
        transformed <- vst(dds, blind = FALSE)
        cat("Using VST transformation\n")
    } else {
        transformed <- rlog(dds, blind = FALSE)
        cat("Using rlog transformation\n")
        # Update filename if using rlog
        if (output_file == "vst_transformed.csv") {
            output_file <- "rlog_transformed.csv"
        }
    }

    write.csv(assay(transformed), file = output_file, row.names = TRUE)
    cat("Transformed counts saved to:", output_file, "\n")
}

#' Export top genes by significance or fold change
#'
#' @param res DESeqResults object
#' @param n Number of top genes to export (default: 100)
#' @param order_by Order by 'padj' or 'lfc' (default: 'padj')
#' @param output_file Output file path (CSV)
#'
#' @export
export_top_genes <- function(res, n = 100, order_by = "padj",
                             output_file = NULL) {
    if (order_by == "padj") {
        res_ordered <- res[order(res$padj), ]
        if (is.null(output_file)) output_file <- paste0("top", n, "_by_padj.csv")
        cat("Ordering by adjusted p-value\n")
    } else if (order_by == "lfc") {
        res_ordered <- res[order(abs(res$log2FoldChange), decreasing = TRUE), ]
        if (is.null(output_file)) output_file <- paste0("top", n, "_by_lfc.csv")
        cat("Ordering by absolute log2 fold change\n")
    } else {
        stop("order_by must be 'padj' or 'lfc'")
    }

    top_genes <- head(res_ordered, n)
    write.csv(as.data.frame(top_genes), file = output_file, row.names = TRUE)

    cat("Top", n, "genes saved to:", output_file, "\n")
}

#' Export all standard outputs
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param res DESeqResults object
#' @param res_shrunk DESeqResults object with LFC shrinkage (optional)
#' @param output_dir Output directory (default: "deseq2_results")
#' @param padj_threshold Significance threshold for filtering (default: 0.05)
#' @param lfc_threshold Fold change threshold for filtering (default: 1)
#'
#' @export
export_all <- function(dds, res, res_shrunk = NULL,
                       output_dir = "deseq2_results",
                       padj_threshold = 0.05,
                       lfc_threshold = 1) {

    cat("\n=== Exporting DESeq2 Results ===\n\n")

    # Create output directory
    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
        cat("Created directory:", output_dir, "\n\n")
    }

    # Export all results
    cat("1. Exporting all results...\n")
    export_results(res, file.path(output_dir, "deseq2_results.csv"))
    cat("\n")

    # Export shrunk results if available
    if (!is.null(res_shrunk)) {
        cat("2. Exporting shrunk LFC results...\n")
        export_results(res_shrunk, file.path(output_dir, "deseq2_results_shrunk.csv"))
        cat("\n")
    }

    # Export significant genes
    cat("3. Exporting significant genes...\n")
    export_significant(res,
                      padj_threshold = padj_threshold,
                      lfc_threshold = lfc_threshold,
                      output_file = file.path(output_dir, "deseq2_significant.csv"))
    cat("\n")

    # Export normalized counts
    cat("4. Exporting normalized counts...\n")
    export_normalized_counts(dds, file.path(output_dir, "normalized_counts.csv"))
    cat("\n")

    # Save DESeqDataSet object
    cat("5. Saving DESeqDataSet object...\n")
    saveRDS(dds, file.path(output_dir, "dds_object.rds"))
    cat("DESeqDataSet saved to: dds_object.rds\n")
    cat("  (Load with: dds <- readRDS('dds_object.rds'))\n\n")

    # Export transformed counts
    cat("6. Exporting transformed counts...\n")
    use_vst <- ncol(dds) > 30
    export_transformed_counts(dds,
                             file.path(output_dir, "vst_transformed.csv"),
                             use_vst = use_vst)
    cat("\n")

    # Export top genes
    cat("7. Exporting top genes...\n")
    export_top_genes(res, n = 100,
                    output_file = file.path(output_dir, "top100_genes.csv"))

    cat("\n=== Export Complete ===\n")
    cat("All files saved to:", output_dir, "\n")
}

# Example usage:
# library(DESeq2)
# source("scripts/export_results.R")
#
# # After DESeq2 analysis
# dds <- DESeq(dds)
# res <- results(dds)
# res_shrunk <- lfcShrink(dds, coef = "condition_treated_vs_control", type = "apeglm")
#
# # Export all standard outputs
# export_all(dds, res, res_shrunk, output_dir = "deseq2_results")
#
# # Or export individual files
# export_results(res, "all_results.csv")
# export_significant(res, padj_threshold = 0.05, lfc_threshold = 1)
# export_normalized_counts(dds, "normalized.csv")

