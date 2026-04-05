#!/usr/bin/env Rscript
# OmicsClaw: Seurat-based single-cell preprocessing
#
# Usage:
#   Rscript sc_seurat_preprocess.R <h5ad_file> <output_dir> [workflow] [min_genes]
#     [min_cells] [max_mt_pct] [n_hvg] [n_pcs] [n_neighbors] [resolution]
#
# Extracted from skills/singlecell/_lib/r_bridge.py::run_seurat_preprocessing

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript sc_seurat_preprocess.R <h5ad_file> <output_dir>",
        "[workflow] [min_genes] [min_cells] [max_mt_pct] [n_hvg] [n_pcs]",
        "[n_neighbors] [resolution]\n")
    quit(status = 1)
}

h5ad_file   <- args[1]
output_dir  <- args[2]
workflow    <- if (length(args) >= 3)  args[3]            else "seurat"
min_genes   <- if (length(args) >= 4)  as.integer(args[4]) else 200L
min_cells   <- if (length(args) >= 5)  as.integer(args[5]) else 3L
max_mt_pct  <- if (length(args) >= 6)  as.numeric(args[6]) else 20.0
n_top_hvg   <- if (length(args) >= 7)  as.integer(args[7]) else 2000L
n_pcs       <- if (length(args) >= 8)  as.integer(args[8]) else 50L
n_neighbors <- if (length(args) >= 9)  as.integer(args[9]) else 15L
resolution  <- if (length(args) >= 10) as.numeric(args[10]) else 1.0

suppressPackageStartupMessages({
    library(Seurat)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

.get_assay_matrix <- function(seurat_obj, assay_name, layer_name) {
    if ("LayerData" %in% getNamespaceExports("SeuratObject")) {
        return(as.matrix(SeuratObject::LayerData(seurat_obj, assay = assay_name, layer = layer_name)))
    }
    return(as.matrix(GetAssayData(seurat_obj, assay = assay_name, slot = layer_name)))
}

cat(sprintf("Loading data from %s...\n", h5ad_file))

tryCatch({
    sce <- readH5AD(h5ad_file, reader = "R")
    counts <- SummarizedExperiment::assay(sce, "X")
    meta   <- as.data.frame(SummarizedExperiment::colData(sce))

    cat(sprintf("  %d cells x %d genes\n", ncol(counts), nrow(counts)))

    seurat_obj <- CreateSeuratObject(
        counts     = counts,
        meta.data  = meta,
        min.cells  = min_cells,
        min.features = min_genes
    )

    # Mitochondrial QC
    mt_pattern <- if (sum(grepl("^MT-", rownames(seurat_obj))) > 0) "^MT-" else "^mt-"
    seurat_obj[["percent.mt"]] <- PercentageFeatureSet(seurat_obj, pattern = mt_pattern)
    seurat_obj <- subset(seurat_obj,
        subset = nFeature_RNA >= min_genes & percent.mt <= max_mt_pct)

    cat(sprintf("  %d cells after QC filtering\n", ncol(seurat_obj)))

    # Normalize
    if (workflow == "sctransform") {
        if (!requireNamespace("sctransform", quietly = TRUE))
            stop("SCTransform workflow requires the R package 'sctransform'")
        seurat_obj <- SCTransform(seurat_obj,
            vars.to.regress = if ("percent.mt" %in% colnames(seurat_obj@meta.data)) "percent.mt" else NULL,
            variable.features.n = n_top_hvg, verbose = FALSE)
    } else {
        seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)
        seurat_obj <- FindVariableFeatures(seurat_obj,
            selection.method = "vst", nfeatures = n_top_hvg, verbose = FALSE)
        seurat_obj <- ScaleData(seurat_obj, verbose = FALSE)
    }

    # Dimensionality reduction (base preprocessing stops at PCA)
    seurat_obj <- RunPCA(seurat_obj, npcs = n_pcs, verbose = FALSE)

    # Extract results
    meta_out <- seurat_obj@meta.data
    assay_name <- DefaultAssay(seurat_obj)

    # Write outputs
    cat("Writing results...\n")

    write.csv(meta_out, file.path(output_dir, "obs.csv"), quote = FALSE)

    pca_emb <- Embeddings(seurat_obj, "pca")
    write.csv(pca_emb, file.path(output_dir, "pca.csv"), quote = FALSE)

    hvg <- VariableFeatures(seurat_obj)
    write.csv(data.frame(gene = hvg), file.path(output_dir, "hvg.csv"),
        row.names = FALSE, quote = FALSE)

    # Normalized expression matrix (genes x cells) — can be large
    norm_mat <- .get_assay_matrix(seurat_obj, assay_name, "data")
    write.csv(norm_mat, file.path(output_dir, "X_norm.csv"), quote = FALSE)

    # Metadata JSON
    cat(sprintf('{"workflow": "%s", "default_assay": "%s", "n_cells": %d, "n_genes": %d}\n',
        workflow, assay_name, ncol(seurat_obj), nrow(seurat_obj)),
        file = file.path(output_dir, "info.json"))

    cat(sprintf("Done. %d cells, %d genes, %d HVGs\n",
        ncol(seurat_obj), nrow(seurat_obj), length(hvg)))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
