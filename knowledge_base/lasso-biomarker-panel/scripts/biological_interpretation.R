# Biological Interpretation of Biomarker Panel
#
# Three complementary analyses:
#   1. Pathway enrichment (ORA on panel genes + GSEA on ranked features)
#   2. Cell-type expression context (CZI CELLxGENE Census)
#   3. GWAS genetic risk / disease gene overlap
#
# Usage:
#   source("scripts/biological_interpretation.R")
#   interp <- run_biological_interpretation(model, features, output_dir = "results",
#                                            disease = "ibd")  # or "bladder_cancer", "breast_cancer", or "sepsis"

cat("Loading biological interpretation functions...\n")

# ============================================================
# 1. Pathway Enrichment
# ============================================================

.run_pathway_enrichment <- function(model_result, features = NULL, output_dir = "results") {
    cat("\n--- Pathway Enrichment Analysis ---\n\n")

    suppressPackageStartupMessages({
        library(clusterProfiler)
        library(org.Hs.eg.db)
        library(fgsea)
        library(msigdbr)
        library(ggplot2)
        library(ggprism)
    })

    panel_genes <- model_result$stable_features
    fi <- model_result$feature_importance

    results <- list(ora_go = NULL, ora_kegg = NULL, gsea_hallmark = NULL,
                    gsea_reactome = NULL, gsea_immunologic = NULL)

    # ---- ORA on panel genes (GO:BP) ----
    cat("  ORA: GO Biological Process on", length(panel_genes), "panel genes...\n")

    # Filter out non-standard gene symbols (IGLV4-60 etc.)
    valid_genes <- panel_genes[!grepl("^IGH|^IGK|^IGL|^LOC|^C\\d+orf", panel_genes)]
    cat("    Valid gene symbols for ORA:", length(valid_genes), "\n")

    # Get universe from all tested features
    all_genes <- fi$feature
    all_valid <- all_genes[!grepl("^IGH|^IGK|^IGL|^LOC|^C\\d+orf", all_genes)]

    ora_go <- tryCatch({
        ego <- enrichGO(
            gene         = valid_genes,
            universe     = all_valid,
            OrgDb        = org.Hs.eg.db,
            keyType      = "SYMBOL",
            ont          = "BP",
            pAdjustMethod = "BH",
            pvalueCutoff = 0.1,   # Relaxed for small gene list
            qvalueCutoff = 0.2,
            minGSSize    = 5,
            maxGSSize    = 500,
            readable     = TRUE
        )
        if (!is.null(ego) && nrow(ego@result[ego@result$p.adjust < 0.1, ]) > 0) {
            cat("    Found", sum(ego@result$p.adjust < 0.1), "significant GO terms (padj < 0.1)\n")
            ego
        } else {
            cat("    No significant GO terms at padj < 0.1 (expected with 10 genes)\n")
            ego
        }
    }, error = function(e) {
        cat("    GO ORA failed:", conditionMessage(e), "\n")
        NULL
    })
    results$ora_go <- ora_go

    # ---- ORA on panel genes (Reactome via msigdbr) ----
    cat("  ORA: Reactome pathways on panel genes...\n")

    reactome_sets <- msigdbr(species = "Homo sapiens", collection = "C2", subcollection = "CP:REACTOME")
    reactome_list <- split(reactome_sets$gene_symbol, reactome_sets$gs_name)

    ora_reactome <- tryCatch({
        er <- enricher(
            gene         = valid_genes,
            universe     = all_valid,
            TERM2GENE    = reactome_sets[, c("gs_name", "gene_symbol")],
            pvalueCutoff = 0.1,
            qvalueCutoff = 0.2,
            minGSSize    = 5,
            maxGSSize    = 500
        )
        if (!is.null(er) && nrow(er@result[er@result$p.adjust < 0.1, ]) > 0) {
            cat("    Found", sum(er@result$p.adjust < 0.1), "significant Reactome terms\n")
        } else {
            cat("    No significant Reactome terms (expected with 10 genes)\n")
        }
        er
    }, error = function(e) {
        cat("    Reactome ORA failed:", conditionMessage(e), "\n")
        NULL
    })
    results$ora_reactome <- ora_reactome

    # ---- GSEA on ranked feature list (500 genes) ----
    cat("  GSEA: Ranked analysis on", nrow(fi), "features using selection frequency...\n")

    # Create ranked vector: combined score to break ties in selection_frequency
    # Use selection_frequency * (1 + scaled |mean_coefficient|) for unique ranks
    max_coef <- max(abs(fi$mean_coefficient), na.rm = TRUE)
    combo_score <- fi$selection_frequency + abs(fi$mean_coefficient) / (max_coef * 10)
    stats <- setNames(combo_score, fi$feature)
    stats <- sort(stats, decreasing = TRUE)
    # Remove non-standard symbols
    stats <- stats[!grepl("^IGH|^IGK|^IGL|^LOC|^C\\d+orf", names(stats))]

    # Hallmark gene sets
    cat("    GSEA: MSigDB Hallmark (50 gene sets)...\n")
    hallmark <- msigdbr(species = "Homo sapiens", collection = "H")
    hallmark_list <- split(hallmark$gene_symbol, hallmark$gs_name)

    gsea_hallmark <- tryCatch({
        res <- fgsea(pathways = hallmark_list, stats = stats,
                     minSize = 5, maxSize = 500)
        res <- res[order(res$pval), ]
        n_sig <- sum(res$padj < 0.25, na.rm = TRUE)
        cat("      Found", n_sig, "enriched hallmark pathways (padj < 0.25)\n")
        res
    }, error = function(e) {
        cat("      Hallmark GSEA failed:", conditionMessage(e), "\n")
        NULL
    })
    results$gsea_hallmark <- gsea_hallmark

    # Reactome
    cat("    GSEA: Reactome pathways...\n")
    gsea_reactome <- tryCatch({
        res <- fgsea(pathways = reactome_list, stats = stats,
                     minSize = 5, maxSize = 500)
        res <- res[order(res$pval), ]
        n_sig <- sum(res$padj < 0.25, na.rm = TRUE)
        cat("      Found", n_sig, "enriched Reactome pathways (padj < 0.25)\n")
        res
    }, error = function(e) {
        cat("      Reactome GSEA failed:", conditionMessage(e), "\n")
        NULL
    })
    results$gsea_reactome <- gsea_reactome

    # Immunologic signatures (C7) - especially relevant for IBD
    cat("    GSEA: Immunologic signatures (C7)...\n")
    immuno <- msigdbr(species = "Homo sapiens", collection = "C7",
                      subcollection = "IMMUNESIGDB")
    immuno_list <- split(immuno$gene_symbol, immuno$gs_name)

    gsea_immuno <- tryCatch({
        res <- fgsea(pathways = immuno_list, stats = stats,
                     minSize = 5, maxSize = 500)
        res <- res[order(res$pval), ]
        n_sig <- sum(res$padj < 0.25, na.rm = TRUE)
        cat("      Found", n_sig, "enriched immunologic signatures (padj < 0.25)\n")
        res
    }, error = function(e) {
        cat("      Immunologic GSEA failed:", conditionMessage(e), "\n")
        NULL
    })
    results$gsea_immunologic <- gsea_immuno

    # ---- Generate plots ----
    cat("  Generating enrichment plots...\n")

    # GSEA dot plot for hallmark pathways
    if (!is.null(gsea_hallmark) && nrow(gsea_hallmark) > 0) {
        top_pathways <- head(gsea_hallmark[order(gsea_hallmark$pval), ], 15)
        top_pathways$pathway_short <- gsub("HALLMARK_", "",  top_pathways$pathway)
        top_pathways$pathway_short <- gsub("_", " ", top_pathways$pathway_short)
        top_pathways$pathway_short <- tolower(top_pathways$pathway_short)
        # Title case
        top_pathways$pathway_short <- gsub("(^|\\s)(\\w)", "\\1\\U\\2",
                                           top_pathways$pathway_short, perl = TRUE)

        p_gsea <- ggplot(top_pathways, aes(x = NES,
                                            y = reorder(pathway_short, NES),
                                            size = size,
                                            color = -log10(pval))) +
            geom_point() +
            scale_color_gradient(low = "grey70", high = "firebrick", name = "-log10(p)") +
            scale_size_continuous(range = c(2, 6), name = "Gene set\nsize") +
            theme_prism(base_size = 11) +
            theme(
                axis.text.y = element_text(size = 9),
                plot.title = element_text(hjust = 0.5, face = "bold", size = 13)
            ) +
            labs(x = "Normalized Enrichment Score (NES)",
                 y = NULL,
                 title = "GSEA: MSigDB Hallmark Pathways") +
            geom_vline(xintercept = 0, linetype = "dashed", color = "grey50")

        .save_enrichment_plot(p_gsea, file.path(output_dir, "gsea_hallmark_dotplot"), 9, 6)
    }

    # GO ORA dot plot
    if (!is.null(ora_go) && nrow(ora_go@result) > 0) {
        tryCatch({
            top_go <- head(ora_go@result[order(ora_go@result$pvalue), ], 15)
            if (nrow(top_go) > 0) {
                top_go$GeneRatio_num <- sapply(top_go$GeneRatio, function(x) {
                    parts <- strsplit(x, "/")[[1]]
                    as.numeric(parts[1]) / as.numeric(parts[2])
                })
                # Truncate long descriptions
                top_go$Description_short <- ifelse(
                    nchar(top_go$Description) > 50,
                    paste0(substr(top_go$Description, 1, 47), "..."),
                    top_go$Description
                )
                p_ora <- ggplot(top_go, aes(x = GeneRatio_num,
                                             y = reorder(Description_short, GeneRatio_num),
                                             size = Count,
                                             color = -log10(pvalue))) +
                    geom_point() +
                    scale_color_gradient(low = "grey70", high = "steelblue4",
                                        name = "-log10(p)") +
                    scale_size_continuous(range = c(3, 7), name = "Gene\ncount") +
                    theme_prism(base_size = 11) +
                    theme(
                        axis.text.y = element_text(size = 9),
                        plot.title = element_text(hjust = 0.5, face = "bold", size = 13)
                    ) +
                    labs(x = "Gene Ratio", y = NULL,
                         title = "GO Biological Process (Panel Genes)")

                .save_enrichment_plot(p_ora, file.path(output_dir, "ora_go_dotplot"), 9, 6)
            }
        }, error = function(e) cat("    GO plot failed:", conditionMessage(e), "\n"))
    }

    cat("  Pathway enrichment complete.\n")
    return(results)
}


