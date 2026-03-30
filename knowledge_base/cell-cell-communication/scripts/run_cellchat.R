# =============================================================================
# Cell-Cell Communication Analysis — Core CellChat Pipeline
# =============================================================================
# Runs the complete CellChat v2 analysis: ligand-receptor identification,
# communication probability inference, pathway aggregation, and centrality.
# =============================================================================

suppressPackageStartupMessages({
    library(CellChat)
    library(Seurat)
})

#' Run complete CellChat analysis pipeline
#'
#' @param seurat_obj Annotated Seurat object
#' @param species "human" or "mouse"
#' @param group.by Metadata column with cell type annotations
#' @param db_category Which interaction categories to use:
#'   "all" (default), "Secreted Signaling", "ECM-Receptor", "Cell-Cell Contact"
#' @param min.cells Minimum cells per group for communication inference
#' @return CellChat object with all analyses computed
run_cellchat_analysis <- function(seurat_obj,
                                  species = "human",
                                  group.by = "celltype",
                                  db_category = "all",
                                  min.cells = 10) {

    cat("\n=== Running CellChat Analysis ===\n\n")

    # -------------------------------------------------------------------------
    # 1. Create CellChat object
    # -------------------------------------------------------------------------
    cat("Step 1/6: Creating CellChat object...\n")
    cellchat <- createCellChat(object = seurat_obj, group.by = group.by)
    cat("   Created CellChat object with", length(levels(cellchat@idents)),
        "cell groups\n")

    # -------------------------------------------------------------------------
    # 2. Set ligand-receptor database
    # -------------------------------------------------------------------------
    cat("Step 2/6: Setting CellChat database...\n")
    if (tolower(species) == "human") {
        CellChatDB <- CellChatDB.human
        cat("   Using CellChatDB.human\n")
    } else if (tolower(species) == "mouse") {
        CellChatDB <- CellChatDB.mouse
        cat("   Using CellChatDB.mouse\n")
    } else {
        stop("Species must be 'human' or 'mouse'. Got: ", species)
    }

    # Optionally filter to specific signaling category
    if (db_category != "all") {
        valid_cats <- unique(CellChatDB$interaction$annotation)
        if (!db_category %in% valid_cats) {
            stop("Invalid db_category '", db_category, "'. Valid options: ",
                 paste(valid_cats, collapse = ", "))
        }
        CellChatDB_use <- subsetDB(CellChatDB, search = db_category)
        cat("   Filtered to:", db_category, "\n")
    } else {
        CellChatDB_use <- CellChatDB
        cat("   Using all signaling categories\n")
    }

    cellchat@DB <- CellChatDB_use
    n_interactions <- nrow(CellChatDB_use$interaction)
    cat("   Database contains", n_interactions, "ligand-receptor interactions\n")

    # -------------------------------------------------------------------------
    # 3. Identify overexpressed genes and interactions
    # -------------------------------------------------------------------------
    cat("Step 3/6: Identifying overexpressed signaling genes...\n")
    cellchat <- subsetData(cellchat)

    # Use presto for fast Wilcoxon if available, otherwise standard
    has_presto <- requireNamespace("presto", quietly = TRUE)
    if (!has_presto) {
        cat("   (presto not installed — using standard Wilcoxon test, slower)\n")
    }
    cellchat <- identifyOverExpressedGenes(cellchat,
                                            do.fast = has_presto)
    cellchat <- identifyOverExpressedInteractions(cellchat)
    n_LR <- nrow(cellchat@LR$LRsig)
    cat("   Identified", n_LR, "overexpressed ligand-receptor pairs\n")

    # -------------------------------------------------------------------------
    # 4. Compute communication probabilities
    # -------------------------------------------------------------------------
    cat("Step 4/6: Computing communication probabilities...\n")
    cat("   (This may take 1-3 minutes depending on dataset size)\n")
    cellchat <- computeCommunProb(cellchat, type = "triMean")
    cellchat <- filterCommunication(cellchat, min.cells = min.cells)

    # Count significant interactions
    df_net <- subsetCommunication(cellchat)
    n_sig <- nrow(df_net)
    cat("   Found", n_sig, "significant cell-cell interactions\n")

    # -------------------------------------------------------------------------
    # 5. Pathway-level aggregation
    # -------------------------------------------------------------------------
    cat("Step 5/6: Aggregating at pathway level...\n")
    cellchat <- computeCommunProbPathway(cellchat)
    cellchat <- aggregateNet(cellchat)

    # Count active pathways
    pathways <- cellchat@netP$pathways
    n_pathways <- length(pathways)
    cat("   Aggregated into", n_pathways, "signaling pathways\n")

    # Print top pathways by overall information flow
    if (n_pathways > 0) {
        cat("\n   Top signaling pathways:\n")
        # Get pathway contribution
        pathway_prob <- cellchat@netP$prob
        if (!is.null(pathway_prob) && length(dim(pathway_prob)) == 3) {
            pathway_strength <- apply(pathway_prob, 3, sum)
            pathway_strength <- sort(pathway_strength, decreasing = TRUE)
            top_n <- min(10, length(pathway_strength))
            for (i in seq_len(top_n)) {
                cat(sprintf("     %2d. %-20s (strength: %.4f)\n",
                    i, names(pathway_strength)[i], pathway_strength[i]))
            }
        }
    }

    # -------------------------------------------------------------------------
    # 6. Compute network centrality
    # -------------------------------------------------------------------------
    cat("\nStep 6/6: Computing network centrality scores...\n")
    cellchat <- netAnalysis_computeCentrality(cellchat)
    cat("   Computed sender, receiver, mediator, and influencer roles\n")

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    cat("\n--- Analysis Summary ---\n")
    cat("   Species:", species, "\n")
    cat("   Cell types:", length(levels(cellchat@idents)), "\n")
    cat("   L-R pairs tested:", n_LR, "\n")
    cat("   Significant interactions:", n_sig, "\n")
    cat("   Active pathways:", n_pathways, "\n")

    cat("\n✓ CellChat analysis completed!", n_sig,
        "significant interactions across", n_pathways, "pathways\n\n")

    return(cellchat)
}

