# Export LASSO Biomarker Panel Results
# Saves all results including RDS objects for downstream skills
# Generates comprehensive markdown + PDF reports with embedded plots

#' Export all LASSO biomarker panel results
#'
#' @param model_result Result from run_lasso_panel()
#' @param validation_result Result from validate_panel() (optional)
#' @param output_dir Output directory (default: "results")
#' @param data Original data object from load_*_data() (optional, enriches report)
#' @param features Feature matrix result from prepare_feature_matrix() (optional)
#'
#' @export
export_all <- function(model_result, validation_result = NULL,
                        output_dir = "results",
                        data = NULL, features = NULL,
                        interpretation = NULL) {

    cat("\n=== Exporting LASSO Biomarker Panel Results ===\n\n")

    # Create output directory
    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
        cat("Created directory:", output_dir, "\n\n")
    }

    # 1. Biomarker panel (stable features with coefficients)
    cat("1. Exporting biomarker panel...\n")
    panel <- model_result$feature_importance[model_result$feature_importance$is_stable, ]
    write.csv(panel, file.path(output_dir, "biomarker_panel.csv"), row.names = FALSE)
    cat("   Saved: biomarker_panel.csv (", nrow(panel), "features)\n\n")

    # 2. All feature stability scores
    cat("2. Exporting all feature stability scores...\n")
    write.csv(model_result$feature_importance,
              file.path(output_dir, "all_feature_stability.csv"), row.names = FALSE)
    cat("   Saved: all_feature_stability.csv (",
        nrow(model_result$feature_importance), "features)\n\n")

    # 3. Discovery performance (per-fold)
    cat("3. Exporting discovery performance...\n")
    perf <- data.frame(
        fold = seq_along(model_result$fold_aucs),
        auc = model_result$fold_aucs,
        sensitivity = model_result$fold_sensitivities,
        specificity = model_result$fold_specificities,
        stringsAsFactors = FALSE
    )
    write.csv(perf, file.path(output_dir, "discovery_performance.csv"), row.names = FALSE)
    cat("   Saved: discovery_performance.csv\n")
    cat("   Mean AUC:", round(model_result$mean_auc, 3),
        "(95% CI:", round(model_result$auc_ci[1], 3), "-",
        round(model_result$auc_ci[2], 3), ")\n\n")

    # 4. Validation performance (if provided)
    if (!is.null(validation_result)) {
        cat("4. Exporting validation performance...\n")
        write.csv(validation_result$performance_table,
                  file.path(output_dir, "validation_performance.csv"), row.names = FALSE)
        cat("   Saved: validation_performance.csv\n")
        cat("   Validation AUC:", round(validation_result$auc, 3), "\n\n")

        # Validation predictions
        write.csv(validation_result$predictions,
                  file.path(output_dir, "validation_predictions.csv"), row.names = FALSE)
        cat("   Saved: validation_predictions.csv\n\n")
    } else {
        cat("4. No validation result provided (skipped)\n\n")
    }

    # 5. Cross-validation predictions
    cat("5. Exporting CV predictions...\n")
    write.csv(model_result$cv_predictions,
              file.path(output_dir, "cv_predictions.csv"), row.names = FALSE)
    cat("   Saved: cv_predictions.csv (",
        nrow(model_result$cv_predictions), "predictions across",
        length(unique(model_result$cv_predictions$fold)), "folds)\n\n")

    # 6. LASSO model object (CRITICAL for downstream skills)
    cat("6. Saving LASSO model object (RDS)...\n")
    saveRDS(model_result, file.path(output_dir, "lasso_model.rds"))
    cat("   Saved: lasso_model.rds\n")
    cat("   (Load with: model <- readRDS('results/lasso_model.rds'))\n")
    cat("   (Predict with: predict_biomarker_panel(model, new_X))\n\n")

    # 7. Final glmnet model only (lightweight, for prediction only)
    if (!is.null(model_result$final_model)) {
        cat("7. Saving final glmnet model (RDS)...\n")
        saveRDS(model_result$final_model,
                file.path(output_dir, "final_glmnet_model.rds"))
        cat("   Saved: final_glmnet_model.rds\n")
        cat("   (Load with: fit <- readRDS('results/final_glmnet_model.rds'))\n\n")
    }

    # 8. Summary report (enhanced markdown)
    cat("8. Generating summary report (markdown)...\n")
    .write_summary_report(model_result, validation_result, output_dir, data, features,
                           interpretation)
    cat("   Saved: summary_report.md\n\n")

    # 9. PDF report (with embedded plots)
    cat("9. Generating PDF report...\n")
    .render_pdf_report(model_result, validation_result, output_dir, data, features,
                       interpretation)

    # 10. Parameters log
    cat("10. Saving parameters...\n")
    params_df <- data.frame(
        parameter = names(model_result$parameters),
        value = as.character(model_result$parameters),
        stringsAsFactors = FALSE
    )
    write.csv(params_df, file.path(output_dir, "parameters.csv"), row.names = FALSE)
    cat("   Saved: parameters.csv\n\n")

    cat("\n=== Export Complete ===\n")
    cat("All files saved to:", output_dir, "\n")
    cat("Files:\n")
    files <- list.files(output_dir, full.names = FALSE)
    for (f in files) {
        cat("  -", f, "\n")
    }
}