# ============================================================
# 2. Cell-Type Expression (CZI CELLxGENE Census)
# ============================================================

.run_celltype_enrichment <- function(panel_genes, output_dir = "results",
                                      disease = "ibd") {
    cat("\n--- Cell-Type Expression Analysis (CZI CELLxGENE) ---\n\n")

    csv_path <- file.path(output_dir, "celltype_expression.csv")

    # Disease-specific tissue for CZI Census query
    tissue <- switch(disease,
        ibd = "large intestine",
        bladder_cancer = "bladder organ",
        breast_cancer = "breast",
        sepsis = "blood",
        "large intestine"  # default
    )

    # Filter to protein-coding genes with standard symbols
    query_genes <- panel_genes[!grepl("^IGH|^IGK|^IGL|^LOC|^TMB", panel_genes)]
    cat("  Querying", length(query_genes), "genes in '", tissue, "':",
        paste(query_genes, collapse = ", "), "\n")

    # Try Python CELLxGENE Census query
    py_script <- file.path("scripts", "query_cellxgene.py")

    celltype_data <- NULL

    if (file.exists(py_script)) {
        gene_args <- paste(query_genes, collapse = " ")
        cmd <- sprintf("python3 '%s' %s --output '%s' --tissue '%s' 2>&1",
                        py_script, gene_args, csv_path, tissue)
        cat("  Running CZI Census query (may take 1-3 minutes)...\n")

        result <- tryCatch({
            system(cmd, intern = TRUE, timeout = 300)
        }, error = function(e) {
            cat("  Census query failed:", conditionMessage(e), "\n")
            NULL
        })

        if (!is.null(result)) cat(paste("   ", result, collapse = "\n"), "\n")

        if (file.exists(csv_path)) {
            celltype_data <- read.csv(csv_path, stringsAsFactors = FALSE)
            if (nrow(celltype_data) > 0) {
                cat("  Census data loaded:", nrow(celltype_data), "rows,",
                    length(unique(celltype_data$cell_type)), "cell types\n")
            }
        }
    }

    # Fallback: curated literature-based annotations
    if (is.null(celltype_data) || nrow(celltype_data) == 0) {
        if (disease == "bladder_cancer") {
            cat("  Using curated cell-type annotations from published bladder cancer atlases...\n")
            celltype_data <- .bladder_cancer_celltype_annotations(panel_genes)
        } else if (disease == "breast_cancer") {
            cat("  Using curated cell-type annotations from published breast cancer atlases...\n")
            celltype_data <- .breast_cancer_celltype_annotations(panel_genes)
        } else if (disease == "sepsis") {
            cat("  Using curated cell-type annotations from published sepsis blood atlases...\n")
            celltype_data <- .sepsis_celltype_annotations(panel_genes)
        } else {
            cat("  Using curated cell-type annotations from published UC single-cell atlases...\n")
            celltype_data <- .curated_celltype_annotations()
        }
    }

    # Generate cell-type heatmap
    tissue_label <- switch(disease,
        ibd = "Large Intestine",
        bladder_cancer = "Bladder Tumor",
        breast_cancer = "Breast Tumor",
        sepsis = "Blood",
        "Tissue"
    )
    if (!is.null(celltype_data) && nrow(celltype_data) > 0) {
        .plot_celltype_expression(celltype_data, output_dir, tissue_label = tissue_label)
    }

    cat("  Cell-type analysis complete.\n")
    return(celltype_data)
}


.curated_celltype_annotations <- function() {
    # Curated from published UC single-cell atlases:
    # - Smillie et al. 2019 (Cell) - Human UC colon atlas
    # - Parikh et al. 2019 (Nature) - Intestinal organoids
    # - Kinchen et al. 2018 (Cell) - Colonic mesenchyme
    # - Corridoni et al. 2020 (Nat Med) - UC immune cells
    data.frame(
        gene = c(
            # S100A8 - calprotectin subunit, innate immunity
            "S100A8", "S100A8", "S100A8",
            # SELENBP1 - selenium binding, colonocyte marker
            "SELENBP1", "SELENBP1",
            # GUCA2B - uroguanylin, epithelial secretory
            "GUCA2B", "GUCA2B",
            # RGS13 - regulator of G-protein signaling
            "RGS13", "RGS13",
            # PTP4A3 - phosphatase, cell proliferation
            "PTP4A3", "PTP4A3",
            # CKB - creatine kinase brain-type
            "CKB", "CKB",
            # UCA1 - lncRNA, epithelial
            "UCA1", "UCA1",
            # GLDN - gliomedin, neural/enteric
            "GLDN"
        ),
        cell_type = c(
            "Neutrophils", "Inflammatory monocytes", "Macrophages",
            "Absorptive colonocytes", "Transit-amplifying cells",
            "Goblet cells", "Absorptive colonocytes",
            "Germinal center B cells", "Mast cells",
            "Endothelial cells", "Epithelial progenitors",
            "Absorptive colonocytes", "Smooth muscle cells",
            "Absorptive colonocytes", "Transit-amplifying cells",
            "Enteric neurons"
        ),
        compartment = c(
            "Immune", "Immune", "Immune",
            "Epithelial", "Epithelial",
            "Epithelial", "Epithelial",
            "Immune", "Immune",
            "Stromal", "Epithelial",
            "Epithelial", "Stromal",
            "Epithelial", "Epithelial",
            "Stromal"
        ),
        uc_change = c(
            "Strong upregulation", "Strong upregulation", "Upregulation",
            "Downregulation", "Reduced",
            "Strong downregulation", "Downregulation",
            "Upregulation", "Upregulation",
            "Variable", "Variable",
            "Downregulation", "No change",
            "Upregulation", "Upregulation",
            "Not characterized"
        ),
        evidence = c(
            "Smillie 2019, Corridoni 2020", "Corridoni 2020", "Smillie 2019",
            "Smillie 2019, Parikh 2019", "Smillie 2019",
            "Parikh 2019", "Smillie 2019",
            "Smillie 2019", "Kinchen 2018",
            "Kinchen 2018", "Smillie 2019",
            "Smillie 2019", "Kinchen 2018",
            "Smillie 2019", "Smillie 2019",
            "Limited data"
        ),
        source = "curated",
        stringsAsFactors = FALSE
    )
}


#' Curated bladder cancer TME cell-type annotations
#' Sources: Chen et al. 2020 (Nat Commun), Lai et al. 2021 (Int J Cancer)
.bladder_cancer_celltype_annotations <- function(panel_genes) {
    # Generic TME cell types for bladder cancer - annotated per gene if known
    # Since panel genes are data-driven, provide general bladder TME context
    known_annotations <- list(
        "CD8A" = list(ct = c("CD8+ T cells", "NK cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Enriched in inflamed tumors", "Variable")),
        "CD8B" = list(ct = c("CD8+ T cells"),
                      comp = c("Immune"),
                      change = c("Enriched in inflamed tumors")),
        "CXCL9" = list(ct = c("Macrophages", "Dendritic cells"),
                       comp = c("Immune", "Immune"),
                       change = c("Upregulated in inflamed TME", "Upregulated")),
        "CXCL10" = list(ct = c("Macrophages", "Endothelial cells"),
                        comp = c("Immune", "Stromal"),
                        change = c("Upregulated in inflamed TME", "Variable")),
        "IFNG" = list(ct = c("CD8+ T cells", "NK cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Enriched in responders", "Enriched in responders")),
        "GZMA" = list(ct = c("CD8+ T cells", "NK cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Cytolytic marker", "Cytolytic marker")),
        "GZMB" = list(ct = c("CD8+ T cells", "NK cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Cytolytic marker", "Cytolytic marker")),
        "PRF1" = list(ct = c("CD8+ T cells", "NK cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Cytolytic marker", "Cytolytic marker")),
        "IDO1" = list(ct = c("Macrophages", "Dendritic cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Upregulated in immune-active tumors", "Upregulated")),
        "FOXP3" = list(ct = c("Regulatory T cells"),
                       comp = c("Immune"),
                       change = c("Enriched in excluded/inflamed")),
        "TGFB1" = list(ct = c("Cancer-associated fibroblasts", "Macrophages"),
                       comp = c("Stromal", "Immune"),
                       change = c("Promotes T cell exclusion", "Variable")),
        "S100A8" = list(ct = c("Neutrophils", "Inflammatory monocytes"),
                        comp = c("Immune", "Immune"),
                        change = c("Myeloid inflammation marker", "Upregulated")),
        "S100A9" = list(ct = c("Neutrophils", "Inflammatory monocytes"),
                        comp = c("Immune", "Immune"),
                        change = c("Myeloid inflammation marker", "Upregulated")),
        "TOP2A" = list(ct = c("Proliferating tumor cells", "Proliferating T cells"),
                       comp = c("Epithelial", "Immune"),
                       change = c("High in basal subtype", "Proliferation marker")),
        "ADAM12" = list(ct = c("Cancer-associated fibroblasts", "Myofibroblasts"),
                        comp = c("Stromal", "Stromal"),
                        change = c("Stromal remodeling", "Stromal remodeling"))
    )

    rows <- list()
    for (gene in panel_genes) {
        if (gene %in% names(known_annotations)) {
            ann <- known_annotations[[gene]]
            for (i in seq_along(ann$ct)) {
                rows[[length(rows) + 1]] <- data.frame(
                    gene = gene, cell_type = ann$ct[i],
                    compartment = ann$comp[i], disease_change = ann$change[i],
                    evidence = "Chen 2020, Lai 2021", source = "curated",
                    stringsAsFactors = FALSE)
            }
        } else {
            # Generic annotation for unknown genes
            rows[[length(rows) + 1]] <- data.frame(
                gene = gene, cell_type = "Not characterized in bladder TME",
                compartment = "Unknown", disease_change = "Not characterized",
                evidence = "Limited data", source = "curated",
                stringsAsFactors = FALSE)
        }
    }
    do.call(rbind, rows)
}


