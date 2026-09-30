#!/usr/bin/env Rscript
# OmicsClaw: clusterProfiler GSEA / ORA for bulk RNA-seq
#
# Usage:
#   Rscript bulkrna_enrichment.R <de_results_csv> <output_dir> <method> [organism] [gene_sets]
#
# method: gsea | ora
# organism: human | mouse (default: human)
# gene_sets: H | C2 | C5 | C7 (MSigDB collections, default: H)
#
# de_results_csv must have columns: gene, log2FoldChange, pvalue (or padj)

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 3) {
    cat("Usage: Rscript bulkrna_enrichment.R <de_results.csv> <output_dir> <method>",
        "[organism] [gene_sets]\n")
    quit(status = 1)
}

de_file    <- args[1]
output_dir <- args[2]
method     <- args[3]
organism   <- if (length(args) >= 4) args[4] else "human"
gene_sets  <- if (length(args) >= 5) args[5] else "H"

suppressPackageStartupMessages({
    library(clusterProfiler)
    library(msigdbr)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat(sprintf("Loading DE results from %s...\n", de_file))
    de <- read.csv(de_file, check.names = FALSE)

    # Ensure required columns
    if (!"gene" %in% colnames(de)) {
        if ("X" %in% colnames(de)) de$gene <- de$X
        else stop("DE results must have a 'gene' column")
    }
    if (!"log2FoldChange" %in% colnames(de)) {
        if ("log2fc" %in% colnames(de)) de$log2FoldChange <- de$log2fc
        else if ("logFC" %in% colnames(de)) de$log2FoldChange <- de$logFC
    }

    cat(sprintf("  %d genes loaded\n", nrow(de)))

    # Get gene sets from MSigDB
    species_map <- list(human = "Homo sapiens", mouse = "Mus musculus")
    species_name <- species_map[[organism]]
    if (is.null(species_name)) stop(sprintf("Unsupported organism: %s", organism))

    cat(sprintf("Loading MSigDB %s gene sets for %s...\n", gene_sets, species_name))
    msig <- msigdbr(species = species_name, category = gene_sets)
    term2gene <- msig[, c("gs_name", "gene_symbol")]
    cat(sprintf("  %d gene sets, %d gene-set entries\n",
        length(unique(term2gene$gs_name)), nrow(term2gene)))

    if (method == "gsea") {
        # GSEA: need ranked gene list
        if (!"log2FoldChange" %in% colnames(de))
            stop("GSEA requires 'log2FoldChange' column for ranking")

        de <- de[!is.na(de$log2FoldChange), ]
        ranked <- de$log2FoldChange
        names(ranked) <- de$gene
        ranked <- sort(ranked, decreasing = TRUE)

        cat(sprintf("Running GSEA on %d ranked genes...\n", length(ranked)))
        result <- GSEA(
            geneList     = ranked,
            TERM2GENE    = term2gene,
            minGSSize    = 15,
            maxGSSize    = 500,
            pvalueCutoff = 1.0,
            pAdjustMethod = "BH",
            nPermSimple  = 10000,
            seed         = TRUE,
            verbose      = FALSE
        )

        out <- as.data.frame(result)
        write.csv(out, file.path(output_dir, "gsea_results.csv"),
            row.names = FALSE, quote = FALSE)

        n_sig <- sum(out$p.adjust < 0.05, na.rm = TRUE)
        cat(sprintf("Done. %d enriched gene sets (FDR < 0.05) out of %d tested\n",
            n_sig, nrow(out)))

    } else if (method == "ora") {
        # ORA: need significant gene list + background
        padj_col <- if ("padj" %in% colnames(de)) "padj" else "pvalue"
        lfc_col  <- if ("log2FoldChange" %in% colnames(de)) "log2FoldChange" else NULL

        sig_mask <- de[[padj_col]] < 0.05
        if (!is.null(lfc_col)) sig_mask <- sig_mask & abs(de[[lfc_col]]) > 1
        sig_mask[is.na(sig_mask)] <- FALSE

        sig_genes  <- de$gene[sig_mask]
        background <- de$gene

        cat(sprintf("Running ORA with %d significant genes (background: %d)...\n",
            length(sig_genes), length(background)))

        if (length(sig_genes) == 0) {
            cat("WARNING: No significant genes for ORA\n")
            write.csv(data.frame(), file.path(output_dir, "ora_results.csv"),
                row.names = FALSE, quote = FALSE)
        } else {
            result <- enricher(
                gene      = sig_genes,
                TERM2GENE = term2gene,
                universe  = background,
                pvalueCutoff  = 1.0,
                pAdjustMethod = "BH",
                minGSSize     = 10,
                maxGSSize     = 500
            )

            out <- as.data.frame(result)
            write.csv(out, file.path(output_dir, "ora_results.csv"),
                row.names = FALSE, quote = FALSE)

            n_sig <- sum(out$p.adjust < 0.05, na.rm = TRUE)
            cat(sprintf("Done. %d enriched gene sets (FDR < 0.05) out of %d tested\n",
                n_sig, nrow(out)))
        }
    } else {
        stop(sprintf("Unknown method: %s. Use 'gsea' or 'ora'", method))
    }

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
