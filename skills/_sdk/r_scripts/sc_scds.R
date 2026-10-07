#!/usr/bin/env Rscript
# OmicsClaw: scds doublet detection
#
# Usage:
#   Rscript sc_scds.R <input_dir> <output_dir> [expected_doublet_rate] [mode] [random_state]

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript sc_scds.R <input_dir> <output_dir> [expected_doublet_rate] [mode] [random_state]\n")
    quit(status = 1)
}

input_dir <- args[1]
output_dir <- args[2]
expected_rate <- if (length(args) >= 3) as.numeric(args[3]) else 0.06
mode <- if (length(args) >= 4) as.character(args[4]) else "hybrid"
mode <- match.arg(mode, choices = c("hybrid", "cxds", "bcds"))

suppressPackageStartupMessages({
    library(scds)
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

    set.seed(if (length(args) >= 5) as.integer(args[5]) else 0)
    cat(sprintf("Running scds (%s)...\n", mode))
    if (mode == "cxds") {
        sce <- scds::cxds(sce, verb = FALSE)
        score_col <- "cxds_score"
    } else if (mode == "bcds") {
        sce <- scds::bcds(sce, verb = FALSE)
        score_col <- "bcds_score"
    } else {
        sce <- scds::cxds_bcds_hybrid(sce, verb = FALSE)
        score_col <- "hybrid_score"
    }

    scores <- as.numeric(SummarizedExperiment::colData(sce)[[score_col]])
    n_cells <- length(scores)
    n_exp <- max(1, round(expected_rate * n_cells))
    rank_idx <- order(scores, decreasing = TRUE)
    predicted <- rep(FALSE, n_cells)
    predicted[rank_idx[seq_len(min(n_exp, n_cells))]] <- TRUE
    classification <- ifelse(predicted, "Doublet", "Singlet")

    out <- data.frame(
        cell = colnames(sce),
        classification = classification,
        doublet_score = scores,
        predicted_doublet = predicted,
        stringsAsFactors = FALSE,
        row.names = colnames(sce)
    )

    write.csv(out, file.path(output_dir, "scds_results.csv"), quote = FALSE)
    n_doublets <- sum(out$predicted_doublet)
    cat(sprintf("Done. %d doublets detected out of %d cells (%.1f%%)\n",
        n_doublets, nrow(out), 100 * n_doublets / nrow(out)))
}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