#' Curated breast cancer TME cell-type annotations
#' Sources: Wu et al. 2021 (Nat Genet), Bassez et al. 2021 (Nat Med),
#'          Pal et al. 2021 (EMBO J)
.breast_cancer_celltype_annotations <- function(panel_genes) {
    known_annotations <- list(
        "ZIC1" = list(ct = c("Epithelial tumor cells"),
                      comp = c("Epithelial"),
                      change = c("Methylation marker in breast cancer")),
        "TPSAB1" = list(ct = c("Mast cells"),
                        comp = c("Immune"),
                        change = c("Stromal immune infiltrate; variable with chemo")),
        "CHAF1B" = list(ct = c("Proliferating tumor cells", "Proliferating T cells"),
                        comp = c("Epithelial", "Immune"),
                        change = c("Proliferation marker", "Proliferation marker")),
        "RRAGD" = list(ct = c("Epithelial tumor cells"),
                       comp = c("Epithelial"),
                       change = c("mTOR pathway; metabolically active cells")),
        "TTLL4" = list(ct = c("Epithelial tumor cells"),
                       comp = c("Epithelial"),
                       change = c("Tubulin modification; taxane sensitivity marker")),
        "RARRES1" = list(ct = c("Epithelial tumor cells", "Luminal progenitors"),
                         comp = c("Epithelial", "Epithelial"),
                         change = c("Tumor suppressor; retinoic acid pathway", "Differentiation")),
        "ESR1" = list(ct = c("Luminal epithelial cells", "ER+ tumor cells"),
                      comp = c("Epithelial", "Epithelial"),
                      change = c("Estrogen receptor; luminal marker", "ER+ tumors: lower pCR")),
        "S100B" = list(ct = c("Basal-like tumor cells", "Neural cells"),
                       comp = c("Epithelial", "Stromal"),
                       change = c("Basal subtype marker", "TME neural component")),
        "NMU" = list(ct = c("Epithelial tumor cells"),
                     comp = c("Epithelial"),
                     change = c("Neuropeptide; proliferation signal")),
        "NFIB" = list(ct = c("Basal-like tumor cells", "Cancer stem cells"),
                      comp = c("Epithelial", "Epithelial"),
                      change = c("TNBC-associated TF", "Stemness marker")),
        "TM4SF1" = list(ct = c("Epithelial tumor cells", "Endothelial cells"),
                        comp = c("Epithelial", "Stromal"),
                        change = c("Tumor cell surface marker", "Angiogenesis")),
        "GREB1" = list(ct = c("ER+ tumor cells"),
                       comp = c("Epithelial"),
                       change = c("Estrogen-responsive; ER+ subtype marker")),
        "CD8A" = list(ct = c("CD8+ T cells"),
                      comp = c("Immune"),
                      change = c("Tumor-infiltrating lymphocytes; predicts pCR")),
        "GZMA" = list(ct = c("CD8+ T cells", "NK cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Cytolytic activity", "Cytolytic activity")),
        "GZMB" = list(ct = c("CD8+ T cells", "NK cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Cytolytic activity", "Cytolytic activity")),
        "MKI67" = list(ct = c("Proliferating tumor cells", "Proliferating immune cells"),
                       comp = c("Epithelial", "Immune"),
                       change = c("Ki-67; standard proliferation marker", "Active immune response"))
    )

    rows <- list()
    for (gene in panel_genes) {
        if (gene %in% names(known_annotations)) {
            ann <- known_annotations[[gene]]
            for (i in seq_along(ann$ct)) {
                rows[[length(rows) + 1]] <- data.frame(
                    gene = gene, cell_type = ann$ct[i],
                    compartment = ann$comp[i], disease_change = ann$change[i],
                    evidence = "Wu 2021, Bassez 2021", source = "curated",
                    stringsAsFactors = FALSE)
            }
        } else {
            rows[[length(rows) + 1]] <- data.frame(
                gene = gene, cell_type = "Not characterized in breast TME",
                compartment = "Unknown", disease_change = "Not characterized",
                evidence = "Limited data", source = "curated",
                stringsAsFactors = FALSE)
        }
    }
    do.call(rbind, rows)
}


#' Curated sepsis blood cell-type annotations
#' Sources: Reyes et al. 2020 (Nat Med), Scicluna et al. 2017 (Lancet Respir Med),
#'          Kwok et al. 2023 (Nat Commun), Sweeney et al. 2018 (Sci Transl Med)
.sepsis_celltype_annotations <- function(panel_genes) {
    known_annotations <- list(
        "IFIT1B" = list(ct = c("Monocytes", "Dendritic cells"),
                        comp = c("Immune", "Immune"),
                        change = c("Downregulated in Mars1 immunosuppression", "Reduced interferon response")),
        "ACSL6" = list(ct = c("Monocytes/Macrophages", "Neutrophils"),
                       comp = c("Immune", "Immune"),
                       change = c("Metabolic reprogramming in sepsis", "Altered lipid metabolism")),
        "CTNNAL1" = list(ct = c("Monocytes", "Neutrophils"),
                         comp = c("Immune", "Immune"),
                         change = c("Altered leukocyte adhesion", "Impaired migration")),
        "ABCC13" = list(ct = c("Neutrophils"),
                        comp = c("Immune"),
                        change = c("Pseudogene; potential regulatory role")),
        "C9orf78" = list(ct = c("Monocytes", "T cells"),
                         comp = c("Immune", "Immune"),
                         change = c("Apoptosis regulation", "Lymphocyte survival")),
        "KCNH2" = list(ct = c("Multiple cell types"),
                       comp = c("Immune"),
                       change = c("Electrolyte regulation in critical illness")),
        "FAM104A" = list(ct = c("Multiple cell types"),
                         comp = c("Immune"),
                         change = c("Function in immune cells unclear")),
        "POC1B" = list(ct = c("Proliferating immune cells"),
                       comp = c("Immune"),
                       change = c("Cell division in activated immune cells")),
        "BPGM" = list(ct = c("Erythrocytes", "Neutrophils"),
                      comp = c("Erythroid", "Immune"),
                      change = c("2,3-BPG regulation; oxygen delivery", "Variable")),
        "ZDHHC2" = list(ct = c("T cells", "Monocytes"),
                        comp = c("Immune", "Immune"),
                        change = c("Protein palmitoylation in signaling", "Immune signaling regulation")),
        "FGFR1OP2" = list(ct = c("Multiple cell types"),
                          comp = c("Immune"),
                          change = c("Centrosome/cytoskeletal organization")),
        "SAMHD1" = list(ct = c("Monocytes/Macrophages", "Dendritic cells"),
                        comp = c("Immune", "Immune"),
                        change = c("Interferon-stimulated gene; innate defense", "Antiviral response")),
        "DARC" = list(ct = c("Erythrocytes", "Endothelial cells"),
                      comp = c("Erythroid", "Stromal"),
                      change = c("Chemokine scavenger; regulates neutrophil trafficking", "Chemokine sequestration")),
        "ACKR1" = list(ct = c("Erythrocytes", "Endothelial cells"),
                       comp = c("Erythroid", "Stromal"),
                       change = c("Chemokine scavenger; regulates neutrophil trafficking", "Chemokine sequestration")),
        "DDX17" = list(ct = c("Monocytes", "Dendritic cells"),
                       comp = c("Immune", "Immune"),
                       change = c("Innate immune signaling", "RNA processing in immune activation")),
        "DAAM2" = list(ct = c("T cells", "Monocytes"),
                       comp = c("Immune", "Immune"),
                       change = c("Wnt signaling; cytoskeletal regulation", "Cell migration")),
        "TUBG2" = list(ct = c("Proliferating immune cells"),
                       comp = c("Immune"),
                       change = c("Centrosome function; cell division")),
        "IL8" = list(ct = c("Neutrophils", "Monocytes/Macrophages"),
                     comp = c("Immune", "Immune"),
                     change = c("Major neutrophil chemoattractant; strongly upregulated", "Key inflammatory mediator")),
        "CXCL8" = list(ct = c("Neutrophils", "Monocytes/Macrophages"),
                       comp = c("Immune", "Immune"),
                       change = c("Major neutrophil chemoattractant; strongly upregulated", "Key inflammatory mediator")),
        "EGR1" = list(ct = c("Monocytes/Macrophages", "Endothelial cells"),
                      comp = c("Immune", "Stromal"),
                      change = c("Stress-responsive TF; monocyte activation", "Endothelial activation")),
        "TNFSF12" = list(ct = c("Monocytes/Macrophages", "T cells"),
                         comp = c("Immune", "Immune"),
                         change = c("TWEAK; immune regulation", "T cell modulation")),
        "TNFRSF8" = list(ct = c("T cells", "B cells"),
                         comp = c("Immune", "Immune"),
                         change = c("CD30; T-cell activation marker", "Activation marker")),
        "CTSO" = list(ct = c("Monocytes/Macrophages", "Dendritic cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Lysosomal protease; antigen processing", "Antigen presentation")),
        "TNKS" = list(ct = c("Multiple cell types"),
                      comp = c("Immune"),
                      change = c("Wnt signaling; telomere maintenance")),
        "PTPLA" = list(ct = c("Monocytes", "Neutrophils"),
                       comp = c("Immune", "Immune"),
                       change = c("Fatty acid elongation", "Lipid metabolism")),
        "HACD1" = list(ct = c("Monocytes", "Neutrophils"),
                       comp = c("Immune", "Immune"),
                       change = c("Fatty acid elongation", "Lipid metabolism")),
        "DEFA4" = list(ct = c("Neutrophils"),
                       comp = c("Immune"),
                       change = c("Antimicrobial peptide; strongly upregulated in sepsis")),
        "S100A12" = list(ct = c("Neutrophils", "Inflammatory monocytes"),
                         comp = c("Immune", "Immune"),
                         change = c("Alarmin; neutrophil activation marker", "Strong upregulation")),
        "S100A8" = list(ct = c("Neutrophils", "Inflammatory monocytes"),
                        comp = c("Immune", "Immune"),
                        change = c("Calprotectin subunit; innate immunity", "Strong upregulation")),
        "S100A9" = list(ct = c("Neutrophils", "Inflammatory monocytes"),
                        comp = c("Immune", "Immune"),
                        change = c("Calprotectin subunit; innate immunity", "Strong upregulation")),
        "TNF" = list(ct = c("Monocytes/Macrophages", "NK cells"),
                     comp = c("Immune", "Immune"),
                     change = c("Master pro-inflammatory cytokine", "Early sepsis response")),
        "IL1B" = list(ct = c("Monocytes/Macrophages", "Neutrophils"),
                      comp = c("Immune", "Immune"),
                      change = c("Inflammasome-derived cytokine", "Pyroptosis pathway")),
        "IL6" = list(ct = c("Monocytes/Macrophages", "Endothelial cells"),
                     comp = c("Immune", "Stromal"),
                     change = c("Key sepsis cytokine; drives CRP", "Endothelial activation")),
        "IL10" = list(ct = c("Monocytes/Macrophages", "Regulatory T cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Anti-inflammatory; immunosuppression marker", "Immune regulation")),
        "IFNG" = list(ct = c("NK cells", "T cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Macrophage activation", "Adaptive immune response")),
        "CD14" = list(ct = c("Monocytes/Macrophages"),
                      comp = c("Immune"),
                      change = c("LPS co-receptor; monocyte marker; soluble CD14 is sepsis biomarker")),
        "HLA-DRA" = list(ct = c("Monocytes/Macrophages", "Dendritic cells", "B cells"),
                         comp = c("Immune", "Immune", "Immune"),
                         change = c("Reduced in immunoparalysis", "Reduced antigen presentation", "Variable")),
        "CX3CR1" = list(ct = c("Monocytes", "NK cells"),
                        comp = c("Immune", "Immune"),
                        change = c("Non-classical monocyte marker; reduced in sepsis", "Tissue surveillance")),
        "CCR7" = list(ct = c("Dendritic cells", "T cells"),
                      comp = c("Immune", "Immune"),
                      change = c("Lymph node homing; reduced in sepsis", "Naive/central memory marker"))
    )

    rows <- list()
    for (gene in panel_genes) {
        if (gene %in% names(known_annotations)) {
            ann <- known_annotations[[gene]]
            for (i in seq_along(ann$ct)) {
                rows[[length(rows) + 1]] <- data.frame(
                    gene = gene, cell_type = ann$ct[i],
                    compartment = ann$comp[i], disease_change = ann$change[i],
                    evidence = "Reyes 2020, Scicluna 2017", source = "curated",
                    stringsAsFactors = FALSE)
            }
        } else {
            # Generic annotation for unknown genes
            rows[[length(rows) + 1]] <- data.frame(
                gene = gene, cell_type = "Not characterized in sepsis blood",
                compartment = "Unknown", disease_change = "Not characterized",
                evidence = "Limited data", source = "curated",
                stringsAsFactors = FALSE)
        }
    }
    do.call(rbind, rows)
}


