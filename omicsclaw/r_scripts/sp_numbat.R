#!/usr/bin/env Rscript
# OmicsClaw: Numbat haplotype-aware CNV inference
#
# Usage:
#   Rscript sp_numbat.R <h5ad_file> <output_dir> <allele_counts_csv> <ref_key> <ref_cat> [genome] [max_entropy] [min_LLR] [min_cells] [ncores]

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 5) {
    cat(
        "Usage: Rscript sp_numbat.R <h5ad_file> <output_dir> <allele_counts_csv> <ref_key> <ref_cat> [genome] [max_entropy] [min_LLR] [min_cells] [ncores]\n"
    )
    quit(status = 1)
}

h5ad_file        <- args[1]
output_dir       <- args[2]
allele_csv       <- args[3]
ref_key          <- if (nzchar(args[4])) args[4] else NULL
ref_cat          <- if (nzchar(args[5])) strsplit(args[5], ",")[[1]] else character(0)
genome           <- if (length(args) >= 6 && nzchar(args[6])) args[6] else "hg38"
max_entropy      <- if (length(args) >= 7 && nzchar(args[7])) as.numeric(args[7]) else 0.8
min_LLR          <- if (length(args) >= 8 && nzchar(args[8])) as.numeric(args[8]) else 5
min_cells        <- if (length(args) >= 9 && nzchar(args[9])) as.integer(args[9]) else 50L
ncores           <- if (length(args) >= 10 && nzchar(args[10])) as.integer(args[10]) else 1L

suppressPackageStartupMessages({
    library(numbat)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

.write_empty_csv <- function(path) {
    write.csv(data.frame(), path, row.names = FALSE, quote = FALSE)
}

tryCatch({
    cat(sprintf("Loading data from %s...\n", h5ad_file))
    sce <- readH5AD(h5ad_file)
    obs_df <- as.data.frame(SummarizedExperiment::colData(sce))
    count_mat <- SummarizedExperiment::assay(sce, "X")

    cat(sprintf("  %d cells x %d genes\n", ncol(sce), nrow(sce)))

    if (is.null(ref_key) || !nzchar(ref_key)) {
        stop("Numbat wrapper requires a non-empty reference key.")
    }
    if (!(ref_key %in% colnames(obs_df))) {
        stop(sprintf("Reference key '%s' not found in colData(sce).", ref_key))
    }
    if (length(ref_cat) == 0) {
        stop("Numbat wrapper requires at least one reference category.")
    }

    ref_mask <- obs_df[[ref_key]] %in% ref_cat
    if (!any(ref_mask)) {
        stop("No cells matched the supplied reference categories.")
    }

    if (!file.exists(allele_csv)) {
        stop(sprintf("Allele counts CSV not found: %s", allele_csv))
    }
    df_allele <- read.csv(allele_csv, stringsAsFactors = FALSE, check.names = FALSE)
    required_cols <- c("cell", "snp_id", "CHROM", "POS", "AD", "DP", "GT", "gene")
    missing_cols <- setdiff(required_cols, colnames(df_allele))
    if (length(missing_cols) > 0) {
        stop(sprintf("Allele count table missing required columns: %s", paste(missing_cols, collapse = ", ")))
    }

    cat("Building diploid reference expression profiles...\n")
    annotation <- data.frame(
        cell = colnames(sce)[ref_mask],
        group = as.character(obs_df[[ref_key]][ref_mask]),
        cell_type = as.character(obs_df[[ref_key]][ref_mask]),
        stringsAsFactors = FALSE
    )
    lambdas_ref <- aggregate_counts(count_mat[, ref_mask, drop = FALSE], annotation = annotation)

    cat("Running Numbat CNV inference...\n")
    status <- run_numbat(
        count_mat = count_mat,
        lambdas_ref = lambdas_ref,
        df_allele = df_allele,
        genome = genome,
        out_dir = output_dir,
        max_entropy = max_entropy,
        min_LLR = min_LLR,
        min_cells = min_cells,
        ncores = ncores,
        plot = FALSE
    )

    if (!is.null(status) && is.numeric(status) && status != 0) {
        stop(sprintf("run_numbat exited with non-zero status: %s", status))
    }

    nb <- Numbat$new(out_dir = output_dir, genome = genome, ncores = ncores)

    joint_post <- nb$joint_post
    clone_post <- nb$clone_post

    if (!is.null(joint_post) && nrow(joint_post) > 0) {
        write.csv(
            as.data.frame(joint_post),
            file.path(output_dir, "numbat_results.csv"),
            row.names = FALSE,
            quote = FALSE
        )
        cat(sprintf("Saved %d joint posterior CNV rows\n", nrow(joint_post)))
    } else {
        cat("WARNING: joint_post was empty\n")
        .write_empty_csv(file.path(output_dir, "numbat_results.csv"))
    }

    if (!is.null(clone_post) && nrow(clone_post) > 0) {
        write.csv(
            as.data.frame(clone_post),
            file.path(output_dir, "numbat_clone_post.csv"),
            row.names = FALSE,
            quote = FALSE
        )
        cat(sprintf("Saved %d clone posterior rows\n", nrow(clone_post)))
    } else {
        cat("WARNING: clone_post was empty\n")
        .write_empty_csv(file.path(output_dir, "numbat_clone_post.csv"))
    }

}, error = function(e) {
    .write_empty_csv(file.path(output_dir, "numbat_results.csv"))
    .write_empty_csv(file.path(output_dir, "numbat_clone_post.csv"))
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
