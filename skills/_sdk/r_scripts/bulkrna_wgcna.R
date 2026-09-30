#!/usr/bin/env Rscript
# OmicsClaw: WGCNA co-expression network analysis
#
# Usage:
#   Rscript bulkrna_wgcna.R <counts_csv> <output_dir> [min_module_size] [merge_cut_height]
#
# counts_csv: genes as rows, samples as columns (first col = gene names)

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 2) {
    cat("Usage: Rscript bulkrna_wgcna.R <counts.csv> <output_dir> [min_module_size] [merge_cut_height]\n")
    quit(status = 1)
}

counts_file      <- args[1]
output_dir       <- args[2]
min_module_size  <- if (length(args) >= 3) as.integer(args[3]) else 30L
merge_cut_height <- if (length(args) >= 4) as.numeric(args[4]) else 0.25

suppressPackageStartupMessages({
    library(WGCNA)
})

allowWGCNAThreads()

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading expression data...\n")
    raw <- read.csv(counts_file, row.names = 1, check.names = FALSE)

    # WGCNA expects samples as rows, genes as columns
    datExpr <- t(raw)
    cat(sprintf("  %d samples x %d genes\n", nrow(datExpr), ncol(datExpr)))

    # Filter genes with too many missing values or zero variance
    gsg <- goodSamplesGenes(datExpr, verbose = 0)
    if (!gsg$allOK) {
        datExpr <- datExpr[gsg$goodSamples, gsg$goodGenes]
        cat(sprintf("  Filtered to %d samples x %d genes\n", nrow(datExpr), ncol(datExpr)))
    }

    # Step 1: Pick soft-thresholding power
    cat("Step 1: Selecting soft-thresholding power...\n")
    powers <- c(1:10, seq(12, 20, 2))
    sft <- pickSoftThreshold(datExpr, powerVector = powers, verbose = 0)

    # Find first power with R² > 0.8
    fit_index <- sft$fitIndices
    r2_vals <- -sign(fit_index[, 3]) * fit_index[, 2]
    best_idx <- which(r2_vals > 0.8)[1]
    if (is.na(best_idx)) best_idx <- which.max(r2_vals)
    soft_power <- fit_index[best_idx, 1]
    cat(sprintf("  Selected power: %d (R² = %.3f)\n", soft_power, r2_vals[best_idx]))

    # Write power selection results
    write.csv(fit_index, file.path(output_dir, "soft_power_table.csv"),
        row.names = FALSE, quote = FALSE)

    # Step 2: Build network and detect modules
    cat("Step 2: Building network and detecting modules...\n")
    net <- blockwiseModules(
        datExpr,
        power = soft_power,
        minModuleSize = min_module_size,
        mergeCutHeight = merge_cut_height,
        reassignThreshold = 0,
        numericLabels = TRUE,
        pamRespectsDendro = FALSE,
        saveTOMs = FALSE,
        verbose = 0
    )

    module_labels <- net$colors
    module_colors <- labels2colors(module_labels)
    n_modules <- length(unique(module_colors)) - 1  # Exclude grey (unassigned)
    cat(sprintf("  Detected %d modules\n", n_modules))

    # Step 3: Module membership and hub genes
    cat("Step 3: Computing module membership and identifying hub genes...\n")
    MEs <- moduleEigengenes(datExpr, colors = module_colors)$eigengenes

    gene_module_df <- data.frame(
        gene = colnames(datExpr),
        module = module_colors,
        stringsAsFactors = FALSE
    )

    # Compute intramodular connectivity (kME)
    kME <- cor(datExpr, MEs, use = "p")
    colnames(kME) <- gsub("^ME", "", colnames(kME))

    # For each module, identify top hub genes
    hub_list <- list()
    for (mod in unique(module_colors)) {
        if (mod == "grey") next
        mod_genes <- gene_module_df$gene[gene_module_df$module == mod]
        me_col <- paste0("ME", mod)
        if (me_col %in% colnames(MEs)) {
            kme_vals <- abs(kME[mod_genes, mod, drop = TRUE])
            top_n <- min(10, length(kme_vals))
            top_genes <- head(sort(kme_vals, decreasing = TRUE), top_n)
            for (g in names(top_genes)) {
                hub_list[[length(hub_list) + 1]] <- data.frame(
                    gene = g, module = mod, kME = top_genes[[g]],
                    stringsAsFactors = FALSE
                )
            }
        }
    }
    hub_df <- do.call(rbind, hub_list)

    # Write outputs
    write.csv(gene_module_df, file.path(output_dir, "gene_modules.csv"),
        row.names = FALSE, quote = FALSE)
    write.csv(MEs, file.path(output_dir, "module_eigengenes.csv"), quote = FALSE)
    write.csv(hub_df, file.path(output_dir, "hub_genes.csv"),
        row.names = FALSE, quote = FALSE)
    write.csv(as.data.frame(kME), file.path(output_dir, "kME.csv"), quote = FALSE)

    # Summary
    cat(sprintf('{"n_modules": %d, "soft_power": %d, "n_genes": %d, "n_samples": %d}\n',
        n_modules, soft_power, ncol(datExpr), nrow(datExpr)),
        file = file.path(output_dir, "wgcna_info.json"))

    cat(sprintf("Done. %d modules, power=%d, %d hub genes\n",
        n_modules, soft_power, nrow(hub_df)))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