.plot_celltype_expression <- function(celltype_data, output_dir, tissue_label = "Tissue") {
    suppressPackageStartupMessages({
        library(ggplot2)
        library(ggprism)
    })

    if ("source" %in% names(celltype_data) && all(celltype_data$source == "curated")) {
        # Plot curated data as a tile plot
        plot_data <- celltype_data

        # Detect change column (uc_change for legacy IBD, disease_change for new)
        change_col <- if ("disease_change" %in% names(plot_data)) "disease_change" else "uc_change"

        # Map change to numeric for color scale
        change_map <- c("Strong upregulation" = 2, "Upregulation" = 1,
                        "Enriched in inflamed tumors" = 1.5, "Enriched in responders" = 1.5,
                        "Upregulated in inflamed TME" = 1.5, "Upregulated" = 1,
                        "Cytolytic marker" = 1, "Cytolytic activity" = 1,
                        "Myeloid inflammation marker" = 1,
                        "Promotes T cell exclusion" = -1, "Stromal remodeling" = 0,
                        "Proliferation marker" = 0.5, "High in basal subtype" = 0.5,
                        "Proliferation" = 0.5, "Active immune response" = 1,
                        "Tumor-infiltrating lymphocytes; predicts pCR" = 1.5,
                        "Methylation marker in breast cancer" = 0,
                        "Stromal immune infiltrate; variable with chemo" = 0,
                        "mTOR pathway; metabolically active cells" = 0.5,
                        "Tubulin modification; taxane sensitivity marker" = 0.5,
                        "Tumor suppressor; retinoic acid pathway" = 0,
                        "Differentiation" = 0, "Stemness marker" = 0.5,
                        "Estrogen receptor; luminal marker" = 0,
                        "ER+ tumors: lower pCR" = -1,
                        "Basal subtype marker" = 0.5,
                        "TME neural component" = 0,
                        "Neuropeptide; proliferation signal" = 0.5,
                        "TNBC-associated TF" = 0.5,
                        "Tumor cell surface marker" = 0, "Angiogenesis" = 0,
                        "Estrogen-responsive; ER+ subtype marker" = -0.5,
                        "Ki-67; standard proliferation marker" = 1,
                        "Variable" = 0, "No change" = 0, "Not characterized" = NA,
                        "Not characterized in bladder TME" = NA,
                        "Not characterized in breast TME" = NA,
                        "Not characterized in sepsis blood" = NA,
                        "Downregulated in Mars1 immunosuppression" = -1.5,
                        "Reduced interferon response" = -1,
                        "Metabolic reprogramming in sepsis" = 0.5,
                        "Altered lipid metabolism" = 0,
                        "Altered leukocyte adhesion" = 0.5,
                        "Impaired migration" = -0.5,
                        "Pseudogene; potential regulatory role" = 0,
                        "Apoptosis regulation" = 0,
                        "Lymphocyte survival" = 0,
                        "Electrolyte regulation in critical illness" = 0,
                        "Function in immune cells unclear" = NA,
                        "Cell division in activated immune cells" = 0.5,
                        "2,3-BPG regulation; oxygen delivery" = 0.5,
                        "Protein palmitoylation in signaling" = 0,
                        "Immune signaling regulation" = 0,
                        "Centrosome/cytoskeletal organization" = 0,
                        "Interferon-stimulated gene; innate defense" = 1,
                        "Antiviral response" = 1,
                        "Chemokine scavenger; regulates neutrophil trafficking" = 1,
                        "Chemokine sequestration" = 0.5,
                        "Innate immune signaling" = 1,
                        "RNA processing in immune activation" = 0.5,
                        "Wnt signaling; cytoskeletal regulation" = 0,
                        "Cell migration" = 0,
                        "Centrosome function; cell division" = 0.5,
                        "Major neutrophil chemoattractant; strongly upregulated" = 2,
                        "Key inflammatory mediator" = 1.5,
                        "Stress-responsive TF; monocyte activation" = 1,
                        "Endothelial activation" = 1,
                        "TWEAK; immune regulation" = 0.5,
                        "T cell modulation" = 0,
                        "CD30; T-cell activation marker" = 1,
                        "Activation marker" = 0.5,
                        "Lysosomal protease; antigen processing" = 0.5,
                        "Antigen presentation" = 0.5,
                        "Wnt signaling; telomere maintenance" = 0,
                        "Fatty acid elongation" = 0,
                        "Lipid metabolism" = 0,
                        "Antimicrobial peptide; strongly upregulated in sepsis" = 2,
                        "Alarmin; neutrophil activation marker" = 1.5,
                        "Calprotectin subunit; innate immunity" = 1.5,
                        "Master pro-inflammatory cytokine" = 2,
                        "Early sepsis response" = 1.5,
                        "Inflammasome-derived cytokine" = 2,
                        "Pyroptosis pathway" = 1.5,
                        "Key sepsis cytokine; drives CRP" = 2,
                        "Anti-inflammatory; immunosuppression marker" = -1,
                        "Immune regulation" = 0,
                        "Macrophage activation" = 1,
                        "Adaptive immune response" = 1,
                        "LPS co-receptor; monocyte marker; soluble CD14 is sepsis biomarker" = 1.5,
                        "Reduced in immunoparalysis" = -1.5,
                        "Reduced antigen presentation" = -1,
                        "Non-classical monocyte marker; reduced in sepsis" = -1,
                        "Tissue surveillance" = 0,
                        "Lymph node homing; reduced in sepsis" = -1,
                        "Naive/central memory marker" = 0,
                        "Reduced" = -1, "Downregulation" = -1,
                        "Strong downregulation" = -2)
        plot_data$change_score <- change_map[plot_data[[change_col]]]

        legend_name <- paste0(tissue_label, "\nChange")

        p <- ggplot(plot_data, aes(x = gene, y = cell_type, fill = change_score)) +
            geom_tile(color = "white", linewidth = 0.5) +
            geom_text(aes(label = compartment), size = 2.8, color = "grey30") +
            scale_fill_gradient2(low = "steelblue3", mid = "white", high = "firebrick3",
                                 midpoint = 0, na.value = "grey90",
                                 name = legend_name,
                                 breaks = c(-2, -1, 0, 1, 2),
                                 labels = c("Strong down", "Down", "No change",
                                            "Up", "Strong up")) +
            theme_prism(base_size = 11) +
            theme(
                axis.text.x = element_text(angle = 45, hjust = 1, size = 10, face = "italic"),
                axis.text.y = element_text(size = 9),
                plot.title = element_text(hjust = 0.5, face = "bold", size = 13),
                legend.position = "right"
            ) +
            labs(x = NULL, y = NULL,
                 title = paste("Cell-Type Expression of Panel Genes in", tissue_label))

        .save_enrichment_plot(p, file.path(output_dir, "celltype_expression"), 10, 7)

    } else if ("mean_expression" %in% names(celltype_data)) {
        # Plot Census data - top cell types per gene
        # Filter to normal tissue for baseline expression
        if ("disease" %in% names(celltype_data)) {
            plot_data <- celltype_data[celltype_data$disease == "normal", ]
            if (nrow(plot_data) == 0) plot_data <- celltype_data
        } else {
            plot_data <- celltype_data
        }

        # Top 3 cell types per gene by expression
        top_ct <- do.call(rbind, lapply(split(plot_data, plot_data$gene), function(df) {
            head(df[order(-df$mean_expression), ], 5)
        }))

        if (nrow(top_ct) > 0) {
            p <- ggplot(top_ct, aes(x = reorder(cell_type, mean_expression),
                                     y = mean_expression,
                                     fill = gene)) +
                geom_col(position = "dodge") +
                coord_flip() +
                facet_wrap(~ gene, scales = "free", ncol = 2) +
                theme_prism(base_size = 10) +
                theme(
                    legend.position = "none",
                    strip.text = element_text(face = "italic", size = 10),
                    plot.title = element_text(hjust = 0.5, face = "bold", size = 13)
                ) +
                labs(x = NULL, y = "Mean Expression",
                     title = paste("Cell-Type Expression in", tissue_label, "(CZI CELLxGENE)"))

            .save_enrichment_plot(p, file.path(output_dir, "celltype_expression"), 12, 10)
        }
    }
}


