#!/usr/bin/env Rscript
# OmicsClaw: SPARK-X spatially variable gene detection
#
# Usage:
#   Rscript sp_sparkx.R <counts_csv> <coords_csv> <output_dir> [num_cores] [option]
#
# counts_csv: genes x spots matrix (first column = gene names)
# coords_csv: spots x 2 (x, y) coordinates (first column = spot names)

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 3) {
    cat("Usage: Rscript sp_sparkx.R <counts.csv> <coords.csv> <output_dir> [num_cores] [option]\n")
    quit(status = 1)
}

counts_file <- args[1]
coords_file <- args[2]
output_dir  <- args[3]
num_cores   <- ifelse(length(args) >= 4, max(1, as.integer(args[4])), 1)
sparkx_option <- ifelse(length(args) >= 5, args[5], "mixture")

suppressPackageStartupMessages({
    library(SPARK)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading data...\n")
    counts <- as.matrix(read.csv(counts_file, row.names = 1, check.names = FALSE))
    coords <- as.matrix(read.csv(coords_file, row.names = 1, check.names = FALSE))

    cat(sprintf("  %d genes x %d spots\n", nrow(counts), ncol(counts)))

    cat("Running SPARK-X...\n")
    cat(sprintf("  numCores=%d, option=%s\n", num_cores, sparkx_option))
    sparkx_result <- spark.sparkx(counts, coords, numCores = num_cores, option = sparkx_option)

    res_df <- sparkx_result$res_mtest
    res_df$gene <- rownames(res_df)

    # Rename columns to match OmicsClaw convention
    colnames(res_df)[colnames(res_df) == "combinedPval"] <- "pval"
    colnames(res_df)[colnames(res_df) == "adjustedPval"] <- "qval"

    write.csv(res_df, file.path(output_dir, "sparkx_results.csv"), quote = FALSE)

    n_sig <- sum(res_df$qval < 0.05, na.rm = TRUE)
    cat(sprintf("Done. %d spatially variable genes (FDR < 0.05)\n", n_sig))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
