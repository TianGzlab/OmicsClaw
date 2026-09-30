#!/usr/bin/env Rscript
# OmicsClaw: scDblFinder doublet detection
#
# Usage:
#   Rscript sc_scdblfinder.R <h5ad_file> <output_dir> [expected_doublet_rate]

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript sc_scdblfinder.R <h5ad_file> <output_dir> [expected_doublet_rate]\n")
    quit(status = 1)
}

h5ad_file     <- args[1]
output_dir    <- args[2]
expected_rate <- if (length(args) >= 3) as.numeric(args[3]) else 0.06

suppressPackageStartupMessages({
    library(scDblFinder)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat(sprintf("Loading data from %s...\n", h5ad_file))
    sce <- readH5AD(h5ad_file)

    SummarizedExperiment::assay(sce, "counts") <- round(SummarizedExperiment::assay(sce, "X"))

    cat("Running scDblFinder...\n")
    set.seed(42)
    sce <- scDblFinder::scDblFinder(sce, dbr = expected_rate, verbose = FALSE)

    out <- data.frame(
        cell             = colnames(sce),
        classification   = as.character(colData(sce)$scDblFinder.class),
        doublet_score    = as.numeric(colData(sce)$scDblFinder.score),
        predicted_doublet = as.character(colData(sce)$scDblFinder.class) == "doublet",
        stringsAsFactors = FALSE,
        row.names        = colnames(sce)
    )

    write.csv(out, file.path(output_dir, "scdblfinder_results.csv"), quote = FALSE)

    n_doublets <- sum(out$predicted_doublet)
    cat(sprintf("Done. %d doublets detected out of %d cells (%.1f%%)\n",
        n_doublets, nrow(out), 100 * n_doublets / nrow(out)))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
