#!/usr/bin/env Rscript
# OmicsClaw: ComBat batch effect correction via sva package
#
# Usage:
#   Rscript bulkrna_combat.R <counts_csv> <batch_info_csv> <output_dir> [parametric]
#
# counts_csv: genes as rows, samples as columns (row.names = gene names)
# batch_info_csv: columns: sample, batch, [condition]
# parametric: "TRUE" (default) or "FALSE" for non-parametric ComBat

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 3) {
    cat("Usage: Rscript bulkrna_combat.R <counts.csv> <batch_info.csv> <output_dir> [parametric]\n")
    quit(status = 1)
}

counts_file  <- args[1]
batch_file   <- args[2]
output_dir   <- args[3]
parametric   <- if (length(args) >= 4) as.logical(args[4]) else TRUE

suppressPackageStartupMessages({
    library(sva)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading data...\n")
    counts <- as.matrix(read.csv(counts_file, row.names = 1, check.names = FALSE))
    batch_info <- read.csv(batch_file, check.names = FALSE)

    # Match samples
    if (!"sample" %in% colnames(batch_info)) {
        batch_info$sample <- batch_info[, 1]
    }
    common <- intersect(colnames(counts), as.character(batch_info$sample))
    if (length(common) == 0) stop("No matching samples between counts and batch info")

    counts <- counts[, common, drop = FALSE]
    batch_info <- batch_info[match(common, batch_info$sample), ]
    rownames(batch_info) <- batch_info$sample

    batch <- batch_info$batch
    n_batches <- length(unique(batch))
    cat(sprintf("  %d genes x %d samples, %d batches\n",
        nrow(counts), ncol(counts), n_batches))

    # Build model matrix (preserve biological condition if available)
    if ("condition" %in% colnames(batch_info)) {
        mod <- model.matrix(~ condition, data = batch_info)
        cat("  Preserving biological condition in ComBat model\n")
    } else {
        mod <- NULL
    }

    # Run ComBat
    cat(sprintf("Running ComBat (parametric=%s)...\n", parametric))
    corrected <- ComBat(
        dat = counts,
        batch = batch,
        mod = mod,
        par.prior = parametric
    )

    # Write outputs
    write.csv(corrected, file.path(output_dir, "corrected_counts.csv"), quote = FALSE)

    # Write metadata JSON
    info <- sprintf('{"n_genes": %d, "n_samples": %d, "n_batches": %d, "parametric": %s}',
        nrow(corrected), ncol(corrected), n_batches, tolower(as.character(parametric)))
    cat(info, file = file.path(output_dir, "combat_info.json"))

    cat(sprintf("Done. Corrected %d genes x %d samples across %d batches.\n",
        nrow(corrected), ncol(corrected), n_batches))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
