#!/usr/bin/env Rscript
# OmicsClaw: DoubletFinder doublet detection
#
# Usage:
#   Rscript sc_doubletfinder.R <h5ad_file> <output_dir> [expected_doublet_rate]

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript sc_doubletfinder.R <h5ad_file> <output_dir> [expected_doublet_rate]\n")
    quit(status = 1)
}

h5ad_file     <- args[1]
output_dir    <- args[2]
expected_rate <- if (length(args) >= 3) as.numeric(args[3]) else 0.06

suppressPackageStartupMessages({
    library(Seurat)
    library(DoubletFinder)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat(sprintf("Loading data from %s...\n", h5ad_file))
    sce <- readH5AD(h5ad_file)
    counts <- SummarizedExperiment::assay(sce, "X")
    meta   <- as.data.frame(SummarizedExperiment::colData(sce))

    cat("Running DoubletFinder pipeline...\n")
    seurat_obj <- CreateSeuratObject(counts = counts, meta.data = meta)
    seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)
    seurat_obj <- FindVariableFeatures(seurat_obj, verbose = FALSE)
    seurat_obj <- ScaleData(seurat_obj, verbose = FALSE)
    seurat_obj <- RunPCA(seurat_obj, npcs = 30, verbose = FALSE)
    seurat_obj <- FindNeighbors(seurat_obj, dims = 1:30, verbose = FALSE)
    seurat_obj <- FindClusters(seurat_obj, resolution = 0.5, verbose = FALSE)

    pK_optimal <- 0.15
    annotations <- as.character(Idents(seurat_obj))
    homotypic_prop <- modelHomotypic(annotations)
    nExp_poi <- round(expected_rate * ncol(seurat_obj))
    nExp_poi_adj <- max(1, round(nExp_poi * (1 - homotypic_prop)))

    seurat_obj <- doubletFinder(seurat_obj,
        PCs = 1:30, pN = 0.25, pK = pK_optimal,
        nExp = nExp_poi_adj, reuse.pANN = NULL, sct = FALSE)

    df_cols  <- grep("^DF.classifications", colnames(seurat_obj@meta.data), value = TRUE)
    pann_cols <- grep("^pANN", colnames(seurat_obj@meta.data), value = TRUE)

    out <- data.frame(
        cell             = colnames(seurat_obj),
        classification   = as.character(seurat_obj@meta.data[[df_cols[1]]]),
        doublet_score    = as.numeric(seurat_obj@meta.data[[pann_cols[1]]]),
        predicted_doublet = as.character(seurat_obj@meta.data[[df_cols[1]]]) == "Doublet",
        stringsAsFactors = FALSE,
        row.names        = colnames(seurat_obj)
    )

    write.csv(out, file.path(output_dir, "doubletfinder_results.csv"), quote = FALSE)

    n_doublets <- sum(out$predicted_doublet)
    cat(sprintf("Done. %d doublets detected out of %d cells (%.1f%%)\n",
        n_doublets, nrow(out), 100 * n_doublets / nrow(out)))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
