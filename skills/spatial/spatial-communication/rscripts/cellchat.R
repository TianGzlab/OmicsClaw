#!/usr/bin/env Rscript
# OmicsClaw: CellChat cell-cell communication analysis
#
# Usage:
#   Rscript cellchat.R <input_directory> <output_dir> [cell_type_key] [species] [prob_type] [min_cells] [random_state]
#
# species: human | mouse (default: human)
# Spatial communication skill; expression is exchanged as Matrix Market.
#
# Input: adata.X must be log-normalized expression (not raw counts).
# CellChat requires "normalized data (library-size normalization and then
# log-transformed with a pseudocount of 1)" as input.
# The raw.use=TRUE parameter in computeCommunProb() refers to CellChat's
# internal signaling gene subset, NOT raw UMI counts.

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript cellchat.R <input_directory> <output_dir> [cell_type_key] [species] [prob_type] [min_cells] [random_state]\n")
    quit(status = 1)
}

input_dir     <- args[1]
output_dir    <- args[2]
cell_type_key <- if (length(args) >= 3) args[3] else "cell_type"
species       <- if (length(args) >= 4) args[4] else "human"
prob_type     <- if (length(args) >= 5) args[5] else "triMean"
min_cells     <- if (length(args) >= 6) as.integer(args[6]) else 10
random_state  <- if (length(args) >= 7) as.integer(args[7]) else 1

suppressPackageStartupMessages({
    library(CellChat)
    library(Matrix)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    counts <- Matrix::readMM(file.path(input_dir, "matrix.mtx"))
    rownames(counts) <- read.delim(file.path(input_dir, "features.tsv"), header=FALSE, colClasses="character")[[1]]
    colnames(counts) <- read.delim(file.path(input_dir, "barcodes.tsv"), header=FALSE, colClasses="character")[[1]]
    meta <- read.csv(file.path(input_dir, "obs.csv"), row.names=1,
                     check.names=FALSE, colClasses="character", na.strings=NULL)
    stopifnot(identical(colnames(counts), rownames(meta)))

    if (!cell_type_key %in% colnames(meta))
        stop(sprintf("Cell type key '%s' not found in metadata", cell_type_key))

    if (!"samples" %in% colnames(meta))
        meta$samples <- "sample1"

    labels <- unique(as.character(meta[[cell_type_key]]))
    safe_labels <- paste0("group_", seq_along(labels))
    label_map <- setNames(labels, safe_labels)
    meta[[cell_type_key]] <- factor(safe_labels[match(meta[[cell_type_key]], labels)])
    restore_label <- function(x) unname(label_map[as.character(x)])

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
    cellchat <- computeCommunProb(cellchat, raw.use = TRUE, type = prob_type, seed.use = random_state)
    cellchat <- filterCommunication(cellchat, min.cells = min_cells)
    cellchat <- computeCommunProbPathway(cellchat)
    cellchat <- aggregateNet(cellchat)

    cat("Computing network centrality metrics...\n")
    tryCatch({
        cellchat <- netAnalysis_computeCentrality(cellchat)
    }, error = function(e) {
        cat(sprintf("  Note: centrality computation skipped (%s)\n", e$message))
    })

    # --- Export L-R pair interactions ---
    df <- tryCatch(
        subsetCommunication(cellchat),
        error = function(e) {
            cat(sprintf("  Note: interaction export returned no significant hits (%s)\n", e$message))
            data.frame()
        }
    )

    if (!nrow(df)) {
        cat("WARNING: No significant interactions found\n")
        write.csv(data.frame(ligand=character(), receptor=character(), source=character(),
                             target=character(), score=numeric(), pvalue=numeric()),
                  file.path(output_dir, "cellchat_results.csv"),
            row.names = FALSE, quote = TRUE)
    } else {
        out <- data.frame(
            ligand   = df$ligand,
            receptor = df$receptor,
            source   = restore_label(df$source),
            target   = restore_label(df$target),
            pathway  = df$pathway_name,
            score    = df$prob,
            pvalue   = df$pval,
            stringsAsFactors = FALSE
        )
        write.csv(out, file.path(output_dir, "cellchat_results.csv"),
            row.names = FALSE, quote = TRUE)
        cat(sprintf("  L-R pairs: %d interactions across %d pathways\n",
            nrow(out), length(unique(out$pathway))))
    }

    # --- Export pathway-level aggregated results ---
    tryCatch({
        pathway_df <- subsetCommunication(cellchat, slot.name = "netP")
        if (nrow(pathway_df) > 0) {
            pathway_df$source <- restore_label(pathway_df$source)
            pathway_df$target <- restore_label(pathway_df$target)
            write.csv(pathway_df, file.path(output_dir, "cellchat_pathways.csv"),
                row.names = FALSE, quote = TRUE)
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
                        cell_type = restore_label(ct_names),
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
                    row.names = FALSE, quote = TRUE)
                cat(sprintf("  Centrality: %d records across %d pathways\n",
                    nrow(centr_df), length(pathways)))
            }
        }
    }, error = function(e) {
        cat(sprintf("  Note: centrality export skipped (%s)\n", e$message))
    })

    # --- Export interaction count/weight matrices ---
    tryCatch({
        dimnames(cellchat@net$count) <- lapply(dimnames(cellchat@net$count), restore_label)
        dimnames(cellchat@net$weight) <- lapply(dimnames(cellchat@net$weight), restore_label)
        write.csv(cellchat@net$count, file.path(output_dir, "cellchat_count_matrix.csv"),
            quote = TRUE)
        write.csv(cellchat@net$weight, file.path(output_dir, "cellchat_weight_matrix.csv"),
            quote = TRUE)
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
