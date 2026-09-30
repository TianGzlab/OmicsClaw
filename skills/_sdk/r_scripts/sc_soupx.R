#!/usr/bin/env Rscript
# OmicsClaw: SoupX ambient RNA removal
#
# Usage:
#   Rscript sc_soupx.R <raw_matrix_dir> <filtered_matrix_dir> <output_dir>

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 3) {
    cat("Usage: Rscript sc_soupx.R <raw_matrix_dir> <filtered_matrix_dir> <output_dir>\n")
    quit(status = 1)
}

raw_dir      <- args[1]
filtered_dir <- args[2]
output_dir   <- args[3]

suppressPackageStartupMessages({
    library(Seurat)
    library(SoupX)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading 10x matrices...\n")
    raw_data      <- Read10X(raw_dir)
    filtered_data <- Read10X(filtered_dir)

    cat(sprintf("  Raw: %d barcodes, Filtered: %d barcodes\n",
        ncol(raw_data), ncol(filtered_data)))

    # Quick Seurat clustering for SoupX
    seurat_temp <- CreateSeuratObject(counts = filtered_data)
    seurat_temp <- NormalizeData(seurat_temp, verbose = FALSE)
    seurat_temp <- FindVariableFeatures(seurat_temp, verbose = FALSE)
    seurat_temp <- ScaleData(seurat_temp, verbose = FALSE)
    seurat_temp <- RunPCA(seurat_temp, npcs = 30, verbose = FALSE)
    seurat_temp <- FindNeighbors(seurat_temp, dims = 1:30, verbose = FALSE)
    seurat_temp <- FindClusters(seurat_temp, resolution = 0.8, verbose = FALSE)

    cat("Running SoupX...\n")
    sc <- SoupChannel(raw_data, filtered_data)
    sc <- setClusters(sc, Idents(seurat_temp))
    sc <- autoEstCont(sc)

    rho <- as.numeric(sc$metaData$rho[1])
    corrected <- adjustCounts(sc)

    # Write corrected counts as dense CSV
    corrected_dense <- as.matrix(corrected)
    write.csv(corrected_dense, file.path(output_dir, "corrected_counts.csv"), quote = FALSE)

    # Write contamination estimate
    cat(sprintf('{"contamination": %f}\n', rho),
        file = file.path(output_dir, "contamination.json"))

    # Write cell/gene names
    write.csv(data.frame(cell = colnames(corrected)),
        file.path(output_dir, "cells.csv"), row.names = FALSE, quote = FALSE)
    write.csv(data.frame(gene = rownames(corrected)),
        file.path(output_dir, "genes.csv"), row.names = FALSE, quote = FALSE)

    cat(sprintf("Done. Estimated contamination: %.2f%%\n", rho * 100))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
