#!/usr/bin/env Rscript
# OmicsClaw: DESeq2 pseudobulk differential expression
#
# Usage:
#   Rscript sc_pseudobulk_deseq2.R <h5ad_file> <output_dir> <condition_key>
#     <case_label> <reference_label> <sample_key> <celltype_key>

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 7) {
    cat("Usage: Rscript sc_pseudobulk_deseq2.R <h5ad_file> <output_dir>",
        "<condition_key> <case_label> <reference_label> <sample_key> <celltype_key>\n")
    quit(status = 1)
}

h5ad_file     <- args[1]
output_dir    <- args[2]
condition_key <- args[3]
case_label    <- args[4]
reference_label <- args[5]
sample_key    <- args[6]
celltype_key  <- args[7]

suppressPackageStartupMessages({
    library(DESeq2)
    library(muscat)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat(sprintf("Loading data from %s...\n", h5ad_file))
    sce <- readH5AD(h5ad_file)
    meta <- as.data.frame(SummarizedExperiment::colData(sce))

    # Validate required columns
    for (key in c(condition_key, sample_key, celltype_key)) {
        if (!key %in% colnames(meta))
            stop(sprintf("Column '%s' not found in metadata", key))
    }

    cat(sprintf("  %d cells, condition=%s, case=%s vs ref=%s\n",
        ncol(sce), condition_key, case_label, reference_label))

    # Set up pseudobulk aggregation
    SummarizedExperiment::assay(sce, "counts") <- round(SummarizedExperiment::assay(sce, "X"))
    colData(sce)$sample_id  <- meta[[sample_key]]
    colData(sce)$cluster_id <- meta[[celltype_key]]
    colData(sce)$condition  <- meta[[condition_key]]

    pb <- aggregateData(sce, assay = "counts", fun = "sum",
        by = c("cluster_id", "sample_id"))

    sample_meta <- unique(meta[, c(sample_key, condition_key)])
    rownames(sample_meta) <- sample_meta[[sample_key]]

    out_list <- list()
    for (celltype in assayNames(pb)) {
        counts_ct <- assay(pb, celltype)
        md <- data.frame(sample_id = colnames(counts_ct),
            row.names = colnames(counts_ct))
        md$condition <- sample_meta[md$sample_id, condition_key]

        keep_samples <- !is.na(md$condition) &
            md$condition %in% c(case_label, reference_label)
        counts_ct <- counts_ct[, keep_samples, drop = FALSE]
        md <- md[keep_samples, , drop = FALSE]

        if (ncol(counts_ct) < 2 || length(unique(md$condition)) < 2) {
            cat(sprintf("  Skipping %s: insufficient samples\n", celltype))
            next
        }

        dds <- DESeqDataSetFromMatrix(
            countData = round(counts_ct), colData = md, design = ~ condition)
        keep_genes <- rowSums(counts(dds) >= 10) >= 2
        dds <- dds[keep_genes, ]
        if (nrow(dds) == 0) next

        dds$condition <- relevel(as.factor(dds$condition), ref = reference_label)
        dds <- DESeq(dds, quiet = TRUE)
        res <- results(dds, contrast = c("condition", case_label, reference_label))
        res_df <- as.data.frame(res)
        res_df$gene <- rownames(res_df)
        res_df$cell_type <- celltype
        out_list[[celltype]] <- res_df

        n_sig <- sum(res_df$padj < 0.05, na.rm = TRUE)
        cat(sprintf("  %s: %d significant DEGs\n", celltype, n_sig))
    }

    if (length(out_list) == 0) {
        cat("WARNING: No cell types had enough data for DE analysis\n")
        write.csv(data.frame(), file.path(output_dir, "deseq2_results.csv"),
            row.names = FALSE, quote = FALSE)
    } else {
        out <- do.call(rbind, out_list)
        rownames(out) <- NULL
        write.csv(out, file.path(output_dir, "deseq2_results.csv"),
            row.names = FALSE, quote = FALSE)
        cat(sprintf("Done. %d total DEGs across %d cell types\n",
            nrow(out), length(out_list)))
    }

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
