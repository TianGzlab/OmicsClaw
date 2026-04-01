#!/usr/bin/env Rscript
# OmicsClaw: CellChat cell-cell communication analysis
#
# Usage:
#   Rscript sc_cellchat.R <h5ad_file> <output_dir> [cell_type_key] [species] [prob_type] [min_cells]
#
# species: human | mouse (default: human)
# Used by both single-cell and spatial communication skills.
#
# Input: adata.X must be log-normalized expression (not raw counts).
# CellChat requires "normalized data (library-size normalization and then
# log-transformed with a pseudocount of 1)" as input.
# The raw.use=TRUE parameter in computeCommunProb() refers to CellChat's
# internal signaling gene subset, NOT raw UMI counts.

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript sc_cellchat.R <h5ad_file> <output_dir> [cell_type_key] [species] [prob_type] [min_cells]\n")
    quit(status = 1)
}

h5ad_file     <- args[1]
output_dir    <- args[2]
cell_type_key <- if (length(args) >= 3) args[3] else "cell_type"
species       <- if (length(args) >= 4) args[4] else "human"
prob_type     <- if (length(args) >= 5) args[5] else "triMean"
min_cells     <- if (length(args) >= 6) as.integer(args[6]) else 10

suppressPackageStartupMessages({
    library(CellChat)
    library(SingleCellExperiment)
    library(zellkonverter)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat(sprintf("Loading data from %s...\n", h5ad_file))
    sce <- readH5AD(h5ad_file)
    counts <- SummarizedExperiment::assay(sce, "X")
    meta   <- as.data.frame(SummarizedExperiment::colData(sce))

    if (!cell_type_key %in% colnames(meta))
        stop(sprintf("Cell type key '%s' not found in metadata", cell_type_key))

    if (!"samples" %in% colnames(meta))
        meta$samples <- "sample1"

    meta[[cell_type_key]] <- as.character(meta[[cell_type_key]])
    meta[[cell_type_key]] <- ifelse(grepl("^[0-9]", meta[[cell_type_key]]),
        paste0("cluster_", meta[[cell_type_key]]),
        meta[[cell_type_key]])
    meta[[cell_type_key]] <- make.unique(meta[[cell_type_key]])

    cat(sprintf("  %d cells, %d cell types, species=%s\n",
        ncol(counts), length(unique(meta[[cell_type_key]])), species))

    cat("Creating CellChat object...\n")
    cellchat <- createCellChat(object = counts, meta = meta, group.by = cell_type_key)

    cellchat@DB <- if (tolower(species) == "mouse") CellChatDB.mouse else CellChatDB.human

    cat("Identifying overexpressed genes and interactions...\n")
    cellchat <- subsetData(cellchat)

    # Use presto for fast Wilcoxon if available, otherwise standard method.
    has_presto <- requireNamespace("presto", quietly = TRUE)
    cellchat <- identifyOverExpressedGenes(cellchat, do.fast = has_presto)
    cellchat <- identifyOverExpressedInteractions(cellchat)

    cat(sprintf("Computing communication probabilities (type=%s)...\n", prob_type))
    cellchat <- computeCommunProb(cellchat, raw.use = TRUE, type = prob_type)
    cellchat <- filterCommunication(cellchat, min.cells = min_cells)
    cellchat <- computeCommunProbPathway(cellchat)
    cellchat <- aggregateNet(cellchat)

    cat("Computing network centrality metrics...\n")
    cellchat <- netAnalysis_computeCentrality(cellchat)

    # --- Export L-R pair interactions ---
    df <- subsetCommunication(cellchat)

    if (!nrow(df)) {
        cat("WARNING: No significant interactions found\n")
        write.csv(data.frame(), file.path(output_dir, "cellchat_results.csv"),
            row.names = FALSE, quote = FALSE)
    } else {
        out <- data.frame(
            ligand   = df$ligand,
            receptor = df$receptor,
            source   = df$source,
            target   = df$target,
            pathway  = df$pathway_name,
            score    = df$prob,
            pvalue   = df$pval,
            stringsAsFactors = FALSE
        )
        write.csv(out, file.path(output_dir, "cellchat_results.csv"),
            row.names = FALSE, quote = FALSE)
        cat(sprintf("  L-R pairs: %d interactions across %d pathways\n",
            nrow(out), length(unique(out$pathway))))
    }

    # --- Export pathway-level aggregated results ---
    tryCatch({
        pathway_df <- subsetCommunication(cellchat, slot.name = "netP")
        if (nrow(pathway_df) > 0) {
            write.csv(pathway_df, file.path(output_dir, "cellchat_pathways.csv"),
                row.names = FALSE, quote = FALSE)
            cat(sprintf("  Pathways: %d pathway-level interactions\n", nrow(pathway_df)))
        }
    }, error = function(e) {
        cat(sprintf("  Note: pathway export skipped (%s)\n", e$message))
    })

    # --- Export centrality scores per pathway ---
    tryCatch({
        pathways <- cellchat@netP$pathways
        if (length(pathways) > 0) {
            centrality_records <- list()
            for (pw in pathways) {
                centr <- cellchat@netP$centr[[pw]]
                if (!is.null(centr)) {
                    ct_names <- names(centr$outdeg)
                    centrality_records[[length(centrality_records) + 1]] <- data.frame(
                        pathway = pw,
                        cell_type = ct_names,
                        outdeg_sender = centr$outdeg,
                        indeg_receiver = centr$indeg,
                        flowbet_mediator = if (!is.null(centr$flowbet)) centr$flowbet else 0,
                        info_influencer = if (!is.null(centr$info)) centr$info else 0,
                        stringsAsFactors = FALSE
                    )
                }
            }
            if (length(centrality_records) > 0) {
                centr_df <- do.call(rbind, centrality_records)
                write.csv(centr_df, file.path(output_dir, "cellchat_centrality.csv"),
                    row.names = FALSE, quote = FALSE)
                cat(sprintf("  Centrality: %d records across %d pathways\n",
                    nrow(centr_df), length(pathways)))
            }
        }
    }, error = function(e) {
        cat(sprintf("  Note: centrality export skipped (%s)\n", e$message))
    })

    # --- Export interaction count/weight matrices ---
    tryCatch({
        write.csv(cellchat@net$count, file.path(output_dir, "cellchat_count_matrix.csv"),
            quote = FALSE)
        write.csv(cellchat@net$weight, file.path(output_dir, "cellchat_weight_matrix.csv"),
            quote = FALSE)
        cat("  Matrices: count + weight exported\n")
    }, error = function(e) {
        cat(sprintf("  Note: matrix export skipped (%s)\n", e$message))
    })

    # --- Save RDS object for downstream multi-condition comparison ---
    tryCatch({
        saveRDS(cellchat, file.path(output_dir, "cellchat_object.rds"))
        cat("  RDS: CellChat object saved for downstream analysis\n")
    }, error = function(e) {
        cat(sprintf("  Note: RDS save skipped (%s)\n", e$message))
    })

    cat("Done.\n")

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
