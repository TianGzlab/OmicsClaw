# =============================================================================
# Cell-Cell Communication Analysis — Export Results
# =============================================================================
# Exports all CellChat analysis results: CSV tables, CellChat RDS object,
# markdown report, and PDF report (via generate_report.R).
# =============================================================================

suppressPackageStartupMessages({
    library(CellChat)
})

#' Export all CellChat analysis results
#'
#' @param cellchat CellChat object (from run_cellchat_analysis)
#' @param seurat_obj Original Seurat object (optional, for metadata export)
#' @param output_dir Output directory
export_all <- function(cellchat, seurat_obj = NULL, output_dir = "results") {

    cat("\n=== Exporting Results ===\n\n")

    dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

    # -------------------------------------------------------------------------
    # 1. Significant interactions (all L-R pairs with statistics)
    # -------------------------------------------------------------------------
    cat("1. Significant interactions...\n")
    df_net <- subsetCommunication(cellchat)
    write.csv(df_net, file.path(output_dir, "significant_interactions.csv"),
              row.names = FALSE)
    cat("   Saved:", file.path(output_dir, "significant_interactions.csv"),
        "(", nrow(df_net), "interactions )\n")

    # -------------------------------------------------------------------------
    # 2. Pathway-level summary
    # -------------------------------------------------------------------------
    cat("2. Pathway-level summary...\n")
    df_pathway <- subsetCommunication(cellchat, slot.name = "netP")
    write.csv(df_pathway, file.path(output_dir, "pathway_summary.csv"),
              row.names = FALSE)
    cat("   Saved:", file.path(output_dir, "pathway_summary.csv"),
        "(", nrow(df_pathway), "pathway-level interactions )\n")

    # -------------------------------------------------------------------------
    # 3. Interaction count matrix (cell type × cell type)
    # -------------------------------------------------------------------------
    cat("3. Interaction count matrix...\n")
    count_mat <- cellchat@net$count
    write.csv(count_mat, file.path(output_dir, "interaction_count_matrix.csv"))
    cat("   Saved:", file.path(output_dir, "interaction_count_matrix.csv"), "\n")

    # -------------------------------------------------------------------------
    # 4. Interaction strength matrix (cell type × cell type)
    # -------------------------------------------------------------------------
    cat("4. Interaction strength matrix...\n")
    weight_mat <- cellchat@net$weight
    write.csv(weight_mat, file.path(output_dir, "interaction_strength_matrix.csv"))
    cat("   Saved:", file.path(output_dir, "interaction_strength_matrix.csv"), "\n")

    # -------------------------------------------------------------------------
    # 5. Signaling roles (centrality scores)
    # -------------------------------------------------------------------------
    cat("5. Signaling role scores...\n")
    tryCatch({
        # Extract centrality measures for each pathway
        centr_list <- list()
        pathways <- cellchat@netP$pathways
        for (pw in pathways) {
            pw_centr <- tryCatch(
                cellchat@netP$centr[[pw]],
                error = function(e) NULL
            )
            if (!is.null(pw_centr)) {
                df_pw <- data.frame(
                    pathway = pw,
                    cell_type = names(pw_centr$outdeg),
                    outdeg_sender = pw_centr$outdeg,
                    indeg_receiver = pw_centr$indeg,
                    flowbet_mediator = if (!is.null(pw_centr$flowbet)) pw_centr$flowbet else NA,
                    info_influencer = if (!is.null(pw_centr$info)) pw_centr$info else NA,
                    stringsAsFactors = FALSE
                )
                centr_list[[pw]] <- df_pw
            }
        }
        if (length(centr_list) > 0) {
            df_centr <- do.call(rbind, centr_list)
            rownames(df_centr) <- NULL
            write.csv(df_centr, file.path(output_dir, "signaling_roles.csv"),
                      row.names = FALSE)
            cat("   Saved:", file.path(output_dir, "signaling_roles.csv"),
                "(", length(pathways), "pathways )\n")
        }
    }, error = function(e) {
        cat("   ⚠ Signaling roles export failed:", conditionMessage(e), "\n")
    })

    # -------------------------------------------------------------------------
    # 6. Top interactions summary (human-readable)
    # -------------------------------------------------------------------------
    cat("6. Top interactions summary...\n")
    tryCatch({
        # Top 20 by communication probability
        if (nrow(df_net) > 0) {
            df_top <- df_net[order(df_net$prob, decreasing = TRUE), ]
            df_top <- head(df_top, 20)
            write.csv(df_top, file.path(output_dir, "top_interactions.csv"),
                      row.names = FALSE)
            cat("   Saved:", file.path(output_dir, "top_interactions.csv"), "\n")
        }
    }, error = function(e) {
        cat("   ⚠ Top interactions export failed:", conditionMessage(e), "\n")
    })

    # -------------------------------------------------------------------------
    # 7. CellChat object (CRITICAL for downstream use)
    # -------------------------------------------------------------------------
    cat("7. CellChat analysis object (RDS)...\n")
    saveRDS(cellchat, file.path(output_dir, "cellchat_object.rds"))
    cat("   Saved:", file.path(output_dir, "cellchat_object.rds"), "\n")
    cat("   (Load with: cellchat <- readRDS('cellchat_object.rds'))\n")

    # -------------------------------------------------------------------------
    # 8. Markdown report (always generated)
    # -------------------------------------------------------------------------
    cat("8. Generating markdown report...\n")
    .generate_markdown_report(cellchat, df_net, df_pathway, output_dir)
    cat("   Saved:", file.path(output_dir, "analysis_report.md"), "\n")

    # -------------------------------------------------------------------------
    # 9. PDF report (optional, via generate_report.R)
    # -------------------------------------------------------------------------
    cat("9. Generating PDF report...\n")
    tryCatch({
        source("scripts/generate_report.R")
        generate_report(cellchat, df_net, df_pathway, output_dir = output_dir)
    }, error = function(e) {
        cat("   PDF generation skipped:", conditionMessage(e), "\n")
        cat("   (Markdown report still available)\n")
    })

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    cat("\n=== Export Complete ===\n")
    cat("\nOutput files in '", output_dir, "/':\n")
    output_files <- list.files(output_dir, full.names = FALSE)
    for (f in sort(output_files)) {
        fsize <- file.size(file.path(output_dir, f))
        cat(sprintf("  %-45s %s\n", f, .format_size(fsize)))
    }
    cat("\n")
}


