#!/usr/bin/env Rscript
# OmicsClaw: Seurat integration (CCA, RPCA, fastMNN)
#
# Usage:
#   Rscript sc_seurat_integrate.R <h5ad_file> <output_dir> <method> <batch_key>
#     [n_features] [n_pcs]
#
# method: seurat_cca | seurat_rpca | fastmnn

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 4) {
    cat("Usage: Rscript sc_seurat_integrate.R <h5ad_file> <output_dir>",
        "<method> <batch_key> [n_features] [n_pcs]\n")
    quit(status = 1)
}

h5ad_file  <- args[1]
output_dir <- args[2]
method     <- args[3]
batch_key  <- args[4]
n_features <- if (length(args) >= 5) as.integer(args[5]) else 2000L
n_pcs      <- if (length(args) >= 6) as.integer(args[6]) else 30L

suppressPackageStartupMessages({
    library(SingleCellExperiment)
    library(zellkonverter)
    library(scuttle)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat(sprintf("Loading data from %s...\n", h5ad_file))
    sce <- readH5AD(h5ad_file, reader = "R")
    meta <- as.data.frame(SummarizedExperiment::colData(sce))

    if (!batch_key %in% colnames(meta))
        stop(sprintf("Batch key '%s' not found in metadata", batch_key))

    cat(sprintf("Running %s integration (batch_key=%s)...\n", method, batch_key))

    if (method == "fastmnn") {
        suppressPackageStartupMessages(library(batchelor))
        counts <- as.matrix(SummarizedExperiment::assay(sce, "X"))
        split_idx <- split(seq_len(ncol(sce)), factor(meta[[batch_key]], levels = unique(meta[[batch_key]])))
        sce_list <- lapply(split_idx, function(idx) {
            batch_counts <- counts[, idx, drop = FALSE]
            batch_sce <- SingleCellExperiment(
                assays = list(counts = batch_counts),
                colData = S4Vectors::DataFrame(row.names = colnames(sce)[idx])
            )
            scuttle::logNormCounts(batch_sce)
        })

        mnn <- do.call(batchelor::fastMNN, c(sce_list, list(k = 20, d = n_pcs, deferred = FALSE)))
        embedding <- SingleCellExperiment::reducedDim(mnn, "corrected")
        if (is.null(embedding)) {
            stop("fastMNN did not return a reducedDim named 'corrected'")
        }
        embedding <- as.matrix(embedding)
        write.csv(embedding, file.path(output_dir, "embedding.csv"), quote = FALSE)
        write.csv(data.frame(row.names = rownames(embedding)),
            file.path(output_dir, "obs.csv"), quote = FALSE)

        cat(sprintf("Done. fastMNN embedding: %d cells x %d dims\n",
            nrow(embedding), ncol(embedding)))

    } else {
        suppressPackageStartupMessages(library(Seurat))

        counts <- SummarizedExperiment::assay(sce, "X")
        seurat_obj <- CreateSeuratObject(counts = counts, meta.data = meta)
        seurat_list <- SplitObject(seurat_obj, split.by = batch_key)

        seurat_list <- lapply(seurat_list, function(x) {
            x <- NormalizeData(x, verbose = FALSE)
            x <- FindVariableFeatures(x, nfeatures = n_features, verbose = FALSE)
            x
        })

        features <- SelectIntegrationFeatures(seurat_list, nfeatures = n_features)
        reduction_name <- if (method == "seurat_rpca") "rpca" else "cca"

        if (method == "seurat_rpca") {
            seurat_list <- lapply(seurat_list, function(x) {
                x <- ScaleData(x, features = features, verbose = FALSE)
                x <- RunPCA(x, features = features, npcs = n_pcs, verbose = FALSE)
                x
            })
        }

        anchors <- FindIntegrationAnchors(
            object.list     = seurat_list,
            anchor.features = features,
            reduction       = reduction_name,
            dims            = seq_len(n_pcs)
        )
        integrated <- IntegrateData(anchorset = anchors, dims = seq_len(n_pcs))
        DefaultAssay(integrated) <- "integrated"
        integrated <- ScaleData(integrated, verbose = FALSE)
        integrated <- RunPCA(integrated, npcs = n_pcs, verbose = FALSE)
        integrated <- RunUMAP(integrated, dims = seq_len(n_pcs), verbose = FALSE)

        write.csv(Embeddings(integrated, "pca"),
            file.path(output_dir, "embedding.csv"), quote = FALSE)
        write.csv(Embeddings(integrated, "umap"),
            file.path(output_dir, "umap.csv"), quote = FALSE)
        write.csv(integrated@meta.data,
            file.path(output_dir, "obs.csv"), quote = FALSE)

        cat(sprintf("Done. %s integration: %d cells\n", method, ncol(integrated)))
    }

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
