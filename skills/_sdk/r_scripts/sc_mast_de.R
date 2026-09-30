#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 3) {
    cat("Usage: Rscript sc_mast_de.R <h5ad_file> <output_dir> <groupby> [group1] [group2]\n")
    quit(status = 1)
}

h5ad_file  <- args[1]
output_dir <- args[2]
groupby    <- args[3]
group1     <- if (length(args) >= 4) args[4] else ""
group2     <- if (length(args) >= 5) args[5] else ""

suppressPackageStartupMessages({
    library(MAST)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

run_one <- function(expr_mat, meta, label, comparison_label) {
    fdata <- data.frame(primerid = rownames(expr_mat), row.names = rownames(expr_mat), stringsAsFactors = FALSE)
    sca <- FromMatrix(exprsArray = as.matrix(expr_mat), cData = meta, fData = fdata)
    colData(sca)$cngeneson <- scale(colSums(assay(sca) > 0))
    z <- zlm(~ contrast_group + cngeneson, sca, method = "bayesglm", silent = TRUE, parallel = FALSE)
    s <- summary(z, doLRT = "contrast_groupcase")$datatable
    cont <- s[s$component == "C" & s$contrast == "contrast_groupcase", c("primerid", "coef")]
    disc <- s[s$component == "H" & s$contrast == "contrast_groupcase", c("primerid", "Pr(>Chisq)")]
    out <- merge(cont, disc, by = "primerid", all = TRUE)
    colnames(out) <- c("gene", "logFC", "pvalue")
    out$padj <- p.adjust(out$pvalue, method = "BH")
    out$group <- label
    out$comparison <- comparison_label
    out
}

tryCatch({
    sce <- readH5AD(h5ad_file)
    meta <- as.data.frame(SummarizedExperiment::colData(sce))
    if (!groupby %in% colnames(meta)) stop(sprintf("Column '%s' not found in metadata", groupby))

    expr_mat <- SummarizedExperiment::assay(sce, "X")
    if (nrow(expr_mat) == nrow(meta)) {
        expr_mat <- t(expr_mat)
    }
    if (is(expr_mat, "sparseMatrix")) expr_mat <- as.matrix(expr_mat)
    rownames(expr_mat) <- rownames(sce)
    colnames(expr_mat) <- colnames(sce)

    results <- list()
    if (nzchar(group1) && nzchar(group2)) {
        keep <- meta[[groupby]] %in% c(group1, group2)
        meta_sub <- meta[keep, , drop = FALSE]
        expr_sub <- expr_mat[, keep, drop = FALSE]
        meta_sub$contrast_group <- factor(ifelse(meta_sub[[groupby]] == group1, "case", "ref"), levels = c("ref", "case"))
        results[[1]] <- run_one(expr_sub, meta_sub, group1, sprintf("%s vs %s", group1, group2))
    } else {
        groups <- unique(as.character(meta[[groupby]]))
        for (grp in groups) {
            meta_sub <- meta
            meta_sub$contrast_group <- factor(ifelse(as.character(meta_sub[[groupby]]) == grp, "case", "ref"), levels = c("ref", "case"))
            results[[grp]] <- run_one(expr_mat, meta_sub, grp, sprintf("%s vs rest", grp))
        }
    }

    out <- do.call(rbind, results)
    rownames(out) <- NULL
    write.csv(out, file.path(output_dir, "mast_results.csv"), quote = FALSE, row.names = FALSE)
}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
