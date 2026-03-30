# =============================================================================
# Cell-Cell Communication Analysis — PDF Report Generation
# =============================================================================
# Generates a publication-quality PDF report using rmarkdown.
# Falls back gracefully if rmarkdown or tinytex is unavailable.
# =============================================================================

#' Generate PDF report from CellChat analysis
#'
#' @param cellchat CellChat object
#' @param df_net Data frame of significant interactions
#' @param df_pathway Data frame of pathway-level interactions
#' @param output_dir Directory containing plots and for output
generate_report <- function(cellchat, df_net, df_pathway,
                            output_dir = "results") {

    # Check rmarkdown availability
    if (!requireNamespace("rmarkdown", quietly = TRUE)) {
        cat("   rmarkdown not installed — skipping PDF report\n")
        cat("   Install with: install.packages('rmarkdown')\n")
        return(invisible(NULL))
    }

    # Check for PDF rendering capability
    has_tinytex <- requireNamespace("tinytex", quietly = TRUE) &&
                   tinytex::is_tinytex()
    has_xelatex <- nchar(Sys.which("xelatex")) > 0
    has_pdflatex <- nchar(Sys.which("pdflatex")) > 0

    if (!has_tinytex && !has_xelatex && !has_pdflatex) {
        cat("   No LaTeX installation found — skipping PDF report\n")
        cat("   Install with: tinytex::install_tinytex()\n")
        return(invisible(NULL))
    }

    # Create temporary Rmd file
    rmd_path <- file.path(output_dir, "_report.Rmd")
    pdf_path <- file.path(output_dir, "analysis_report.pdf")

    pathways <- cellchat@netP$pathways
    cell_types <- levels(cellchat@idents)
    n_interactions <- nrow(df_net)
    n_pathways <- length(pathways)
    n_celltypes <- length(cell_types)

    # Top pathways
    top_pathways_text <- ""
    if (n_pathways > 0) {
        pathway_prob <- cellchat@netP$prob
        if (!is.null(pathway_prob) && length(dim(pathway_prob)) == 3) {
            pathway_strength <- apply(pathway_prob, 3, sum)
            pathway_strength <- sort(pathway_strength, decreasing = TRUE)
            top_n <- min(10, length(pathway_strength))
            top_pw <- data.frame(
                Pathway = names(pathway_strength)[1:top_n],
                Strength = round(pathway_strength[1:top_n], 4)
            )
            top_pathways_text <- knitr::kable(top_pw, format = "pipe")
            top_pathways_text <- paste(top_pathways_text, collapse = "\n")
        }
    }

    # Top interactions
    top_interactions_text <- ""
    if (n_interactions > 0) {
        df_top <- df_net[order(df_net$prob, decreasing = TRUE), ]
        df_top <- head(df_top, 10)
        ti <- data.frame(
            Source = df_top$source,
            Target = df_top$target,
            Interaction = df_top$interaction_name_2,
            Pathway = df_top$pathway_name,
            Prob = round(df_top$prob, 4)
        )
        top_interactions_text <- knitr::kable(ti, format = "pipe")
        top_interactions_text <- paste(top_interactions_text, collapse = "\n")
    }

    # Find available plot PNGs
    plot_files <- list.files(output_dir, pattern = "\\.png$", full.names = TRUE)
    plot_includes <- ""
    for (pf in plot_files) {
        if (!grepl("_report", pf)) {
            plot_name <- gsub("_", " ", tools::file_path_sans_ext(basename(pf)))
            plot_name <- tools::toTitleCase(plot_name)
            plot_includes <- paste0(plot_includes,
                "\n### ", plot_name, "\n\n",
                "![", plot_name, "](", basename(pf), ")\n\n")
        }
    }

    # Build Rmd content
    rmd_content <- paste0(
'---
title: "Cell-Cell Communication Analysis Report"
date: "', Sys.Date(), '"
output:
  pdf_document:
    toc: true
    toc_depth: 2
    latex_engine: xelatex
header-includes:
  - \\usepackage{booktabs}
  - \\usepackage{float}
  - \\floatplacement{figure}{H}
---

# Summary

| Metric | Value |
|--------|-------|
| Cell types | ', n_celltypes, ' |
| Significant interactions | ', n_interactions, ' |
| Active signaling pathways | ', n_pathways, ' |
| Analysis tool | CellChat v2 |

**Cell types analyzed:** ', paste(cell_types, collapse = ", "), '

# Introduction

This report presents cell-cell communication analysis results inferred from
single-cell RNA-seq data using CellChat v2. CellChat identifies intercellular
communication by modeling ligand-receptor interactions and quantifying
communication probabilities between cell populations.

# Methods

- **Ligand-receptor database:** CellChatDB v2
- **Communication inference:** triMean method (robust, favors stronger interactions)
- **Minimum cells per group:** 10
- **Network centrality:** Computed for sender, receiver, mediator, and influencer roles

# Results

## Top Signaling Pathways

', top_pathways_text, '

## Top Ligand-Receptor Interactions

', top_interactions_text, '

## Visualizations

', plot_includes, '

# Conclusions

- **', n_interactions, '** significant ligand-receptor interactions identified across **', n_pathways, '** signaling pathways
- Communication network analysis reveals the dominant senders and receivers among the ', n_celltypes, ' cell types
- Signaling role analysis identifies key mediator and influencer cell populations
- These results can guide target identification for therapeutic intervention

# References

1. Jin S, et al. Inference and analysis of cell-cell communication using CellChat. *Nature Communications*. 2021;12:1088.
2. Jin S, et al. CellChat for systematic analysis of cell-cell communication from single-cell and spatially resolved transcriptomics. *Nature Protocols*. 2024.
')

    writeLines(rmd_content, rmd_path)

    # Render PDF
    tryCatch({
        rmarkdown::render(
            rmd_path,
            output_file = basename(pdf_path),
            output_dir = output_dir,
            quiet = TRUE
        )
        cat("   Saved:", pdf_path, "\n")
    }, error = function(e) {
        cat("   PDF rendering failed:", conditionMessage(e), "\n")
        cat("   (Markdown report still available)\n")
    })

    # Clean up temporary Rmd
    unlink(rmd_path)

    return(invisible(pdf_path))
}

