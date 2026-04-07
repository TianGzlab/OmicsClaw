#!/usr/bin/env Rscript
# OmicsClaw: SingleR cell type annotation
#
# Usage:
#   Rscript sc_singler_annotate.R <h5ad_file> <output_dir> [reference]
#
# reference: HPCA | Blueprint_Encode | Monaco | Mouse (default: HPCA)

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript sc_singler_annotate.R <h5ad_file> <output_dir> [reference]\n")
    quit(status = 1)
}

h5ad_file  <- args[1]
output_dir <- args[2]
reference  <- if (length(args) >= 3) args[3] else "HPCA"

suppressPackageStartupMessages({
    library(SingleR)
    library(celldex)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

cache_dir <- Sys.getenv("OMICSCLAW_EXPERIMENTHUB_CACHE", unset = file.path(tempdir(), "omicsclaw", "experimenthub"))
dir.create(cache_dir, recursive = TRUE, showWarnings = FALSE)
Sys.setenv(EXPERIMENT_HUB_CACHE = cache_dir)
options(timeout = max(600, getOption("timeout")))

infer_label_key <- function(sce) {
    candidates <- c("cell_type", "celltype", "label", "annotation", "cell_type_label")
    for (candidate in candidates) {
        if (candidate %in% colnames(colData(sce))) {
            return(candidate)
        }
    }
    stop("Reference H5AD must contain a label column such as cell_type or annotation")
}

tryCatch({
    cat(sprintf("Loading data from %s...\n", h5ad_file))
    sce <- readH5AD(h5ad_file, reader = "R")

    cat(sprintf("Loading reference: %s...\n", reference))
    if (file.exists(reference)) {
        ref_data <- readH5AD(reference, reader = "R")
        label_key <- infer_label_key(ref_data)
        ref_labels <- colData(ref_data)[[label_key]]
        if (!"logcounts" %in% SummarizedExperiment::assayNames(ref_data) && "X" %in% SummarizedExperiment::assayNames(ref_data)) {
            SummarizedExperiment::assay(ref_data, "logcounts") <- SummarizedExperiment::assay(ref_data, "X")
        }
    } else {
        ref_data <- switch(reference,
            HPCA             = celldex::HumanPrimaryCellAtlasData(),
            Blueprint_Encode = celldex::BlueprintEncodeData(),
            Monaco           = celldex::MonacoImmuneData(),
            Mouse            = celldex::MouseRNAseqData(),
            stop(sprintf("Unsupported SingleR reference: %s", reference))
        )
        ref_labels <- ref_data$label.main
    }

    cat("Running SingleR annotation...\n")
    pred <- SingleR(
        test   = SummarizedExperiment::assay(sce, "X"),
        ref    = ref_data,
        labels = ref_labels
    )

    score <- apply(pred$scores, 1, max)
    out <- data.frame(
        cell         = colnames(sce),
        cell_type    = pred$labels,
        pruned_label = ifelse(is.na(pred$pruned.labels), pred$labels, pred$pruned.labels),
        score        = score,
        stringsAsFactors = FALSE,
        row.names    = colnames(sce)
    )

    write.csv(out, file.path(output_dir, "singler_results.csv"), quote = FALSE)
    cat(sprintf("Done. Annotated %d cells with %d unique types\n",
        nrow(out), length(unique(out$cell_type))))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