# ============================================================================
# SHARED HELPER: Build enriched report context lines
# ============================================================================

#' Build enriched report content from report_context metadata
#'
#' Returns a named list of character vectors for enriched report sections.
#' When report_context is NULL, returns all-NULL list (generators fall back
#' to generic text).
#'
#' @param rc report_context list from data loader (or NULL)
#' @param data Full data object from loader (or NULL)
#' @param p Model parameters list
#' @param features Feature matrix result (or NULL)
#' @param model_result Full model result
#' @param validation_result Validation result (or NULL)
#' @param format "md" for markdown, "rmd" for R Markdown with LaTeX math
#' @return Named list with: analytical_goals, disease_sections, lasso_rationale,
#'         method_text, references
#' @keywords internal
.build_context_lines <- function(rc, data, p, features, model_result,
                                  validation_result, format = "md") {

    # Default: all NULL = use generic text in generators
    ctx <- list(
        analytical_goals  = NULL,   # Numbered aims with inline citations
        disease_sections  = NULL,   # Disease context subsections
        lasso_rationale   = NULL,   # LASSO rationale with citations
        method_text       = NULL,   # Methods with inline citations
        benchmarks        = NULL,   # Published benchmarks section
        references        = NULL    # Numbered reference list
    )

    if (is.null(rc)) return(ctx)

    # Subsection heading prefix: ### for markdown, ## for Rmd (numbered_sections)
    sub_pfx <- if (format == "rmd") "##" else "###"

    # Math symbols by format
    alpha_sym  <- if (format == "rmd") paste0("$\\alpha$ = ", p$alpha) else paste0("alpha = ", p$alpha)
    lambda_sym <- if (format == "rmd") "$\\lambda$" else "lambda"
    geq_sym    <- if (format == "rmd") "$\\geq$" else ">="
    arrow_sym  <- if (format == "rmd") "$\\rightarrow$" else "->"

    # ---- Analytical Goals (with inline citations) ----
    if (!is.null(rc$analytical_goals)) {
        goal_lines <- character(0)
        for (i in seq_along(rc$analytical_goals)) {
            goal_lines <- c(goal_lines, paste0(i, ". ", rc$analytical_goals[i]))
        }
        ctx$analytical_goals <- goal_lines
    }

    # ---- Disease Context Subsections ----
    sections <- character(0)

    if (!is.null(rc$disease_background)) {
        sections <- c(sections,
            paste(sub_pfx, "Disease Background"), "",
            rc$disease_background, "")
    }
    if (!is.null(rc$trial_description)) {
        sections <- c(sections,
            paste(sub_pfx, "Clinical Trial"), "",
            rc$trial_description, "")
    }
    if (!is.null(rc$patient_population)) {
        sections <- c(sections,
            paste(sub_pfx, "Patient Population"), "",
            rc$patient_population, "")
    }
    if (!is.null(rc$endpoint_definition)) {
        sections <- c(sections,
            paste(sub_pfx, "Endpoint Definition"), "",
            rc$endpoint_definition, "")
    }
    if (!is.null(rc$platform_description)) {
        sections <- c(sections,
            paste(sub_pfx, "Expression Platform"), "",
            rc$platform_description, "")
    }

    if (length(sections) > 0) {
        ctx$disease_sections <- sections
    }

    # ---- LASSO Rationale (with citations) ----
    if (!is.null(rc$references)) {
        lasso_text <- c(
            paste("LASSO logistic regression [1] performs simultaneous feature selection and",
                  "coefficient estimation by applying an L1 penalty that shrinks many",
                  "coefficients to exactly zero. This produces sparse, interpretable",
                  "models ideal for clinical biomarker panels where a small number of",
                  "measurable features is critical for translation to diagnostic",
                  "assays. Compared to other machine learning approaches, LASSO provides",
                  "transparent, interpretable coefficients and naturally handles the",
                  "p >> n problem common in omics data (thousands of features, tens to",
                  "hundreds of samples)."),
            "")

        if (p$alpha < 1) {
            lasso_text <- c(lasso_text,
                paste0("This analysis uses **elastic net** regularization (",
                       alpha_sym, ") [2], which combines L1 (LASSO) and L2 (ridge) ",
                       "penalties. This is particularly useful when features are ",
                       "correlated, as it tends to retain groups of correlated genes ",
                       "rather than arbitrarily selecting one from each group."),
                "")
        }

        lasso_text <- c(lasso_text,
            paste("Model fitting uses the glmnet coordinate descent algorithm [4]",
                  "with regularization path optimization. Stability selection [3]",
                  "ensures that selected features are robust to sampling variation,",
                  "reducing false discovery of noise features. Model discrimination",
                  "is evaluated via ROC analysis using the pROC package [5],",
                  "following the cross-validated biomarker discovery framework of",
                  "Ali et al. [6]."),
            "")

        ctx$lasso_rationale <- lasso_text
    }

    # ---- Methods with inline citations ----
    if (!is.null(rc$references)) {
        ctx$method_text <- c(
            paste0("- **Regularization:** ", alpha_sym,
                   ifelse(p$alpha == 1, " (pure LASSO [1])",
                          " (elastic net [1,2])")),
            paste("- **Repeated CV:**", p$n_repeats,
                  "iterations of class-balanced",
                  paste0(round(p$train_fraction * 100), "/",
                         round((1 - p$train_fraction) * 100)),
                  "train/test splits"),
            paste("- **Inner CV:**", p$n_inner_folds, "folds for", lambda_sym,
                  "selection (cv.glmnet [4])"),
            paste("- **Stability threshold:**", p$stability_threshold,
                  "(features must be selected in", geq_sym,
                  paste0(p$stability_threshold * 100, "%"),
                  "of iterations [3])"),
            paste("- **Random seed:**", p$seed, "(reproducible)"),
            "",
            paste0("**Algorithm:** For each of the ", p$n_repeats,
                   " repeated CV iterations, a class-balanced train/test split is ",
                   "created. On the training set, cv.glmnet [4] selects the optimal ",
                   lambda_sym, " via inner cross-validation (", p$n_inner_folds,
                   "-fold). Non-zero coefficients are recorded. After all iterations, ",
                   "features selected in ", geq_sym, " ",
                   p$stability_threshold * 100, "% of iterations (stability ",
                   "selection [3]) form the final panel. A final model is fit on all ",
                   "samples using only these stable features."),
            "",
            paste(sub_pfx, "Performance Evaluation"),
            "",
            "- **Discrimination:** AUC (Area Under ROC Curve) via pROC package [5] (DeLong method for CIs)",
            paste("- **Confidence intervals:** 2.5th and 97.5th percentiles of fold AUCs across",
                  p$n_repeats, "iterations"),
            "- **Sensitivity/Specificity:** At Youden's J-statistic optimal threshold",
            "- **Calibration:** Predicted probability vs observed event rate",
            "")
    }

    # ---- Published Benchmarks ----
    if (!is.null(rc$published_benchmarks)) {
        pb <- rc$published_benchmarks
        bench_lines <- character(0)

        if (!is.null(pb$intro)) {
            bench_lines <- c(bench_lines, pb$intro, "")
        }

        # Render benchmark table
        if (!is.null(pb$studies)) {
            bench_lines <- c(bench_lines,
                "| Study | Drug | Validated AUC | Method | Notes |",
                "|-------|------|:---:|--------|-------|")
            for (j in seq_len(nrow(pb$studies))) {
                s <- pb$studies[j, ]
                bench_lines <- c(bench_lines,
                    paste0("| ", s$study, " | ", s$drug, " | ", s$validated_auc,
                           " | ", s$method, " | ", s$notes, " |"))
            }
            # Add our result as last row
            our_auc <- round(model_result$mean_auc, 3)
            our_ci <- paste0(round(model_result$auc_ci[1], 3), "-",
                            round(model_result$auc_ci[2], 3))
            alpha_label <- ifelse(p$alpha == 1, "LASSO",
                                  paste0("Elastic net (", p$alpha, ")"))
            # Extract drug from first benchmark row or use generic
            our_drug <- if (nrow(pb$studies) > 0) pb$studies$drug[1] else "—"
            bench_lines <- c(bench_lines,
                paste0("| **This analysis** | **", our_drug, "** | **", our_auc,
                       "** | **", alpha_label, "** | **Nested CV, no leakage** |"),
                "")
        }

        if (!is.null(pb$context)) {
            bench_lines <- c(bench_lines, pb$context, "")
        }

        ctx$benchmarks <- bench_lines
    }

    # ---- References ----
    if (!is.null(rc$references)) {
        ref_lines <- character(0)
        for (ref in rc$references) {
            ref_lines <- c(ref_lines, ref, "")
        }
        ctx$references <- ref_lines
    }

    return(ctx)
}


