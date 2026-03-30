#!/usr/bin/env Rscript
# OmicsClaw: CARD spatial deconvolution
#
# Usage:
#   Rscript sp_card.R <spatial_counts> <spatial_coords> <ref_counts>
#     <ref_meta> <output_dir> [min_count_gene] [min_count_spot]
#     [imputation] [num_grids] [ineibor]

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 5) {
    cat("Usage: Rscript sp_card.R <spatial_counts.csv> <spatial_coords.csv>",
        "<ref_counts.csv> <ref_meta.csv> <output_dir> [min_count_gene] [min_count_spot]",
        "[imputation] [num_grids] [ineibor]\n")
    quit(status = 1)
}

sp_counts_file <- args[1]
sp_coords_file <- args[2]
ref_counts_file <- args[3]
ref_meta_file   <- args[4]
output_dir      <- args[5]
minCountGene    <- if (length(args) >= 6) as.integer(args[6]) else 100L
minCountSpot    <- if (length(args) >= 7) as.integer(args[7]) else 5L
runImputation   <- if (length(args) >= 8 && nzchar(args[8])) toupper(args[8]) %in% c("TRUE", "T", "1", "YES") else FALSE
numGrids        <- if (length(args) >= 9 && nzchar(args[9])) as.integer(args[9]) else 2000L
ineibor         <- if (length(args) >= 10 && nzchar(args[10])) as.integer(args[10]) else 10L

suppressPackageStartupMessages({
    library(CARD)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading data...\n")
    sc_count <- as.matrix(read.csv(ref_counts_file, row.names = 1, check.names = FALSE))
    spatial_count <- as.matrix(read.csv(sp_counts_file, row.names = 1, check.names = FALSE))
    spatial_location <- read.csv(sp_coords_file, row.names = 1, check.names = FALSE)
    sc_meta <- read.csv(ref_meta_file, row.names = 1, check.names = FALSE)

    # Ensure required columns
    if (!"cellType" %in% colnames(sc_meta))
        stop("Reference metadata must contain 'cellType' column")
    if (!"sampleInfo" %in% colnames(sc_meta))
        sc_meta$sampleInfo <- "sample1"

    cat(sprintf("  Spatial: %d genes x %d spots\n", nrow(spatial_count), ncol(spatial_count)))
    cat(sprintf("  Reference: %d genes x %d cells, %d types\n",
        nrow(sc_count), ncol(sc_count), length(unique(sc_meta$cellType))))

    cat("Running CARD deconvolution...\n")
    capture.output(
        CARD_obj <- createCARDObject(
            sc_count = sc_count,
            sc_meta = sc_meta,
            spatial_count = spatial_count,
            spatial_location = spatial_location,
            ct.varname = "cellType",
            ct.select = unique(sc_meta$cellType),
            sample.varname = "sampleInfo",
            minCountGene = minCountGene,
            minCountSpot = minCountSpot),
        file = "/dev/null"
    )

    capture.output(
        CARD_obj <- CARD_deconvolution(CARD_object = CARD_obj),
        file = "/dev/null"
    )

    proportions <- as.data.frame(CARD_obj@Proportion_CARD)

    write.csv(proportions, file.path(output_dir, "card_proportions.csv"),
        quote = FALSE)

    if (runImputation) {
        cat(sprintf(
            "Running CARD imputation (numGrids=%d, ineibor=%d)...\n",
            numGrids, ineibor
        ))
        capture.output(
            CARD_obj <- CARD.imputation(
                CARD_obj,
                NumGrids = numGrids,
                ineibor = ineibor
            ),
            file = "/dev/null"
        )

        if (!is.null(CARD_obj@refined_prop)) {
            write.csv(
                as.data.frame(CARD_obj@refined_prop),
                file.path(output_dir, "card_refined_proportions.csv"),
                quote = FALSE
            )
        }
    }

    cat(sprintf("Done. Deconvolved %d spots into %d cell types\n",
        nrow(proportions), ncol(proportions)))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