# --- Helper: format file size ------------------------------------------------
.format_size <- function(bytes) {
    if (is.na(bytes)) return("")
    if (bytes < 1024) return(paste0(bytes, " B"))
    if (bytes < 1024^2) return(sprintf("%.1f KB", bytes / 1024))
    return(sprintf("%.1f MB", bytes / 1024^2))
}


# --- Helper: Markdown report -------------------------------------------------
.generate_markdown_report <- function(cellchat, df_net, df_pathway, output_dir) {

    pathways <- cellchat@netP$pathways
    cell_types <- levels(cellchat@idents)

    lines <- c(
        "# Cell-Cell Communication Analysis Report",
        "",
        paste("**Date:**", Sys.Date()),
        paste("**Tool:** CellChat v2"),
        "",
        "## Summary",
        "",
        paste("- **Cell types analyzed:**", length(cell_types)),
        paste("- **Significant interactions:**", nrow(df_net)),
        paste("- **Active signaling pathways:**", length(pathways)),
        "",
        "## Introduction",
        "",
        "This report presents cell-cell communication analysis results inferred from",
        "single-cell RNA-seq data using CellChat v2. CellChat identifies intercellular",
        "communication by modeling ligand-receptor interactions and quantifying",
        "communication probabilities between cell populations.",
        "",
        "### Cell Types",
        "",
        paste("-", cell_types),
        "",
        "## Results",
        "",
        "### Top Signaling Pathways",
        ""
    )

    # Top pathways by information flow
    if (length(pathways) > 0) {
        pathway_prob <- cellchat@netP$prob
        if (!is.null(pathway_prob) && length(dim(pathway_prob)) == 3) {
            pathway_strength <- apply(pathway_prob, 3, sum)
            pathway_strength <- sort(pathway_strength, decreasing = TRUE)
            top_n <- min(15, length(pathway_strength))
            lines <- c(lines,
                "| Rank | Pathway | Strength |",
                "|------|---------|----------|"
            )
            for (i in seq_len(top_n)) {
                lines <- c(lines, sprintf("| %d | %s | %.4f |",
                    i, names(pathway_strength)[i], pathway_strength[i]))
            }
        }
    }

    lines <- c(lines, "",
        "### Top Ligand-Receptor Interactions",
        ""
    )

    if (nrow(df_net) > 0) {
        df_top <- df_net[order(df_net$prob, decreasing = TRUE), ]
        df_top <- head(df_top, 15)
        lines <- c(lines,
            "| Source | Target | Interaction | Pathway | Probability |",
            "|--------|--------|-------------|---------|-------------|"
        )
        for (i in seq_len(nrow(df_top))) {
            lines <- c(lines, sprintf("| %s | %s | %s | %s | %.4f |",
                df_top$source[i], df_top$target[i],
                df_top$interaction_name_2[i], df_top$pathway_name[i],
                df_top$prob[i]))
        }
    }

    lines <- c(lines, "",
        "## Methods",
        "",
        "Cell-cell communication was inferred using CellChat v2 (Jin et al., Nature Communications 2021).",
        "Ligand-receptor interactions were identified from the CellChatDB database.",
        "Communication probabilities were computed using the triMean method.",
        "Network centrality analysis was performed to identify dominant senders, receivers, mediators, and influencers.",
        "",
        "## Conclusions",
        "",
        paste("- **", nrow(df_net), "** significant ligand-receptor interactions identified across **",
              length(pathways), "** signaling pathways"),
        paste("- Communication network analysis reveals dominant senders and receivers among",
              length(cell_types), "cell types"),
        "- Signaling role analysis identifies key mediator and influencer cell populations",
        "- These results can guide target identification for therapeutic intervention",
        "",
        "## References",
        "",
        "- Jin S, et al. Inference and analysis of cell-cell communication using CellChat. Nature Communications. 2021;12:1088.",
        "- Jin S, et al. CellChat for systematic analysis of cell-cell communication from single-cell and spatially resolved transcriptomics. Nature Protocols. 2024."
    )

    writeLines(lines, file.path(output_dir, "analysis_report.md"))
}