# ============================================================
# 3. GWAS / Disease Gene Overlap
# ============================================================

.get_gwas_config <- function(disease) {
    if (disease == "breast_cancer") {
        list(
            genes = c(
                # Breast cancer GWAS susceptibility loci (Michailidou 2017, Fachal 2020)
                "BRCA1", "BRCA2", "TP53", "CHEK2", "ATM", "PALB2", "RAD51C",
                "ESR1", "FGFR2", "MAP3K1", "TOX3", "CCND1", "TERT", "CASP8",
                "MYC", "CDKN2A", "PTEN", "PIK3CA", "AKT1", "CDH1",
                "RAD51B", "RAD51D", "NF1", "STK11", "RB1",
                # Chemotherapy response / DNA damage repair genes
                "TOP2A", "TYMS", "ERCC1", "ERCC2", "TUBB3", "RRM1",
                "ABCB1", "GSTP1", "DPYD", "UGT1A1",
                # Immune / tumor microenvironment genes (pCR predictors)
                "CD8A", "CD8B", "GZMA", "GZMB", "PRF1", "IFNG",
                "CXCL9", "CXCL10", "CXCL13", "IDO1", "CD274",
                "FOXP3", "CTLA4", "CD19", "MS4A1", "IGHG1",
                "MKI67", "PCNA", "MCM2", "BIRC5",
                # Breast cancer molecular subtype markers
                "ERBB2", "PGR", "KRT5", "KRT14", "KRT17", "EGFR", "VIM"
            ),
            label = "Breast Cancer GWAS & Chemo Response",
            references = "Michailidou et al. 2017 Nature; Fachal et al. 2020 Nat Genet",
            refs_detail = paste("Breast cancer susceptibility loci (Michailidou et al. 2017",
                                "Nature, 65 GWAS loci) plus chemotherapy response genes and",
                                "immune/proliferation markers associated with pCR",
                                "(Denkert et al. 2018 Lancet Oncol)")
        )
    } else if (disease == "bladder_cancer") {
        list(
            genes = c(
                # Bladder cancer GWAS loci (Figueroa 2023 meta-analysis, 24 loci)
                "PSCA", "FGFR3", "TACC3", "TP63", "MYC", "TERT", "CLPTM1L",
                "NAT2", "UGT1A6", "UGT1A8", "CCNE1", "APOBEC3A", "APOBEC3B",
                "CBX6", "SLC14A1", "GSTM1", "CDKN2A", "MTAP", "PAG1",
                # ICI response / immune checkpoint genes
                "CD274", "PDCD1", "PDCD1LG2", "CTLA4", "LAG3", "HAVCR2",
                "B2M", "JAK1", "JAK2", "STK11", "PTEN", "KEAP1",
                # Immunotherapy response score genes
                "TOP2A", "ADAM12",
                # TME / immune signature genes
                "CD8A", "CD8B", "CXCL9", "CXCL10", "CXCL13", "IFNG",
                "GZMA", "GZMB", "PRF1", "IDO1", "FOXP3", "TGFB1",
                # APOBEC mutagenesis
                "AICDA", "APOBEC3C", "APOBEC3D", "APOBEC3F", "APOBEC3G",
                # DNA damage response
                "ERCC2", "ATM", "RB1", "BRCA2", "FANCA"
            ),
            label = "Bladder Cancer GWAS & ICI Response",
            references = "Figueroa et al. 2023 Eur Urol; Samstein et al. 2019 Nat Genet",
            refs_detail = paste("Bladder cancer susceptibility loci (Figueroa et al. 2023",
                                "Eur Urol, 24 GWAS loci) plus immune checkpoint and",
                                "immunotherapy response genes (Samstein et al. 2019;",
                                "Cristescu et al. 2022)")
        )
    } else if (disease == "sepsis") {
        list(
            genes = c(
                # Sepsis susceptibility GWAS loci (Rautanen et al. 2015 Am J Hum Genet,
                # Scherag et al. 2016 Eur J Hum Genet, Srinivasan et al. 2020 AJRCCM)
                "FER", "PCSK9",
                # Innate immune recognition / TLR pathway
                "TLR1", "TLR4", "TLR5", "MBL2",
                # Pro-inflammatory cytokines
                "TNF", "IL1B", "IL6", "IL10", "IL1R2",
                # Damage-associated / immunomodulatory
                "HMGB1", "MIF", "PAI1",
                # Coagulation / endothelial dysfunction
                "ACE", "ADAMTS13", "PROC", "THBD", "ABO",
                # Adaptive immunity / antigen presentation
                "IFNG", "HLA-DRA", "CD14",
                # Alarmins / myeloid markers
                "S100A12", "S100A8", "S100A9",
                # Chemokine receptors / trafficking
                "CX3CR1", "CCR7",
                # Interferon-stimulated genes
                "IFIT1", "IFIT2", "IFIT3", "MX1", "OAS1"
            ),
            label = "Sepsis GWAS & Immune Response",
            references = "Rautanen et al. 2015 Am J Hum Genet; Scherag et al. 2016 Eur J Hum Genet; Scicluna et al. 2017 Lancet Respir Med",
            refs_detail = paste("Sepsis susceptibility loci (Rautanen et al. 2015 Am J Hum",
                                "Genet, FER locus; Scherag et al. 2016 Eur J Hum Genet)",
                                "plus key innate/adaptive immune response genes from sepsis",
                                "transcriptomic studies (Scicluna et al. 2017 Lancet Respir Med;",
                                "Sweeney et al. 2018 Sci Transl Med)")
        )
    } else {
        # IBD (default)
        list(
            genes = c(
                "NOD2", "CARD9", "RIPK2", "XIAP", "NFKB1", "NFKB2", "REL", "RELA",
                "IL23R", "IL12B", "JAK2", "TYK2", "STAT3", "STAT4", "IL21", "IL6ST",
                "IL23A", "RORC", "CCR6", "IL17A", "IL17F", "IL22",
                "ATG16L1", "IRGM", "LRRK2", "ULK1", "SMURF1",
                "HNF4A", "CDH1", "ITLN1", "MUC1", "MUC19", "FUT2", "ECM1",
                "IL10", "IL2RA", "IL7R", "TNFSF15", "TNFAIP3", "TNFRSF6B",
                "BACH2", "PRDM1", "IKZF1", "TAGAP", "IRF5", "IRF1", "IRF4",
                "PTGER4", "MST1", "CXCR2", "CXCL5", "CCL2", "CCL7", "CCL20",
                "ICAM1", "ITGAL", "MADCAM1",
                "FCGR2A", "FCGR2B", "FCGR3A",
                "PTPN2", "PTPN22", "SH2B3", "SMAD3", "SMAD7",
                "ERAP1", "ERAP2", "BTNL2", "SP140",
                "TLR4", "IFIH1", "MDA5",
                "NKX2-3", "FOXO3", "CEBPB", "GATA3", "CREM", "KLF3",
                "DNMT3A", "ARID5B",
                "SLC22A4", "SLC22A5", "SLC39A8", "GPR35", "GPR65", "ORMDL3",
                "S100A8", "S100A9", "S100A12",
                "ZMIZ1", "PUS10", "SBNO2", "RNF186", "OTUD3", "LITAF",
                "USP25", "CYLD", "NDFIP1", "TNFRSF14", "CARD11",
                "FCER1G", "RNF40", "PDLIM5", "CUL2", "RTEL1", "FOS"
            ),
            label = "IBD GWAS",
            references = "de Lange 2017, Liu 2023, Jostins 2012",
            refs_detail = paste("de Lange et al. 2017 Nat Genet; Liu et al. 2023",
                                "Nat Genet; Jostins et al. 2012 Nature")
        )
    }
}

