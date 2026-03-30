#!/usr/bin/env Rscript
# OmicsClaw: SPOTlight spatial deconvolution
#
# Usage:
#   Rscript sp_spotlight.R <spatial_counts> <spatial_coords> <ref_counts>
#     <ref_celltypes> <output_dir> [n_top] [weight_id] [model] [min_prop] [scale]

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 5) {
    cat("Usage: Rscript sp_spotlight.R <spatial_counts.csv> <spatial_coords.csv>",
        "<ref_counts.csv> <ref_celltypes.csv> <output_dir>",
        "[n_top] [weight_id] [model] [min_prop] [scale]\n")
    quit(status = 1)
}

sp_counts_file  <- args[1]
sp_coords_file  <- args[2]
ref_counts_file <- args[3]
ref_types_file  <- args[4]
output_dir      <- args[5]
n_top           <- if (length(args) >= 6 && nzchar(args[6])) as.integer(args[6]) else NULL
weight_id       <- if (length(args) >= 7 && nzchar(args[7])) args[7] else "weight"
nmf_model       <- if (length(args) >= 8 && nzchar(args[8])) args[8] else "ns"
min_prop        <- if (length(args) >= 9 && nzchar(args[9])) as.numeric(args[9]) else 0.01
scale_input     <- if (length(args) >= 10 && nzchar(args[10])) toupper(args[10]) else "TRUE"
scale_value     <- scale_input %in% c("TRUE", "T", "1", "YES")

suppressPackageStartupMessages({
    library(SPOTlight)
    library(SingleCellExperiment)
    library(SpatialExperiment)
    library(scran)
    library(scuttle)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading data...\n")
    sp_counts  <- as.matrix(read.csv(sp_counts_file, row.names = 1, check.names = FALSE))
    sp_coords  <- as.matrix(read.csv(sp_coords_file, row.names = 1, check.names = FALSE))
    ref_counts <- as.matrix(read.csv(ref_counts_file, row.names = 1, check.names = FALSE))
    ref_types_df <- read.csv(ref_types_file, check.names = FALSE)

    cell_types <- factor(ref_types_df$cell_type)

    gene_names <- rownames(ref_counts)
    spatial_names <- colnames(sp_counts)
    reference_names <- colnames(ref_counts)

    cat(sprintf("  Spatial: %d genes x %d spots\n", nrow(sp_counts), ncol(sp_counts)))
    cat(sprintf("  Reference: %d genes x %d cells, %d types\n",
        nrow(ref_counts), ncol(ref_counts), length(unique(cell_types))))

    # Build SCE and SPE objects
    sce <- SingleCellExperiment(
        assays = list(counts = ref_counts),
        colData = data.frame(cell_type = cell_types, row.names = reference_names))
    sce <- logNormCounts(sce)

    spe <- SpatialExperiment(
        assays = list(counts = sp_counts),
        spatialCoords = sp_coords,
        colData = data.frame(row.names = spatial_names))

    # Find marker genes per cell type
    cat("Finding marker genes...\n")
    markers <- findMarkers(sce, groups = sce$cell_type, test.type = "wilcox")
    mgs_list <- list()
    for (ct in names(markers)) {
        ct_markers <- as.data.frame(markers[[ct]])
        ct_markers$gene <- rownames(ct_markers)
        ct_markers$cluster <- ct

        if (!"weight" %in% colnames(ct_markers)) {
            if ("mean.AUC" %in% colnames(ct_markers)) {
                ct_markers$weight <- ct_markers$mean.AUC
            } else if ("summary.logFC" %in% colnames(ct_markers)) {
                ct_markers$weight <- ct_markers$summary.logFC
            } else if ("logFC" %in% colnames(ct_markers)) {
                ct_markers$weight <- ct_markers$logFC
            } else if ("p.value" %in% colnames(ct_markers)) {
                ct_markers$weight <- -log10(ct_markers$p.value + 1e-300)
            } else {
                ct_markers$weight <- seq_len(nrow(ct_markers))
            }
        }

        if (!"mean.AUC" %in% colnames(ct_markers)) {
            ct_markers$mean.AUC <- ct_markers$weight
        }

        mgs_list[[ct]] <- ct_markers
    }
    mgs <- do.call(rbind, mgs_list)

    if (!(weight_id %in% colnames(mgs))) {
        stop(sprintf(
            "Requested weight_id '%s' not found in marker table. Available columns: %s",
            weight_id, paste(colnames(mgs), collapse = ", ")
        ))
    }

    # Run SPOTlight
    cat("Running SPOTlight NMF deconvolution...\n")
    spotlight_args <- list(
        x = sce, y = spe,
        groups = sce$cell_type,
        mgs = mgs,
        n_top = n_top,
        weight_id = weight_id,
        group_id = "cluster",
        gene_id = "gene",
        model = nmf_model,
        min_prop = min_prop,
        scale = scale_value,
        verbose = FALSE
    )
    spotlight_result <- do.call(SPOTlight, spotlight_args)

    proportions <- as.data.frame(spotlight_result$mat)
    rownames(proportions) <- spatial_names

    write.csv(proportions, file.path(output_dir, "spotlight_proportions.csv"),
        quote = FALSE)

    cat(sprintf("Done. Deconvolved %d spots into %d cell types\n",
        nrow(proportions), ncol(proportions)))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
