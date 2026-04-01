#!/usr/bin/env Rscript
args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
    cat("Usage: Rscript sc_scmap_annotate.R <h5ad_file> <output_dir> [reference]\n")
    quit(status = 1)
}

h5ad_file  <- args[1]
output_dir <- args[2]
reference  <- if (length(args) >= 3) args[3] else "HPCA"

suppressPackageStartupMessages({
    library(scmap)
    library(celldex)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

cache_dir <- file.path(path.expand("~"), ".cache", "omicsclaw", "experimenthub")
dir.create(cache_dir, recursive = TRUE, showWarnings = FALSE)
Sys.setenv(EXPERIMENT_HUB_CACHE = cache_dir)
options(timeout = max(600, getOption("timeout")))

tryCatch({
    sce <- readH5AD(h5ad_file)
    if (!"logcounts" %in% SummarizedExperiment::assayNames(sce)) {
        SummarizedExperiment::assay(sce, "logcounts") <- SummarizedExperiment::assay(sce, "X")
    }
    rowData(sce)$feature_symbol <- rownames(sce)

    ref_data <- switch(reference,
        HPCA = celldex::HumanPrimaryCellAtlasData(),
        Blueprint_Encode = celldex::BlueprintEncodeData(),
        Monaco = celldex::MonacoImmuneData(),
        Mouse = celldex::MouseRNAseqData(),
        stop(sprintf("Unsupported scmap reference: %s", reference))
    )
    ref_data <- as(ref_data, "SingleCellExperiment")
    rowData(ref_data)$feature_symbol <- rownames(ref_data)
    ref_data <- scmap::selectFeatures(ref_data, suppress_plot = TRUE)
    ref_data <- scmap::indexCluster(ref_data, cluster_col = "label.main")

    res <- scmap::scmapCluster(
        projection = sce,
        index_list = list(reference = metadata(ref_data)$scmap_cluster_index),
        threshold = 0.7
    )

    siml <- res$scmap_cluster_siml
    score <- apply(siml, 1, function(x) {
        if (all(is.na(x))) return(NA_real_)
        max(x, na.rm = TRUE)
    })
    out <- data.frame(
        cell = colnames(sce),
        cell_type = as.character(res$combined_labs),
        pruned_label = as.character(res$combined_labs),
        score = as.numeric(score),
        stringsAsFactors = FALSE,
        row.names = colnames(sce)
    )
    write.csv(out, file.path(output_dir, "scmap_results.csv"), quote = FALSE)
}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