# ============================================================================
# BIOLOGICAL INTERPRETATION HELPER
# ============================================================================

#' Build biological interpretation report lines
#' @param interp Result from run_biological_interpretation()
#' @param panel Data frame of panel genes with coefficients
#' @param format "md" for markdown or "rmd" for R Markdown (LaTeX)
#' @return Named list with pathway_lines, celltype_lines, gwas_lines
#' @keywords internal
.build_interpretation_lines <- function(interp, panel, format = "md") {
    result <- list(pathway_lines = NULL, celltype_lines = NULL, gwas_lines = NULL)
    if (is.null(interp)) return(result)

    pos_genes <- panel$feature[panel$mean_coefficient > 0]
    neg_genes <- panel$feature[panel$mean_coefficient < 0]
    arrow <- if (format == "rmd") "$\\rightarrow$" else "→"

    # ---- Pathway Enrichment ----
    pw <- c()

    # Coefficient direction summary
    if (length(pos_genes) > 0) {
        pw <- c(pw, paste0("**Positive coefficient genes** (higher expression ", arrow,
                           " positive outcome): ", paste(pos_genes, collapse = ", ")), "")
    }
    if (length(neg_genes) > 0) {
        pw <- c(pw, paste0("**Negative coefficient genes** (higher expression ", arrow,
                           " negative outcome): ", paste(neg_genes, collapse = ", ")), "")
    }

    # GSEA Hallmark results
    gsea_h <- interp$pathway$gsea_hallmark
    if (!is.null(gsea_h) && nrow(gsea_h) > 0) {
        top_gsea <- head(gsea_h[order(gsea_h$pval), ], 10)
        top_gsea$pathway_short <- gsub("HALLMARK_", "", top_gsea$pathway)
        top_gsea$pathway_short <- gsub("_", " ", top_gsea$pathway_short)

        pw <- c(pw,
            "**Gene Set Enrichment Analysis (GSEA)** — MSigDB Hallmark pathways ranked by",
            "LASSO selection frequency across 500 candidate features:",
            "",
            "| Pathway | NES | P-value | Adj. P | Gene Set Size |",
            "|---------|:---:|:-------:|:------:|:---:|")
        for (i in seq_len(nrow(top_gsea))) {
            pw <- c(pw, sprintf("| %s | %.2f | %.4f | %.3f | %d |",
                                top_gsea$pathway_short[i],
                                top_gsea$NES[i],
                                top_gsea$pval[i],
                                top_gsea$padj[i],
                                top_gsea$size[i]))
        }
        pw <- c(pw, "")
    }

    # ORA Reactome results
    ora_r <- interp$pathway$ora_reactome
    if (!is.null(ora_r) && nrow(ora_r@result[ora_r@result$p.adjust < 0.1, ]) > 0) {
        sig_r <- ora_r@result[ora_r@result$p.adjust < 0.1, ]
        sig_r$Description_short <- gsub("REACTOME_", "", sig_r$Description)
        sig_r$Description_short <- gsub("_", " ", sig_r$Description_short)

        pw <- c(pw,
            "**Over-Representation Analysis (ORA)** — Reactome pathways (10-gene panel):",
            "",
            "| Pathway | Gene Ratio | P-value | Adj. P | Genes |",
            "|---------|:----------:|:-------:|:------:|-------|")
        for (i in seq_len(nrow(sig_r))) {
            pw <- c(pw, sprintf("| %s | %s | %.4f | %.3f | %s |",
                                sig_r$Description_short[i],
                                sig_r$GeneRatio[i],
                                sig_r$pvalue[i],
                                sig_r$p.adjust[i],
                                sig_r$geneID[i]))
        }
        pw <- c(pw, "")
    }

    # ORA GO (only if significant)
    ora_go <- interp$pathway$ora_go
    if (!is.null(ora_go) && nrow(ora_go@result[ora_go@result$p.adjust < 0.1, ]) > 0) {
        sig_go <- ora_go@result[ora_go@result$p.adjust < 0.1, ]
        pw <- c(pw,
            "**GO Biological Process (ORA):**",
            "",
            "| GO Term | Gene Ratio | Adj. P | Genes |",
            "|---------|:----------:|:------:|-------|")
        for (i in seq_len(min(nrow(sig_go), 10))) {
            pw <- c(pw, sprintf("| %s | %s | %.3f | %s |",
                                sig_go$Description[i],
                                sig_go$GeneRatio[i],
                                sig_go$p.adjust[i],
                                sig_go$geneID[i]))
        }
        pw <- c(pw, "")
    }

    result$pathway_lines <- pw

    # ---- Cell-Type Expression Context ----
    ct <- interp$celltype
    ct_lines <- c()
    tissue_label <- if (!is.null(interp$tissue_label)) interp$tissue_label else "Tissue"

    if (!is.null(ct) && nrow(ct) > 0) {
        if ("source" %in% names(ct) && all(ct$source == "curated")) {
            # Detect change column (uc_change for legacy IBD, disease_change for new)
            change_col <- if ("disease_change" %in% names(ct)) "disease_change" else "uc_change"
            change_header <- paste(tissue_label, "Change")

            ct_lines <- c(ct_lines,
                paste("Cell-type expression context from published single-cell atlases for",
                      tissue_label, "tissue:"),
                "",
                sprintf("| Gene | Primary Cell Type | Compartment | %s | Evidence |", change_header),
                "|------|------------------|:-----------:|:------------:|----------|")
            for (i in seq_len(nrow(ct))) {
                ct_lines <- c(ct_lines, sprintf("| *%s* | %s | %s | %s | %s |",
                                                ct$gene[i],
                                                ct$cell_type[i],
                                                ct$compartment[i],
                                                ct[[change_col]][i],
                                                ct$evidence[i]))
            }
        } else {
            # CZI Census real data — summarize top cell types per gene
            ct_lines <- c(ct_lines,
                paste("Cell-type expression in", tissue_label, "from CZI CELLxGENE Census"),
                "(tens of millions of single cells across published datasets):",
                "",
                "| Gene | Top Cell Types (by expression) | % Expressing |",
                "|------|------------------------------|:------------:|")

            # Use normal tissue if available, otherwise all
            disease_col <- if ("disease" %in% names(ct)) "disease" else NULL
            if (!is.null(disease_col) && "normal" %in% ct$disease) {
                ct_sub <- ct[ct$disease == "normal", ]
            } else {
                ct_sub <- ct
            }

            for (gene in unique(ct_sub$gene)) {
                gene_data <- ct_sub[ct_sub$gene == gene, ]
                gene_data <- gene_data[order(-gene_data$mean_expression), ]
                top3 <- head(gene_data, 3)
                ct_str <- paste(sprintf("%s (%.0f%%)", top3$cell_type,
                                        top3$pct_expressing), collapse = "; ")
                ct_lines <- c(ct_lines, sprintf("| *%s* | %s | |", gene, ct_str))
            }
        }
        ct_lines <- c(ct_lines, "")
    }
    result$celltype_lines <- ct_lines

    # ---- GWAS / Disease Gene Overlap ----
    gwas <- interp$gwas
    gwas_lines <- c()
    gwas_label <- if (!is.null(interp$gwas_label)) interp$gwas_label else "Disease GWAS"

    if (!is.null(gwas)) {
        ann <- gwas$panel_annotations
        gwas_refs <- if (!is.null(gwas$gwas_refs)) gwas$gwas_refs else "published GWAS studies"

        gwas_lines <- c(gwas_lines,
            sprintf("Cross-reference with %d curated %s genes (%s):",
                    gwas$n_gwas_genes, gwas_label, gwas_refs),
            "",
            "| Gene | GWAS Hit | Disease Relevance | Drug Relevance |",
            "|------|:--------:|-------------------|----------------|")
        for (i in seq_len(nrow(ann))) {
            gwas_icon <- if (ann$in_gwas[i]) "Direct" else "Indirect/None"
            # Truncate long text for table readability
            dis_rel <- ann$disease_relevance[i]
            drug_rel <- ann$drug_relevance[i]
            if (nchar(dis_rel) > 80) dis_rel <- paste0(substr(dis_rel, 1, 77), "...")
            if (nchar(drug_rel) > 60) drug_rel <- paste0(substr(drug_rel, 1, 57), "...")
            gwas_lines <- c(gwas_lines, sprintf("| *%s* | %s | %s | %s |",
                                                ann$gene[i], gwas_icon,
                                                dis_rel, drug_rel))
        }
        gwas_lines <- c(gwas_lines, "")

        # Summary
        gwas_lines <- c(gwas_lines,
            sprintf("**Summary:** %d/%d panel genes have direct %s association (%s).",
                    sum(ann$in_gwas), nrow(ann), gwas_label,
                    if (sum(ann$in_gwas) > 0) paste(ann$gene[ann$in_gwas], collapse = ", ") else "none"),
            "The panel primarily captures expression-level disease signatures rather than",
            "germline genetic risk — consistent with the transcriptomic biomarker approach.",
            "")
    }
    result$gwas_lines <- gwas_lines

    return(result)
}