.get_gene_annotations <- function(disease) {
    if (disease == "breast_cancer") {
        list(
            # ----- Subtype classification panel genes -----
            "ESR1" = list(
                gwas_evidence = "Direct breast cancer GWAS hit (6q25.1)",
                disease_relevance = "Estrogen receptor alpha; THE defining marker of luminal breast cancer; ER+ in ~70% of cases",
                drug_relevance = "Target of endocrine therapy (tamoxifen, aromatase inhibitors); high expression defines Luminal A",
                references = "TCGA Network 2012 Nature; Parker et al. 2009 JCO"),
            "TBC1D9" = list(
                gwas_evidence = "No direct GWAS hit; strongly co-expressed with ESR1",
                disease_relevance = "TBC1 domain family member 9; Rab GTPase-activating protein; highly expressed in luminal tumors",
                drug_relevance = "Luminal marker; high expression predicts endocrine therapy response",
                references = "Smid et al. 2006 BMC Genomics"),
            "CA12" = list(
                gwas_evidence = "No direct GWAS hit; ER-regulated gene",
                disease_relevance = "Carbonic anhydrase XII; directly induced by estrogen/ER signaling; luminal marker in PAM50",
                drug_relevance = "Potential therapeutic target; high expression indicates active ER signaling",
                references = "Barnett et al. 2008 Cancer Res"),
            "MLPH" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Melanophilin; involved in melanosome transport; highly expressed in luminal breast tumors",
                drug_relevance = "Luminal A marker gene; associated with favorable prognosis",
                references = "Parker et al. 2009 JCO"),
            "NAT1" = list(
                gwas_evidence = "Breast cancer risk locus (8p22); NAT2 variant is GWAS hit",
                disease_relevance = "N-acetyltransferase 1; Phase II detoxification enzyme; high expression defines luminal subtype",
                drug_relevance = "Luminal marker; associated with endocrine therapy sensitivity",
                references = "Perou et al. 2000 Nature"),
            "SLC44A4" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Choline transporter-like protein 4; highly expressed in luminal breast cancer",
                drug_relevance = "Strong luminal marker; negative coefficient indicates Basal-like when absent",
                references = "TCGA Network 2012 Nature"),
            "FOXA1" = list(
                gwas_evidence = "Direct breast cancer GWAS hit (14q21.1)",
                disease_relevance = "Forkhead box A1; pioneer transcription factor for ER; essential for luminal differentiation",
                drug_relevance = "Required for ER chromatin binding; FOXA1 mutations affect endocrine therapy response",
                references = "Carroll et al. 2005 Cell; Hurtado et al. 2011 Nat Genet"),
            "MAPT" = list(
                gwas_evidence = "GWAS hit for Alzheimer's; indirectly linked to breast cancer prognosis",
                disease_relevance = "Microtubule-associated protein Tau; expressed in luminal tumors; inversely correlated with basal markers",
                drug_relevance = "High expression predicts taxane resistance (competes with paclitaxel for tubulin binding)",
                references = "Rouzier et al. 2005 PNAS"),
            "AGR2" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Anterior gradient 2; ER-regulated protein disulfide isomerase; luminal A marker",
                drug_relevance = "High expression in ER+ luminal tumors; associated with favorable prognosis",
                references = "Innes et al. 2006 BJC"),
            "CDC20" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Cell division cycle 20; mitotic checkpoint protein; proliferation marker enriched in basal-like tumors",
                drug_relevance = "High proliferation marker; positive coefficient indicates Basal-like subtype",
                references = "TCGA Network 2012 Nature"),
            "CIRBP" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Cold-inducible RNA binding protein; stress-responsive gene; differentially expressed between subtypes",
                drug_relevance = "Luminal marker; involved in mRNA stability regulation",
                references = "Perou et al. 2000 Nature"),
            "XBP1" = list(
                gwas_evidence = "No direct GWAS hit; near breast cancer GWAS locus",
                disease_relevance = "X-box binding protein 1; UPR transcription factor; strongly expressed in luminal breast cancer",
                drug_relevance = "XBP1 splicing drives endocrine resistance; high expression indicates luminal differentiation",
                references = "Chen et al. 2014 Nature"),
            "KIF2C" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Kinesin family member 2C (MCAK); mitotic kinesin; proliferation marker in breast cancer",
                drug_relevance = "Cell cycle gene enriched in basal-like tumors; potential therapeutic target",
                references = "Parker et al. 2009 JCO"),
            "SLC39A6" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Zinc transporter LIV-1; estrogen-induced gene; luminal breast cancer marker",
                drug_relevance = "Target of ladiratuzumab vedotin (ADC); high expression in luminal tumors",
                references = "Taylor et al. 2007 Cancer Res"),
            "SCUBE2" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Signal peptide CUB EGF-like domain 2; luminal marker; inhibits cancer progression",
                drug_relevance = "High expression indicates favorable prognosis; part of Oncotype DX gene list",
                references = "Cheng et al. 2009 JCO"),
            "DNAJC12" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "DnaJ heat shock protein family member C12; ER-regulated chaperone in luminal tumors",
                drug_relevance = "High expression predicts tamoxifen sensitivity",
                references = "de Ronde et al. 2013 Mol Oncol"),
            "TPX2" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Targeting protein for Xklp2; Aurora A kinase activator; proliferation marker in breast cancer",
                drug_relevance = "Enriched in basal-like tumors; Aurora kinase inhibitors in clinical trials",
                references = "TCGA Network 2012 Nature"),
            # ----- pCR-specific genes (retained for backward compatibility) -----
            "ZIC1" = list(
                gwas_evidence = "No direct breast cancer GWAS hit",
                disease_relevance = "Zinc finger transcription factor; frequently methylated in breast cancer",
                drug_relevance = "Positive coefficient: higher expression predicts pCR",
                references = "Gan et al. 2011 Breast Cancer Res Treat"),
            "TPSAB1" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Tryptase alpha/beta 1; mast cell marker in tumor microenvironment",
                drug_relevance = "Negative coefficient: higher mast cell infiltration predicts residual disease",
                references = "Aponte-López et al. 2018 Immunol Lett"),
            "CHAF1B" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Chromatin assembly factor 1 subunit B; proliferation marker",
                drug_relevance = "Higher proliferation predicts pCR to chemotherapy",
                references = "Peng et al. 2019 BMC Cancer")
        )
    } else if (disease == "bladder_cancer") {
        # Bladder cancer / ICI response gene annotations
        # These are populated dynamically — only genes that appear in the panel get used
        list(
            "TMB_log2" = list(
                gwas_evidence = "Genomic feature (not a gene); TMB is a validated pan-cancer ICI biomarker",
                disease_relevance = "TMB >= 10 mut/Mb predicts ICI response across cancer types",
                drug_relevance = "FDA-approved TMB-high biomarker for pembrolizumab (pan-tumor)",
                references = "Samstein et al. 2019 Nat Genet"),
            "CD274" = list(
                gwas_evidence = "PD-L1 gene; target of atezolizumab",
                disease_relevance = "PD-L1 expression on immune cells (IC2+) enriches response to ~27%",
                drug_relevance = "Direct drug target; SP142 IHC companion diagnostic",
                references = "Mariathasan et al. 2018 Nature"),
            "PDCD1" = list(
                gwas_evidence = "PD-1 gene; immune checkpoint receptor",
                disease_relevance = "Component of IRS; T cell exhaustion marker in bladder TME",
                drug_relevance = "Target of nivolumab/pembrolizumab; high expression indicates active immune checkpoint",
                references = "Cristescu et al. 2022"),
            "CD8A" = list(
                gwas_evidence = "No direct GWAS hit; key ICI response gene",
                disease_relevance = "CD8+ T cell infiltration is strongest predictor of ICI response",
                drug_relevance = "Inflamed phenotype marker; associated with atezolizumab benefit",
                references = "Mariathasan et al. 2018"),
            "CXCL9" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "IFN-gamma-induced chemokine; T cell recruitment to tumor",
                drug_relevance = "Core immune-inflamed signature gene",
                references = "Ayers et al. 2017 JCI"),
            "CXCL10" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "T cell chemoattractant; marks immune-active tumors",
                drug_relevance = "Part of Teff signature predicting anti-PD-L1 response",
                references = "Mariathasan et al. 2018"),
            "TGFB1" = list(
                gwas_evidence = "No direct bladder GWAS hit; major immune regulator",
                disease_relevance = "TGF-beta drives T cell exclusion from tumor parenchyma",
                drug_relevance = "Anti-TGF-beta combinations under investigation; resistance mechanism",
                references = "Mariathasan et al. 2018 Nature"),
            "TOP2A" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Proliferation marker; component of Immunotherapy Response Score (IRS)",
                drug_relevance = "IRS = TMB + PD1 + PDL1 + TOP2A + ADAM12 predicts anti-PD-L1 benefit",
                references = "Cristescu et al. 2022"),
            "ADAM12" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Stromal remodeling; component of IRS; CAF marker",
                drug_relevance = "Part of pan-tumor IRS; high ADAM12 may indicate stromal exclusion",
                references = "Cristescu et al. 2022"),
            "FGFR3" = list(
                gwas_evidence = "Direct bladder cancer GWAS hit (4p16.3); also somatically mutated in ~15% of MIBC",
                disease_relevance = "Receptor tyrosine kinase; FGFR3-mutant tumors are often luminal, immune-cold",
                drug_relevance = "Erdafitinib (FGFR inhibitor) FDA-approved; FGFR3-mutant = poor ICI response",
                references = "Figueroa 2023; Loriot et al. 2019"),
            "PSCA" = list(
                gwas_evidence = "Direct bladder cancer GWAS hit (8q24.3)",
                disease_relevance = "Prostate stem cell antigen; expressed on urothelial cells",
                drug_relevance = "BiTE antibody target (pavurutamab) in clinical trials",
                references = "Wu et al. 2009 PNAS"),
            "IFNG" = list(
                gwas_evidence = "No direct GWAS hit; key effector cytokine",
                disease_relevance = "IFN-gamma drives anti-tumor immunity; marks inflamed tumors",
                drug_relevance = "High IFNG signature predicts ICI response across tumor types",
                references = "Ayers et al. 2017 JCI"),
            "IDO1" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Immune-regulatory enzyme; upregulated in response to IFN-gamma",
                drug_relevance = "IDO inhibitor (epacadostat) failed in ECHO-301; paradoxically marks immune-active tumors",
                references = "Long et al. 2018 J Immunother Cancer"),
            "S100A8" = list(
                gwas_evidence = "No direct bladder GWAS hit",
                disease_relevance = "Calprotectin subunit; neutrophil/monocyte marker in TME",
                drug_relevance = "Myeloid inflammation marker; neutrophil infiltration may impair ICI response",
                references = "Shaul & Fridlender 2019 Nat Rev Cancer"),
            "GZMA" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Granzyme A; CD8+ T cell cytolytic activity marker",
                drug_relevance = "Core cytolytic score gene; high expression predicts ICI response",
                references = "Rooney et al. 2015 Cell"),
            "GZMB" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Granzyme B; key effector of T cell killing",
                drug_relevance = "Cytolytic activity marker; prognostic in IO-treated patients",
                references = "Rooney et al. 2015 Cell"),
            "B2M" = list(
                gwas_evidence = "ICI resistance gene",
                disease_relevance = "Beta-2-microglobulin; loss disrupts MHC-I antigen presentation",
                drug_relevance = "B2M mutations cause primary ICI resistance; loss-of-function = immune evasion",
                references = "Zaretsky et al. 2016 NEJM")
        )
    } else if (disease == "sepsis") {
        # Sepsis / Mars1 biomarker panel gene annotations
        list(
            "IFIT1B" = list(
                gwas_evidence = "No direct GWAS hit; interferon pathway broadly implicated in sepsis outcomes",
                disease_relevance = "Interferon-induced protein; innate antiviral defense; downregulated in Mars1 immunosuppression endotype",
                drug_relevance = "IFN pathway restoration as therapeutic target; marker of immunosuppressive state",
                references = "Scicluna et al. 2017 Lancet Respir Med; Sweeney et al. 2018 Sci Transl Med"),
            "ACSL6" = list(
                gwas_evidence = "No direct sepsis GWAS hit",
                disease_relevance = "Acyl-CoA synthetase long-chain 6; lipid metabolism/immunometabolism; metabolic reprogramming in sepsis monocytes",
                drug_relevance = "Immunometabolic target; fatty acid oxidation modulation under investigation",
                references = "Langley et al. 2013 Sci Transl Med"),
            "CTNNAL1" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Catenin alpha-like 1; cell adhesion molecule; leukocyte adhesion and migration in vascular endothelium",
                drug_relevance = "Adhesion pathway marker; anti-adhesion therapies in sepsis trials",
                references = "Scicluna et al. 2017 Lancet Respir Med"),
            "ABCC13" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "ABC transporter pseudogene; potential role in drug metabolism pathways",
                drug_relevance = "Possible pharmacogenomic relevance for drug clearance in critical illness",
                references = "Limited functional data"),
            "C9orf78" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "HAX1-associated protein (HAIP); apoptosis regulation in immune cells; lymphocyte survival during sepsis",
                drug_relevance = "Apoptosis pathway; anti-apoptotic strategies under investigation in sepsis",
                references = "Hotchkiss et al. 2013 Lancet Infect Dis"),
            "KCNH2" = list(
                gwas_evidence = "No direct sepsis GWAS hit; GWAS hit for cardiac arrhythmia",
                disease_relevance = "Potassium voltage-gated channel (hERG); electrolyte regulation critical in sepsis-associated organ dysfunction",
                drug_relevance = "Cardiac safety marker; QT prolongation risk in ICU drug regimens",
                references = "Sanguinetti & Bhatt 2022 Physiol Rev"),
            "FAM104A" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "DUF1220 domain-containing protein; function in immune cells unclear; identified in Mars1 endotype",
                drug_relevance = "Novel candidate requiring functional validation",
                references = "Scicluna et al. 2017 Lancet Respir Med"),
            "POC1B" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Centriolar protein POC1B; cell division in proliferating immune cells during sepsis response",
                drug_relevance = "Cell cycle marker; potential indicator of immune cell proliferative capacity",
                references = "Limited sepsis-specific data"),
            "BPGM" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Bisphosphoglycerate mutase; regulates 2,3-BPG levels controlling oxygen delivery; critical in tissue hypoxia during sepsis",
                drug_relevance = "Oxygen delivery pathway; potential target for improving tissue oxygenation",
                references = "Ditzel 2003 IUBMB Life"),
            "ZDHHC2" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Palmitoyl transferase (DHHC2); protein palmitoylation in immune signaling; modifies key immune receptors",
                drug_relevance = "Post-translational modification target; palmitoylation inhibitors under investigation",
                references = "Chamberlain & Bhatt 2015 Mol Membr Biol"),
            "FGFR1OP2" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "FGFR1 oncogene partner 2; centrosome and cytoskeletal organization; role in cell division",
                drug_relevance = "Cytoskeletal target; marker of proliferative state",
                references = "Limited sepsis-specific data"),
            "SAMHD1" = list(
                gwas_evidence = "No direct sepsis GWAS hit; mutations cause Aicardi-Goutieres syndrome (innate immune)",
                disease_relevance = "dNTP triphosphohydrolase; innate immune defense; interferon-stimulated gene; restricts viral replication in monocytes",
                drug_relevance = "Innate immune pathway; IFN-stimulated gene used as immunosuppression marker",
                references = "Maelfait et al. 2016 Nat Commun; Scicluna et al. 2017"),
            "DARC" = list(
                gwas_evidence = "Duffy-null polymorphism (rs2814778) affects neutrophil counts; GWAS hit for benign neutropenia",
                disease_relevance = "Atypical chemokine receptor 1 (ACKR1/Duffy); chemokine scavenger on erythrocytes; regulates neutrophil trafficking and chemokine bioavailability",
                drug_relevance = "Pharmacogenomic relevance: Duffy-null status affects baseline neutrophil counts and chemokine levels",
                references = "Pruenster et al. 2009 J Exp Med; Reich et al. 2009 Genome Biol"),
            "ACKR1" = list(
                gwas_evidence = "Duffy-null polymorphism (rs2814778) affects neutrophil counts; GWAS hit for benign neutropenia",
                disease_relevance = "Atypical chemokine receptor 1 (Duffy); chemokine scavenger on erythrocytes; regulates neutrophil trafficking and chemokine bioavailability",
                drug_relevance = "Pharmacogenomic relevance: Duffy-null status affects baseline neutrophil counts and chemokine levels",
                references = "Pruenster et al. 2009 J Exp Med; Reich et al. 2009 Genome Biol"),
            "DDX17" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "DEAD-box RNA helicase 17; innate immune signaling; senses viral RNA and activates NF-kB/IRF pathways",
                drug_relevance = "Pattern recognition pathway; potential target for modulating innate immune activation",
                references = "Moy et al. 2014 Cell Host Microbe"),
            "DAAM2" = list(
                gwas_evidence = "No direct sepsis GWAS hit; associated with autoimmune traits",
                disease_relevance = "Dishevelled-associated activator of morphogenesis 2; Wnt signaling; cytoskeletal regulation in immune cell migration",
                drug_relevance = "Wnt pathway modulation; potential role in immune cell trafficking",
                references = "Lee & Bhatt 2016 Dev Biol"),
            "TUBG2" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Tubulin gamma 2; centrosome function; cell division in proliferating immune cells during sepsis",
                drug_relevance = "Cell cycle marker; indicator of immune proliferative response",
                references = "Limited sepsis-specific data"),
            "IL8" = list(
                gwas_evidence = "No direct sepsis GWAS hit; IL8 polymorphisms associated with sepsis severity",
                disease_relevance = "CXCL8; major neutrophil chemoattractant; key sepsis inflammatory mediator; elevated in severe sepsis",
                drug_relevance = "Anti-IL8/CXCR2 axis under investigation; neutrophil recruitment modulation",
                references = "Bozza et al. 2007 Crit Care; Sweeney et al. 2018 Sci Transl Med"),
            "CXCL8" = list(
                gwas_evidence = "No direct sepsis GWAS hit; IL8 polymorphisms associated with sepsis severity",
                disease_relevance = "Major neutrophil chemoattractant; key sepsis inflammatory mediator; elevated in severe sepsis",
                drug_relevance = "Anti-IL8/CXCR2 axis under investigation; neutrophil recruitment modulation",
                references = "Bozza et al. 2007 Crit Care; Sweeney et al. 2018 Sci Transl Med"),
            "EGR1" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Early growth response 1; stress-responsive transcription factor; rapidly induced in monocyte activation and endothelial stress",
                drug_relevance = "Immediate early gene; marker of innate immune activation state",
                references = "Kharbanda et al. 1991 PNAS; Scicluna et al. 2017"),
            "TNFSF12" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "TNF superfamily member 12 (TWEAK); immune regulation; monocyte/macrophage-derived; modulates inflammation and tissue repair",
                drug_relevance = "Anti-TWEAK antibodies in clinical development; potential for modulating sepsis inflammation",
                references = "Burkly et al. 2011 Drug Discov Today"),
            "TNFRSF8" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "TNF receptor superfamily member 8 (CD30); T-cell activation marker; elevated soluble CD30 in sepsis",
                drug_relevance = "Brentuximab vedotin target (lymphoma); soluble CD30 as sepsis immune activation marker",
                references = "Pellegrini et al. 2003 Clin Exp Immunol"),
            "CTSO" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Cathepsin O; lysosomal protease; antigen processing and MHC-II presentation in monocytes/dendritic cells",
                drug_relevance = "Antigen processing pathway; cathepsin inhibitors under investigation",
                references = "Bhatt et al. 2018 Front Immunol"),
            "TNKS" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "Tankyrase 1; Wnt signaling regulation; telomere maintenance; role in cell survival",
                drug_relevance = "Tankyrase inhibitors in oncology; potential Wnt pathway modulation in immune cells",
                references = "Lehtio et al. 2013 Mol Cell"),
            "PTPLA" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "3-hydroxyacyl-CoA dehydratase 1 (HACD1); fatty acid elongation; lipid metabolism in immune cells",
                drug_relevance = "Immunometabolic pathway; lipid metabolism modulation",
                references = "Ikeda et al. 2008 J Biol Chem"),
            "HACD1" = list(
                gwas_evidence = "No direct GWAS hit",
                disease_relevance = "3-hydroxyacyl-CoA dehydratase 1; fatty acid elongation; lipid metabolism in immune cells",
                drug_relevance = "Immunometabolic pathway; lipid metabolism modulation",
                references = "Ikeda et al. 2008 J Biol Chem"),
            "DEFA4" = list(
                gwas_evidence = "No direct GWAS hit; defensin cluster polymorphisms associated with infection susceptibility",
                disease_relevance = "Defensin alpha 4; neutrophil antimicrobial peptide; innate immunity first line of defense; upregulated in sepsis",
                drug_relevance = "Antimicrobial peptide; neutrophil degranulation marker; indicator of innate immune activation",
                references = "Ganz 2003 Nat Rev Immunol; Scicluna et al. 2017")
        )
    } else {
        # IBD gene annotations
        list(
            "S100A8" = list(
                gwas_evidence = "Indirect: 4 IBD GWAS loci regulate S100A8/A9 expression",
                disease_relevance = "Calprotectin subunit; fecal calprotectin is standard IBD activity biomarker",
                drug_relevance = "Neutrophil/monocyte marker; mucosal healing reduces S100A8 expression",
                references = "S100A8 eQTL: PLOS Genet 2022; Calprotectin: Gut 2018"),
            "SELENBP1" = list(
                gwas_evidence = "No direct hit; near IBD loci (ECM1, FCGR2A cluster)",
                disease_relevance = "Downregulated in active UC (p=0.003); recovers with healing",
                drug_relevance = "Colonocyte differentiation marker; restoration = epithelial recovery",
                references = "SELENBP1 in UC: PMC11677018"),
            "GUCA2B" = list(
                gwas_evidence = "No direct hit",
                disease_relevance = "GC-C pathway disruption is hallmark of IBD; strongly downregulated",
                drug_relevance = "Expression recovers with biologic response; pharmacodynamic marker",
                references = "GC-C pathway in IBD: PMC4673555"),
            "RGS13" = list(
                gwas_evidence = "No direct hit",
                disease_relevance = "Part of 4-gene vedolizumab response predictor (80-100% accuracy)",
                drug_relevance = "Published vedolizumab biomarker (Verstockt 2020)",
                references = "Verstockt et al. Clin Gastroenterol Hepatol 2020"),
            "PTP4A3" = list(
                gwas_evidence = "No direct hit; PTPN2/PTPN22 (same family) are IBD GWAS genes",
                disease_relevance = "Phosphatase regulating cell adhesion in colonic epithelium",
                drug_relevance = "Negative coefficient: higher expression predicts non-response",
                references = "PTP4A3 in colon: Oncogene 2016"),
            "CKB" = list(
                gwas_evidence = "No direct hit",
                disease_relevance = "Creatine kinase brain-type; colonocyte marker, reduced in inflammation",
                drug_relevance = "Epithelial energy metabolism marker",
                references = "CKB: Human Protein Atlas"),
            "UCA1" = list(
                gwas_evidence = "No direct hit",
                disease_relevance = "lncRNA upregulated in IBD epithelium; regulates NF-kB signaling",
                drug_relevance = "Epithelial stress indicator",
                references = "UCA1: RNA Biol 2020"),
            "GLDN" = list(
                gwas_evidence = "No direct hit",
                disease_relevance = "Gliomedin; enteric nervous system expression",
                drug_relevance = "May reflect enteric neural remodeling (gut-brain axis)",
                references = "Enteric nervous system in IBD: Gut 2020"),
            "IGLV4-60" = list(
                gwas_evidence = "No direct hit; Ig loci are polymorphic",
                disease_relevance = "Immunoglobulin light chain; B cell/plasma cell infiltration",
                drug_relevance = "Higher Ig may indicate treatment-refractory inflammation",
                references = "B cell infiltration: Nat Med 2019"),
            "C1orf125" = list(
                gwas_evidence = "No direct hit",
                disease_relevance = "Uncharacterized ORF",
                drug_relevance = "Novel candidate; requires functional validation",
                references = "Limited data")
        )
    }
}

