#!/usr/bin/env Rscript
# OmicsClaw: DESeq2 bulk RNA-seq differential expression
#
# Usage:
#   Rscript bulkrna_deseq2.R <counts_csv> <output_dir> <control_prefix> <treat_prefix>
#
# counts_csv: first column = gene names, remaining columns = sample counts
# Samples are assigned to groups by column name prefix matching.

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 4) {
    cat("Usage: Rscript bulkrna_deseq2.R <counts.csv> <output_dir> <control_prefix> <treat_prefix>\n")
    quit(status = 1)
}

counts_file    <- args[1]
output_dir     <- args[2]
control_prefix <- args[3]
treat_prefix   <- args[4]

suppressPackageStartupMessages({
    library(DESeq2)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading count matrix...\n")
    raw <- read.csv(counts_file, row.names = 1, check.names = FALSE)
    counts <- as.matrix(round(raw))

    # Assign conditions by prefix
    sample_names <- colnames(counts)
    condition <- ifelse(startsWith(sample_names, control_prefix), "ctrl",
                 ifelse(startsWith(sample_names, treat_prefix), "treat", NA))

    if (any(is.na(condition)))
        stop(sprintf("Some samples match neither prefix '%s' nor '%s': %s",
            control_prefix, treat_prefix,
            paste(sample_names[is.na(condition)], collapse = ", ")))

    ctrl_n <- sum(condition == "ctrl")
    treat_n <- sum(condition == "treat")
    cat(sprintf("  %d genes x %d samples (%d ctrl, %d treat)\n",
        nrow(counts), ncol(counts), ctrl_n, treat_n))

    # Build DESeq2 dataset
    coldata <- data.frame(condition = factor(condition, levels = c("ctrl", "treat")),
                          row.names = sample_names)

    dds <- DESeqDataSetFromMatrix(countData = counts, colData = coldata, design = ~ condition)

    # Pre-filter low-count genes
    keep <- rowSums(counts(dds) >= 10) >= 2
    dds <- dds[keep, ]
    cat(sprintf("  %d genes after filtering (removed %d low-count genes)\n",
        nrow(dds), sum(!keep)))

    # Run DESeq2
    cat("Running DESeq2...\n")
    dds <- DESeq(dds, quiet = TRUE)
    res <- results(dds, contrast = c("condition", "treat", "ctrl"))

    # Try LFC shrinkage
    coef_name <- resultsNames(dds)[2]
    if (requireNamespace("apeglm", quietly = TRUE)) {
        cat("  Applying apeglm LFC shrinkage...\n")
        res_shrunk <- lfcShrink(dds, coef = coef_name, type = "apeglm", quiet = TRUE)
    } else if (requireNamespace("ashr", quietly = TRUE)) {
        cat("  Applying ashr LFC shrinkage...\n")
        res_shrunk <- lfcShrink(dds, coef = coef_name, type = "ashr", quiet = TRUE)
    } else {
        cat("  No shrinkage package available; using raw estimates.\n")
        res_shrunk <- res
    }

    # Write results
    out <- as.data.frame(res_shrunk)
    out$gene <- rownames(out)
    out <- out[order(out$padj, na.last = TRUE), ]

    write.csv(out, file.path(output_dir, "deseq2_results.csv"), row.names = FALSE, quote = FALSE)

    # Export normalized counts (size-factor normalized)
    norm_counts <- counts(dds, normalized = TRUE)
    write.csv(norm_counts, file.path(output_dir, "normalized_counts.csv"), quote = FALSE)

    # Export variance-stabilized counts (VST for >30 samples, rlog for <30)
    tryCatch({
        if (ncol(dds) >= 30) {
            cat("  Applying VST transformation (>= 30 samples)...\n")
            vsd <- vst(dds, blind = FALSE)
            write.csv(assay(vsd), file.path(output_dir, "vst_counts.csv"), quote = FALSE)
        } else {
            cat("  Applying rlog transformation (< 30 samples)...\n")
            rld <- rlog(dds, blind = FALSE)
            write.csv(assay(rld), file.path(output_dir, "vst_counts.csv"), quote = FALSE)
        }
    }, error = function(e) {
        cat(sprintf("  Warning: transformation failed: %s\n", e$message))
    })

    n_sig <- sum(out$padj < 0.05, na.rm = TRUE)
    n_up <- sum(out$padj < 0.05 & out$log2FoldChange > 0, na.rm = TRUE)
    n_down <- sum(out$padj < 0.05 & out$log2FoldChange < 0, na.rm = TRUE)

    cat(sprintf("Done. %d significant DEGs (padj < 0.05): %d up, %d down\n",
        n_sig, n_up, n_down))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