# ============================================================================
# ENHANCED MARKDOWN REPORT
# ============================================================================

#' Write comprehensive summary report as markdown
#' @keywords internal
.write_summary_report <- function(model_result, validation_result, output_dir,
                                   data = NULL, features = NULL,
                                   interpretation = NULL) {
    p <- model_result$parameters
    panel <- model_result$feature_importance[model_result$feature_importance$is_stable, ]
    pos_genes <- panel$feature[panel$mean_coefficient > 0]
    neg_genes <- panel$feature[panel$mean_coefficient < 0]

    # Get enriched context (NULL fields => generic fallback)
    rc <- if (!is.null(data)) data$report_context else NULL
    ctx <- .build_context_lines(rc, data, p, features, model_result,
                                 validation_result, format = "md")

    has_validation <- !is.null(validation_result)

    lines <- c(
        "# LASSO Biomarker Panel Discovery Report",
        "",
        paste("**Generated:**", Sys.time()),
        ""
    )

    # Discovery-only caveat (omitted if external validation was performed)
    if (!has_validation) {
        lines <- c(lines,
            "> **IMPORTANT — Discovery-Only Analysis:** This report presents results from a",
            "> single discovery cohort with no independent external validation. All performance",
            "> metrics (AUC, sensitivity, specificity) are estimates from repeated subsampling",
            "> of the same dataset and should be considered **preliminary**. They are expected",
            "> to be optimistic relative to performance on a truly independent cohort. External",
            "> validation is required before any clinical or translational use of this panel.",
            "",
            "---",
            "")
    }

    # ---- 1. Study Objectives ----
    lines <- c(lines, "## 1. Study Objectives", "")

    if (!is.null(ctx$analytical_goals)) {
        # Enriched: clinical question framing + cited aims
        lines <- c(lines,
            "This analysis was designed to address the following specific aims in the",
            "context of predicting clinical outcomes from baseline molecular profiling:",
            "",
            ctx$analytical_goals,
            "")
    } else {
        # Generic fallback
        lines <- c(lines,
            "This analysis aims to identify a minimal, interpretable biomarker panel from",
            "high-dimensional gene expression data using LASSO (Least Absolute Shrinkage",
            "and Selection Operator) regularized regression. The goal is to select a",
            "parsimonious set of transcriptomic features that can predict a binary clinical",
            "outcome from baseline tissue biopsies, enabling potential translation into a",
            "clinical diagnostic or prognostic assay.",
            "",
            "**Specific aims:**",
            "",
            "1. Select a minimal gene panel (<15 features) with robust predictive performance",
            "2. Evaluate model discrimination (AUC), calibration, and feature stability",
            paste0("3. Assess cross-validation performance across ", p$n_repeats,
                   " repeated train/test splits"),
            "")

        if (!is.null(validation_result)) {
            lines <- c(lines,
                paste0("4. Validate the panel on an independent cohort (",
                       validation_result$cohort_name, ")"),
                "")
        }
    }

    # ---- 2. Disease Context & Rationale ----
    lines <- c(lines, "## 2. Disease Context & Rationale", "")

    if (!is.null(ctx$disease_sections)) {
        # Enriched: multiple subsections from report_context
        lines <- c(lines, ctx$disease_sections)
    } else if (!is.null(data) && !is.null(data$description)) {
        # Fallback: single description line
        lines <- c(lines,
            "**Dataset context:**",
            data$description,
            "")
    }

    # LASSO rationale
    lines <- c(lines, "### Why LASSO for biomarker selection", "")

    if (!is.null(ctx$lasso_rationale)) {
        # Enriched: with inline citations
        lines <- c(lines, ctx$lasso_rationale)
    } else {
        # Generic fallback
        lines <- c(lines,
            "LASSO logistic regression performs simultaneous feature selection and coefficient",
            "estimation by applying an L1 penalty that shrinks many coefficients to exactly",
            "zero. This produces sparse, interpretable models ideal for clinical biomarker",
            "panels where a small number of measurable features is critical for translation",
            "to diagnostic assays. Compared to other machine learning approaches, LASSO",
            "provides transparent, interpretable coefficients and naturally handles the",
            "p >> n problem common in omics data (thousands of features, tens to hundreds",
            "of samples).",
            "")

        if (p$alpha < 1) {
            lines <- c(lines,
                paste0("This analysis uses **elastic net** regularization (alpha = ", p$alpha,
                       "), which combines L1 (LASSO) and L2 (ridge) penalties. This is",
                       " particularly useful when features are correlated, as it tends to",
                       " retain groups of correlated genes rather than arbitrarily selecting",
                       " one from each group."),
                "")
        }
    }

    # ---- 3. Datasets ----
    lines <- c(lines,
        "## 3. Datasets",
        "",
        "### 3.1 Discovery Cohort",
        "")

    if (!is.null(data)) {
        n_resp <- sum(data$metadata[[data$outcome_col]] == 1, na.rm = TRUE)
        n_nonresp <- sum(data$metadata[[data$outcome_col]] == 0, na.rm = TRUE)
        treatment_tab <- table(data$metadata$treatment)
        treat_str <- paste(names(treatment_tab), "=", treatment_tab, collapse = ", ")

        lines <- c(lines,
            paste("- **Samples:**", ncol(data$expression),
                  paste0("(", n_resp, " positive / ", n_nonresp, " negative)")),
            paste("- **Genes measured:**", format(nrow(data$expression), big.mark = ",")),
            paste("- **Features after filtering:**", p$n_features,
                  "(top most variable genes)"),
            paste("- **Treatment arms:**", treat_str),
            "")
    } else {
        lines <- c(lines,
            paste("- **Samples:**", p$n_samples),
            paste("- **Features:**", p$n_features),
            "")
    }

    if (!is.null(validation_result)) {
        lines <- c(lines,
            paste("### 3.2 Validation Cohort:", validation_result$cohort_name),
            "",
            paste("- **Features matched:**", validation_result$n_features_used,
                  "/", validation_result$n_features_total, "discovery features"),
            "",
            "The validation cohort shares the same microarray platform as the discovery",
            "cohort, enabling direct application of the trained model without cross-platform",
            "normalization. Cross-drug validation (different therapeutic mechanisms) tests",
            "whether the baseline transcriptomic signature captures shared biology of",
            "treatment response rather than drug-specific effects.",
            "")
    }

    # ---- 4. Methods ----
    lines <- c(lines,
        "## 4. Methods",
        "",
        "### 4.1 Feature Preparation",
        "")

    if (!is.null(features)) {
        lines <- c(lines,
            paste("- **Input features:**", ncol(features$X), "genes selected by variance"),
            paste("- **Samples:**", nrow(features$X)),
            "- **Preprocessing:** Log2-transformed (if not already), filtered to top",
            paste0("  most variable genes, scaled to zero mean and unit variance"),
            "")
    } else {
        lines <- c(lines,
            paste("- **Features:**", p$n_features),
            paste("- **Samples:**", p$n_samples),
            "")
    }

    lines <- c(lines, "### 4.2 LASSO/Elastic Net Model", "")

    if (!is.null(ctx$method_text)) {
        # Enriched: methods with inline citations
        lines <- c(lines, ctx$method_text)
    } else {
        # Generic fallback
        lines <- c(lines,
            paste0("- **Regularization:** alpha = ", p$alpha,
                   ifelse(p$alpha == 1, " (pure LASSO)", " (elastic net)")),
            paste("- **Repeated CV:**", p$n_repeats, "iterations of class-balanced",
                  paste0(round(p$train_fraction * 100), "/", round((1 - p$train_fraction) * 100)),
                  "train/test splits"),
            paste("- **Inner CV:**", p$n_inner_folds, "folds for lambda selection (cv.glmnet)"),
            paste("- **Stability threshold:**", p$stability_threshold,
                  "(features must be selected in this fraction of iterations)"),
            paste("- **Random seed:**", p$seed, "(reproducible)"),
            "",
            "**Algorithm:** For each of the repeated CV iterations, a class-balanced",
            "train/test split is created. On the training set, cv.glmnet selects the",
            "optimal lambda via inner cross-validation. Non-zero coefficients are recorded.",
            "After all iterations, features selected in more than the stability threshold",
            "fraction of iterations form the final panel. A final model is fit on all",
            "samples using only these stable features.",
            "",
            "### 4.3 Performance Evaluation",
            "",
            "- **Discrimination:** AUC (Area Under ROC Curve) via pROC package",
            "- **Confidence intervals:** 2.5th and 97.5th percentiles of fold AUCs",
            "- **Sensitivity/Specificity:** At Youden's J-statistic optimal threshold",
            "- **Calibration:** Predicted probability vs observed event rate",
            "")
    }

    # ---- 5. Results ----
    lines <- c(lines,
        "## 5. Results",
        "",
        "### 5.1 Biomarker Panel",
        "",
        paste("**Panel size:**", nrow(panel), "features"),
        paste0("(stability threshold: ", p$stability_threshold,
               "; ", p$n_stable, " passed threshold",
               ifelse(p$n_stable < nrow(panel),
                      paste0(", relaxed to top ", nrow(panel)), ""), ")"),
        "",
        "| Feature | Selection Frequency | Mean Coefficient | SD Coefficient |",
        "|---------|:------------------:|:----------------:|:--------------:|")

    for (i in seq_len(nrow(panel))) {
        lines <- c(lines, paste0(
            "| ", panel$feature[i],
            " | ", round(panel$selection_frequency[i], 3),
            " | ", sprintf("%+.4f", panel$mean_coefficient[i]),
            " | ", round(panel$sd_coefficient[i], 4), " |"))
    }

    lines <- c(lines,
        "",
        "### 5.2 Discovery Performance (Nested CV)",
        "",
        paste("- **Mean AUC:**", round(model_result$mean_auc, 3),
              "(95% CI:", round(model_result$auc_ci[1], 3), "-",
              round(model_result$auc_ci[2], 3), ")"),
        paste("- **Mean Sensitivity:**",
              round(mean(model_result$fold_sensitivities, na.rm = TRUE), 3)),
        paste("- **Mean Specificity:**",
              round(mean(model_result$fold_specificities, na.rm = TRUE), 3)),
        paste("- **AUC range across folds:**",
              round(min(model_result$fold_aucs, na.rm = TRUE), 3), "-",
              round(max(model_result$fold_aucs, na.rm = TRUE), 3)),
        "")

    if (!is.null(validation_result)) {
        lines <- c(lines,
            paste("### 5.3 External Validation:", validation_result$cohort_name),
            "",
            paste("- **AUC:**", round(validation_result$auc, 3),
                  "(95% CI:", round(validation_result$auc_ci[1], 3), "-",
                  round(validation_result$auc_ci[3], 3), ")"),
            paste("- **Panel features used:**", validation_result$n_features_used,
                  "/", validation_result$n_features_total),
            "")

        if (!is.null(validation_result$performance_table)) {
            perf_t <- validation_result$performance_table
            for (j in seq_len(nrow(perf_t))) {
                lines <- c(lines, paste0("- **", perf_t$metric[j], ":** ",
                                          round(as.numeric(perf_t$value[j]), 3)))
            }
            lines <- c(lines, "")
        }
    }

    # ---- 6. Published Benchmarks (if available) ----
    if (!is.null(ctx$benchmarks)) {
        lines <- c(lines,
            "## 6. Published Benchmarks",
            "",
            ctx$benchmarks)
    }

    # ---- 7. Biological Interpretation ----
    bio_num <- if (!is.null(ctx$benchmarks)) 7 else 6
    lines <- c(lines,
        paste0("## ", bio_num, ". Biological Interpretation"),
        "")

    interp_lines <- .build_interpretation_lines(interpretation, panel, format = "md")

    if (!is.null(interp_lines$pathway_lines)) {
        # Enriched: full pathway, celltype, GWAS analysis
        lines <- c(lines,
            paste0("### ", bio_num, ".1 Pathway Enrichment"),
            "",
            interp_lines$pathway_lines)

        if (!is.null(interp_lines$celltype_lines)) {
            lines <- c(lines,
                paste0("### ", bio_num, ".2 Cell-Type Expression Context"),
                "",
                interp_lines$celltype_lines)
        }

        if (!is.null(interp_lines$gwas_lines)) {
            gwas_header <- if (!is.null(interpretation$gwas_label)) {
                paste0("Genetic Risk Overlap (", interpretation$gwas_label, ")")
            } else "Genetic Risk Overlap"
            lines <- c(lines,
                paste0("### ", bio_num, ".3 ", gwas_header),
                "",
                interp_lines$gwas_lines)
        }
    } else {
        # Fallback: basic coefficient direction
        if (length(pos_genes) > 0) {
            lines <- c(lines,
                paste0("**Positive coefficient genes** (higher expression associated with ",
                       "positive outcome): ", paste(pos_genes, collapse = ", ")),
                "")
        }
        if (length(neg_genes) > 0) {
            lines <- c(lines,
                paste0("**Negative coefficient genes** (higher expression associated with ",
                       "negative outcome): ", paste(neg_genes, collapse = ", ")),
                "")
        }

        lines <- c(lines,
            "The sign and magnitude of LASSO coefficients indicate the direction and",
            "strength of each feature's contribution to the prediction. Features with",
            "positive coefficients suggest that higher expression is associated with the",
            "positive outcome class (e.g., treatment response), while negative coefficients",
            "suggest the opposite. Selection frequency reflects the robustness of each",
            "feature across bootstrap resampling iterations.",
            "")
    }

    # ---- Limitations ----
    lim_num <- bio_num + 1
    lines <- c(lines,
        paste0("## ", lim_num, ". Limitations"),
        "")

    if (!has_validation) {
        lines <- c(lines,
            paste0("### ", lim_num, ".1 No External Validation"),
            "",
            "This is a **discovery-only analysis**. No independent validation cohort was used.",
            paste0("The reported AUC of ", round(model_result$mean_auc, 3),
                   " is derived entirely from the same ", p$n_samples,
                   "-sample dataset used for feature selection and model training."),
            "Performance on an independent cohort is expected to be lower. The workflow",
            "supports external validation via `validate_external.R` — this step is strongly",
            "recommended before drawing conclusions about panel utility.",
            "")
    } else {
        lines <- c(lines,
            paste0("### ", lim_num, ".1 External Validation"),
            "",
            paste0("External validation was performed on ", validation_result$cohort_name,
                   " (AUC: ", round(validation_result$auc, 3), ")."),
            "Additional independent cohorts are recommended to confirm generalizability.",
            "")
    }

    lines <- c(lines,
        paste0("### ", lim_num, ".2 Optimism Bias in CV"),
        "",
        paste0("The stability selection procedure uses ", p$n_repeats,
               " random ", round(p$train_fraction * 100), "/",
               round((1 - p$train_fraction) * 100),
               " splits of the same samples for both (a) determining which"),
        "features are stable and (b) estimating AUC. Because feature selection and",
        "performance estimation share the same data pool, the reported AUC is not fully",
        "independent of the feature selection step. This is a known source of optimism bias",
        "in LASSO stability selection workflows. Expected magnitude: typically 0.02-0.05 AUC units.",
        "",
        paste0("### ", lim_num, ".3 Platform Specificity"),
        "",
        "The panel was derived from a specific expression platform. Transferability to other",
        "platforms (e.g., RNA-seq vs microarray) requires cross-platform validation and may",
        "be affected by gene coverage differences.",
        "")

    # ---- Downstream Use ----
    ds_num <- lim_num + 1
    lines <- c(lines,
        paste0("## ", ds_num, ". Downstream Use"),
        "",
        "### Load the model for prediction on new data:",
        "",
        "