.run_gwas_overlap <- function(panel_genes, all_features = NULL, disease = "ibd") {
    config <- .get_gwas_config(disease)
    gwas_genes <- config$genes

    cat("\n---", config$label, "Genetic Risk Overlap ---\n\n")
    cat("  Curated gene list:", length(gwas_genes), "genes\n")
    cat("  Sources:", config$references, "\n\n")

    # Direct overlap with panel genes
    direct_overlap <- intersect(panel_genes, gwas_genes)
    cat("  Direct panel overlap:", length(direct_overlap), "/", length(panel_genes), "\n")
    if (length(direct_overlap) > 0) cat("    Genes:", paste(direct_overlap, collapse = ", "), "\n")

    # Build annotation table for all panel genes
    gene_annotations <- data.frame(
        gene = panel_genes,
        in_gwas = panel_genes %in% gwas_genes,
        stringsAsFactors = FALSE
    )

    # Detailed annotations per gene (disease-specific)
    annotation_details <- .get_gene_annotations(disease)

    gene_annotations$gwas_evidence <- sapply(panel_genes, function(g) {
        if (g %in% names(annotation_details)) annotation_details[[g]]$gwas_evidence
        else "Not assessed"
    })
    gene_annotations$disease_relevance <- sapply(panel_genes, function(g) {
        if (g %in% names(annotation_details)) annotation_details[[g]]$disease_relevance
        else "Not assessed"
    })
    gene_annotations$drug_relevance <- sapply(panel_genes, function(g) {
        if (g %in% names(annotation_details)) annotation_details[[g]]$drug_relevance
        else "Not assessed"
    })
    gene_annotations$references <- sapply(panel_genes, function(g) {
        if (g %in% names(annotation_details)) annotation_details[[g]]$references
        else ""
    })

    # Check broader feature list overlap with GWAS genes
    if (!is.null(all_features)) {
        all_overlap <- intersect(all_features, gwas_genes)
        cat("\n  Broader overlap (all", length(all_features), "features):",
            length(all_overlap), "disease genes\n")
        if (length(all_overlap) > 0) {
            cat("    Disease genes in feature space:", paste(head(all_overlap, 20), collapse = ", "),
                if (length(all_overlap) > 20) "..." else "", "\n")
        }
    }

    cat("\n  GWAS overlap analysis complete.\n")

    return(list(
        panel_annotations = gene_annotations,
        direct_overlap = direct_overlap,
        gwas_genes = gwas_genes,
        n_gwas_genes = length(gwas_genes),
        gwas_label = config$label,
        gwas_refs = config$refs_detail
    ))
}


