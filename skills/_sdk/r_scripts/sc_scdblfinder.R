#!/usr/bin/env Rscript
# OmicsClaw: scDblFinder doublet detection
#
# Usage:
#   Rscript sc_scdblfinder.R <input_dir> <output_dir> [expected_doublet_rate] [random_state]

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript sc_scdblfinder.R <input_dir> <output_dir> [expected_doublet_rate] [random_state]\n")
    quit(status = 1)
}

input_dir     <- args[1]
output_dir    <- args[2]
expected_rate <- if (length(args) >= 3) as.numeric(args[3]) else 0.06

suppressPackageStartupMessages({
    library(scDblFinder)
    library(SingleCellExperiment)
    library(Matrix)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat(sprintf("Loading data from %s...\n", input_dir))

    counts <- as(Matrix::readMM(file.path(input_dir, "matrix.mtx")), "CsparseMatrix")
    rownames(counts) <- read.delim(file.path(input_dir, "features.tsv"), header = FALSE,
                                  colClasses = "character", quote = "")[[1]]
    colnames(counts) <- read.delim(file.path(input_dir, "barcodes.tsv"), header = FALSE,
                                  colClasses = "character", quote = "")[[1]]
    meta <- read.csv(file.path(input_dir, "obs.csv"), row.names = 1, check.names = FALSE)
    stopifnot(identical(rownames(meta), colnames(counts)))
    sce <- SingleCellExperiment(assays = list(counts = round(counts)), colData = meta)

    cat("Running scDblFinder...\n")
    set.seed(if (length(args) >= 4) as.integer(args[4]) else 0)
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
