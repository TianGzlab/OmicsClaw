#!/usr/bin/env Rscript
# OmicsClaw: RCTD spatial deconvolution (spacexr)
#
# Usage:
#   Rscript sp_rctd.R <spatial_counts> <spatial_coords> <ref_counts>
#     <ref_celltypes> <output_dir> [mode]
#
# mode: full | doublet | multi (default: full)
# All CSV files: genes as rows, cells/spots as columns, first col = row names.
# ref_celltypes: CSV with columns "cell" and "cell_type".

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 5) {
    cat("Usage: Rscript sp_rctd.R <spatial_counts.csv> <spatial_coords.csv>",
        "<ref_counts.csv> <ref_celltypes.csv> <output_dir> [mode]\n")
    quit(status = 1)
}

sp_counts_file <- args[1]
sp_coords_file <- args[2]
ref_counts_file <- args[3]
ref_types_file  <- args[4]
output_dir      <- args[5]
rctd_mode       <- if (length(args) >= 6) args[6] else "full"

suppressPackageStartupMessages({
    library(spacexr)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading spatial data...\n")
    sp_counts <- as.matrix(read.csv(sp_counts_file, row.names = 1, check.names = FALSE))
    sp_coords <- read.csv(sp_coords_file, row.names = 1, check.names = FALSE)

    cat("Loading reference data...\n")
    ref_counts <- as.matrix(read.csv(ref_counts_file, row.names = 1, check.names = FALSE))
    ref_types_df <- read.csv(ref_types_file, check.names = FALSE)
    ref_cell_types <- factor(ref_types_df$cell_type)
    names(ref_cell_types) <- ref_types_df$cell

    cat(sprintf("  Spatial: %d genes x %d spots\n", nrow(sp_counts), ncol(sp_counts)))
    cat(sprintf("  Reference: %d genes x %d cells, %d types\n",
        nrow(ref_counts), ncol(ref_counts), length(unique(ref_cell_types))))

    # Create RCTD objects
    ref <- Reference(ref_counts, ref_cell_types)
    puck <- SpatialRNA(sp_coords, sp_counts)

    cat(sprintf("Running RCTD (mode=%s)...\n", rctd_mode))
    myRCTD <- create.RCTD(puck, ref, max_cores = 1)
    myRCTD <- run.RCTD(myRCTD, doublet_mode = rctd_mode)

    weights <- myRCTD@results$weights
    weights_norm <- sweep(weights, 1, rowSums(weights), "/")

    write.csv(as.data.frame(weights_norm),
        file.path(output_dir, "rctd_proportions.csv"), quote = FALSE)

    cat(sprintf("Done. Deconvolved %d spots into %d cell types\n",
        nrow(weights_norm), ncol(weights_norm)))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