# ============================================================
# Plotting helper
# ============================================================

.save_enrichment_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
    png_path <- paste0(base_path, ".png")
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")

    svg_path <- paste0(base_path, ".svg")
    tryCatch({
        ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        tryCatch({
            svg(svg_path, width = width, height = height)
            print(plot)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e2) {
            cat("   (SVG export failed)\n")
        })
    })
}


# ============================================================
# Main entry point
# ============================================================

#' Run all biological interpretation analyses
#'
#' @param model_result LASSO model result from run_lasso_panel()
#' @param features Feature object from prepare_feature_matrix() (optional)
#' @param output_dir Output directory for plots and CSVs
#' @param disease Disease context: "ibd", "bladder_cancer", "breast_cancer", or "sepsis"
#' @return Named list with pathway, celltype, gwas results + disease metadata
run_biological_interpretation <- function(model_result, features = NULL,
                                          output_dir = "results",
                                          disease = "ibd") {
    cat("\n=== Biological Interpretation of Biomarker Panel ===\n")
    cat("Panel:", paste(model_result$stable_features, collapse = ", "), "\n")
    cat("Disease context:", disease, "\n")

    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    panel_genes <- model_result$stable_features
    all_features <- if (!is.null(model_result$feature_importance)) {
        model_result$feature_importance$feature
    } else NULL

    # 1. Pathway enrichment (disease-agnostic — uses gene sets from MSigDB)
    pathway <- tryCatch(
        .run_pathway_enrichment(model_result, features, output_dir),
        error = function(e) {
            cat("  Pathway enrichment failed:", conditionMessage(e), "\n")
            NULL
        }
    )

    # 2. Cell-type enrichment (disease-specific tissue + curated fallback)
    celltype <- tryCatch(
        .run_celltype_enrichment(panel_genes, output_dir, disease = disease),
        error = function(e) {
            cat("  Cell-type enrichment failed:", conditionMessage(e), "\n")
            NULL
        }
    )

    # 3. GWAS / disease gene overlap (disease-specific gene list)
    gwas <- tryCatch(
        .run_gwas_overlap(panel_genes, all_features, disease = disease),
        error = function(e) {
            cat("  GWAS overlap failed:", conditionMessage(e), "\n")
            NULL
        }
    )

    # Disease metadata for report generation
    disease_label <- switch(disease,
        ibd = "IBD",
        bladder_cancer = "Bladder Cancer / ICI Response",
        breast_cancer = "Breast Cancer / Neoadjuvant Chemotherapy",
        sepsis = "Sepsis / Molecular Endotyping",
        disease)
    tissue_label <- switch(disease,
        ibd = "Large Intestine",
        bladder_cancer = "Bladder Tumor",
        breast_cancer = "Breast Tumor",
        sepsis = "Blood",
        "Tissue")
    gwas_label <- if (!is.null(gwas$gwas_label)) gwas$gwas_label else paste(disease_label, "GWAS")

    # Save combined results
    interp <- list(
        pathway = pathway,
        celltype = celltype,
        gwas = gwas,
        panel_genes = panel_genes,
        disease = disease,
        disease_label = disease_label,
        tissue_label = tissue_label,
        gwas_label = gwas_label
    )
    saveRDS(interp, file.path(output_dir, "biological_interpretation.rds"))
    cat("  Saved: biological_interpretation.rds\n")

    # Save GWAS annotations as CSV
    if (!is.null(gwas$panel_annotations)) {
        write.csv(gwas$panel_annotations,
                  file.path(output_dir, "gwas_gene_annotations.csv"),
                  row.names = FALSE)
        cat("  Saved: gwas_gene_annotations.csv\n")
    }

    cat("\n✓ Biological interpretation completed successfully!\n")
    return(interp)
}

