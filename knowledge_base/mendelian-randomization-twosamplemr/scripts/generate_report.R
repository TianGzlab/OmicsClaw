# =============================================================================
# Mendelian Randomization - Report Generation
# =============================================================================
# Functions:
#   generate_report()  - Generate PDF analysis report (intro/methods/results/conclusions)
# =============================================================================

#' Generate a structured MR analysis report
#'
#' Creates a PDF report with Introduction, Methods, Results, Figures, and Conclusions.
#' Requires rmarkdown + LaTeX (tinytex) for PDF. Falls back to HTML or base R PDF.
#'
#' @param mr_results MR results from run_mr()
#' @param sensitivity Sensitivity results from run_sensitivity()
#' @param dat Harmonized data from load_data.R
#' @param output_dir Directory for saving report (default: "mr_results")
generate_report <- function(mr_results, sensitivity, dat, output_dir = "mr_results") {
    cat("\n=== Generating MR Analysis Report ===\n\n")

    if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

    has_rmarkdown <- requireNamespace("rmarkdown", quietly = TRUE)

    if (has_rmarkdown) {
        rmd_content <- .build_rmd_content(mr_results, sensitivity, dat, output_dir)
        rmd_path <- file.path(output_dir, "mr_report.Rmd")
        writeLines(rmd_content, rmd_path)

        # Try PDF first, then HTML
        pdf_ok <- tryCatch({
            rmarkdown::render(rmd_path,
                output_format = rmarkdown::pdf_document(
                    toc = FALSE, latex_engine = "xelatex"),
                output_file = "mr_report.pdf",
                output_dir = output_dir, quiet = TRUE)
            cat("   Saved:", file.path(output_dir, "mr_report.pdf"), "\n")
            TRUE
        }, error = function(e) {
            cat("   PDF rendering failed (", conditionMessage(e), ")\n")
            FALSE
        })

        if (!pdf_ok) {
            html_ok <- tryCatch({
                rmarkdown::render(rmd_path,
                    output_format = "html_document",
                    output_file = "mr_report.html",
                    output_dir = output_dir, quiet = TRUE)
                cat("   Saved:", file.path(output_dir, "mr_report.html"),
                    "(HTML fallback)\n")
                TRUE
            }, error = function(e) {
                cat("   HTML also failed. Using base R PDF...\n")
                FALSE
            })

            if (!html_ok) {
                .generate_base_pdf(mr_results, sensitivity, dat, output_dir)
            }
        }

        unlink(rmd_path)
    } else {
        cat("   rmarkdown not available. Using base R PDF...\n")
        .generate_base_pdf(mr_results, sensitivity, dat, output_dir)
    }

    cat("\n\u2713 Report generated successfully!\n")
    return(invisible(NULL))
}

# --- Rmd content builder -----------------------------------------------------

.build_rmd_content <- function(mr_results, sensitivity, dat, output_dir) {
    exposure <- unique(dat$exposure)[1]
    outcome <- unique(dat$outcome)[1]
    n_instruments <- nrow(dat)
    date_str <- format(Sys.Date(), "%B %d, %Y")

    ivw <- mr_results[mr_results$method == "Inverse variance weighted", ]
    het <- sensitivity$heterogeneity
    plei <- sensitivity$pleiotropy

    ivw_sig <- ivw$pval[1] < 0.05
    direction <- if (ivw$b[1] > 0) "positive" else "negative"
    sig_text <- if (ivw_sig) "statistically significant" else "non-significant"
    het_ok <- all(het$Q_pval > 0.05)
    plei_ok <- all(plei$pval > 0.05)
    methods_agree <- length(unique(sign(mr_results$b))) == 1

    # --- F-statistics ---
    fstats <- (dat$beta.exposure / dat$se.exposure)^2
    mean_f <- mean(fstats)
    min_f <- min(fstats)
    n_weak <- sum(fstats < 10)

    # --- Method concordance ---
    nonsig_methods <- mr_results$method[mr_results$pval >= 0.05]
    discordant_methods <- mr_results$method[sign(mr_results$b) != sign(ivw$b)]

    # --- Results table ---
    table_rows <- paste(sapply(seq_len(nrow(mr_results)), function(i) {
        sprintf("| %s | %.4f | %.4f | %.2e | %d |",
                mr_results$method[i], mr_results$b[i], mr_results$se[i],
                mr_results$pval[i], mr_results$nsnp[i])
    }), collapse = "\n")

    # --- Heterogeneity ---
    het_lines <- paste(sapply(seq_len(nrow(het)), function(i) {
        sprintf("- %s: Q = %.2f, p = %.2e%s",
                het$method[i], het$Q[i], het$Q_pval[i],
                if (het$Q_pval[i] < 0.05) " **(significant)**" else "")
    }), collapse = "\n")

    # --- Pleiotropy ---
    plei_text <- sprintf("- MR-Egger intercept = %.4f (SE = %.4f, p = %.2e)%s",
                         plei$egger_intercept[1], plei$se[1], plei$pval[1],
                         if (plei$pval[1] < 0.05) " **(significant)**" else "")

    # --- Directionality ---
    if (!is.null(sensitivity$directionality)) {
        d <- sensitivity$directionality
        dir_text <- sprintf(
            "- Steiger test: %s (p = %.2e, R^2^ exposure = %.4f, R^2^ outcome = %.4f)",
            if (d$correct_causal_direction[1]) "**correct** causal direction"
            else "**INCORRECT** direction",
            d$steiger_pval[1], d$snp_r2.exposure[1], d$snp_r2.outcome[1])
        if (isTRUE(sensitivity$steiger_binary_warning)) {
            dir_text <- paste0(dir_text,
                "\n- **Note:** Outcome is binary (case-control). R^2^ was computed using ",
                "quantitative approximation because case/control counts were unavailable. ",
                "For accurate results, use `get_r_from_lor()` with population prevalence.")
        }
    } else {
        dir_text <- "- Steiger test: not available (sample size information missing)"
    }

    # --- MR-PRESSO ---
    presso_text <- ""
    if (!is.null(sensitivity$mr_presso)) {
        global_p <- sensitivity$mr_presso$`MR-PRESSO results`$`Global Test`$Pvalue
        presso_text <- paste0("**MR-PRESSO Outlier Detection:**\n\n",
            sprintf("- Global test p = %.2e", global_p))
        if (global_p < 0.05) {
            presso_text <- paste0(presso_text, " **(significant -- outliers present)**\n")
            outlier_test <- sensitivity$mr_presso$`MR-PRESSO results`$`Outlier Test`
            if (!is.null(outlier_test)) {
                outlier_idx <- which(outlier_test$Pvalue < 0.05)
                if (length(outlier_idx) > 0) {
                    presso_text <- paste0(presso_text, "- Outlier instruments: ",
                        paste(dat$SNP[outlier_idx], collapse = ", "), "\n")
                }
            }
            main_res <- sensitivity$mr_presso$`Main MR results`
            if (nrow(main_res) >= 2) {
                presso_text <- paste0(presso_text,
                    sprintf("- Outlier-corrected IVW: beta = %.4f, p = %.2e\n",
                            main_res$`Causal Estimate`[2], main_res$`P-value`[2]))
            }
        } else {
            presso_text <- paste0(presso_text, " (no significant outliers)\n")
        }
        presso_text <- paste0(presso_text, "\n")
    }

    # --- Outlier SNPs ---
    outlier_text <- ""
    if (!is.null(sensitivity$outlier_snps) && nrow(sensitivity$outlier_snps) > 0) {
        outlier_text <- paste0("**Discordant Instruments:**\n\n",
            "The following SNPs show effects in the **opposite direction** to the IVW estimate ",
            "and may be pleiotropic:\n\n")
        for (j in seq_len(nrow(sensitivity$outlier_snps))) {
            outlier_text <- paste0(outlier_text, sprintf("- %s: beta = %.4f\n",
                sensitivity$outlier_snps$SNP[j], sensitivity$outlier_snps$b[j]))
        }
        outlier_text <- paste0(outlier_text, "\n")
    }

    # --- Leave-one-out ---
    loo <- sensitivity$leaveoneout
    n_loo <- nrow(loo) - 1
    all_est <- loo$b[nrow(loo)]
    loo_range <- range(loo$b[1:n_loo])
    pct_changes <- abs((loo$b[1:n_loo] - all_est) / all_est) * 100
    n_influential <- sum(pct_changes > 20)

    loo_text <- sprintf("- Leave-one-out: %d combinations tested, effect range %.4f to %.4f",
                        n_loo, loo_range[1], loo_range[2])
    if (n_influential > 0) {
        loo_text <- paste0(loo_text,
            sprintf(" (**%d influential SNP(s)**, >20%% change)", n_influential))
    } else {
        loo_text <- paste0(loo_text, " (no SNP changes estimate >20%%, **robust**)")
    }

    # --- Evidence assessment ---
    if (ivw_sig && methods_agree && het_ok && plei_ok) {
        evidence <- paste0("**Strong** -- IVW significant, methods concordant, ",
                           "no heterogeneity or pleiotropy detected.")
    } else if (ivw_sig && methods_agree) {
        evidence <- paste0("**Suggestive** -- IVW significant and methods concordant, ",
                           "but sensitivity analyses raise some concerns.")
    } else if (ivw_sig) {
        evidence <- paste0("**Weak** -- IVW significant but methods disagree or ",
                           "sensitivity analyses indicate potential violations.")
    } else {
        evidence <- "**Insufficient** -- IVW estimate not significant at p < 0.05."
    }

    # --- Figure references ---
    fig_section <- ""
    figs <- list(
        c("mr_scatter_plot.png", "Scatter Plot",
          "SNP-exposure vs SNP-outcome associations with MR method regression lines."),
        c("mr_forest_plot.png", "Forest Plot",
          "Individual SNP Wald ratio estimates and combined method estimates."),
        c("mr_funnel_plot.png", "Funnel Plot",
          "Precision vs effect size; asymmetry suggests directional pleiotropy."),
        c("mr_leaveoneout_plot.png", "Leave-One-Out Plot",
          "IVW estimate stability when each instrument is removed in turn."))

    for (f in figs) {
        if (file.exists(file.path(output_dir, f[1]))) {
            fig_section <- paste0(fig_section,
                "\n### ", f[2], "\n\n", f[3], "\n\n",
                "![", f[2], "](", f[1], "){width=95%}\n\n",
                "\\newpage\n\n")
        }
    }

    # --- Assemble Rmd ---
    paste0(
        "---\n",
        "title: \"Mendelian Randomization Analysis Report\"\n",
        "subtitle: \"", exposure, " \\u2192 ", outcome, "\"\n",
        "date: \"", date_str, "\"\n",
        "output:\n",
        "  pdf_document:\n",
        "    toc: false\n",
        "    latex_engine: xelatex\n",
        "---\n\n",

        "## Introduction\n\n",
        "This report presents the results of a **two-sample Mendelian Randomization (MR)** ",
        "analysis testing whether **", exposure, "** (exposure) has a causal effect on ",
        "**", outcome, "** (outcome).\n\n",
        "MR uses genetic variants as instrumental variables to estimate causal effects from ",
        "observational data. By leveraging the random assortment of alleles at conception, MR ",
        "approximates a natural randomized controlled trial, reducing bias from confounding ",
        "and reverse causation.\n\n",

        "## Methods\n\n",
        "**", n_instruments, "** independent genetic variants were selected as instrumental ",
        "variables for the exposure at genome-wide significance (p < 5 x 10^-8^) and clumped ",
        "for linkage disequilibrium (r^2^ < 0.001, 10 Mb window). Exposure and outcome data ",
        "were harmonized to align effect alleles.\n\n",
        "Four complementary MR methods were applied:\n\n",
        "1. **Inverse-Variance Weighted (IVW)** -- Primary estimate; assumes balanced pleiotropy\n",
        "2. **MR-Egger** -- Allows directional pleiotropy; intercept tests for bias\n",
        "3. **Weighted Median** -- Consistent if 50% or more of instruments are valid\n",
        "4. **Weighted Mode** -- Consistent if the plurality of instruments identify the same effect\n\n",
        "Sensitivity analyses: Cochran's Q (heterogeneity), MR-Egger intercept (pleiotropy), ",
        "MR-PRESSO (outlier detection, if heterogeneity significant), ",
        "Steiger directionality (causal direction), and leave-one-out (influential instruments).\n\n",
        "**Instrument strength:** Mean F-statistic = ", round(mean_f, 1),
        " (min = ", round(min_f, 1), "). ",
        if (n_weak > 0) paste0(n_weak, " instrument(s) with F < 10 (weak). ") else "",
        if (mean_f >= 10) "Instruments are sufficiently strong (F > 10).\n\n"
        else "**Warning:** Mean F < 10 suggests weak instrument bias.\n\n",

        "## Results\n\n",
        "### Primary MR Estimates\n\n",
        "| Method | Beta | SE | P-value | nSNP |\n",
        "|--------|-----:|----:|--------:|-----:|\n",
        table_rows, "\n\n",
        "The IVW estimate indicates a **", sig_text, "** ", direction, " effect of ",
        exposure, " on ", outcome,
        " ($\\beta$ = ", round(ivw$b[1], 4),
        ", SE = ", round(ivw$se[1], 4),
        ", p = ", formatC(ivw$pval[1], format = "e", digits = 2), ").\n\n",
        if (length(nonsig_methods) > 0) paste0(
            "**Note:** The following method(s) did not reach significance: ",
            paste(nonsig_methods, collapse = ", "), ". ") else "",
        if (length(discordant_methods) > 0) paste0(
            "**Warning:** ", paste(discordant_methods, collapse = ", "),
            " showed effect(s) in the **opposite direction** to IVW. ") else "",
        if (length(nonsig_methods) > 0 || length(discordant_methods) > 0) "\n\n" else "",

        "### Sensitivity Analyses\n\n",
        "**Heterogeneity (Cochran's Q):**\n\n", het_lines, "\n\n",
        if (het_ok) "No significant heterogeneity detected.\n\n"
        else "Significant heterogeneity detected -- some instruments may be invalid.\n\n",
        "**Directional Pleiotropy:**\n\n", plei_text, "\n\n",
        if (plei_ok) "No evidence of directional pleiotropy.\n\n"
        else "Directional pleiotropy detected -- IVW estimate may be biased.\n\n",
        "**Causal Direction:**\n\n", dir_text, "\n\n",
        "**Leave-One-Out:**\n\n", loo_text, "\n\n",
        presso_text,
        outlier_text,

        "\\newpage\n\n",
        "## Figures\n", fig_section,

        "## Conclusions\n\n",
        "**Overall evidence for causal effect of ", exposure, " on ", outcome, ":** ",
        evidence, "\n\n",
        "### Caveats\n\n",
        "- MR estimates reflect lifelong genetically-predicted differences, not acute interventions\n",
        "- Results are specific to the ancestry of the GWAS populations studied\n",
        "- Standard MR assumes a linear dose-response relationship\n",
        "- Winner's curse may inflate associations if instruments selected from discovery GWAS\n",
        "- Sample overlap between exposure and outcome GWAS may introduce bias\n"
    )
}

# --- Base R PDF fallback ------------------------------------------------------

.generate_base_pdf <- function(mr_results, sensitivity, dat, output_dir) {
    pdf_path <- file.path(output_dir, "mr_report.pdf")

    suppressPackageStartupMessages({
        library(TwoSampleMR)
        library(ggplot2)
        library(ggprism)
    })

    exposure <- unique(dat$exposure)[1]
    outcome <- unique(dat$outcome)[1]
    ivw <- mr_results[mr_results$method == "Inverse variance weighted", ]
    het <- sensitivity$heterogeneity
    plei <- sensitivity$pleiotropy

    pdf(pdf_path, width = 11, height = 8.5)

    # --- Page 1: Title + summary ---
    par(mar = c(1, 1, 1, 1))
    plot.new()
    text(0.5, 0.92, "Mendelian Randomization Analysis Report",
         cex = 2, font = 2, adj = 0.5)
    text(0.5, 0.85, paste(exposure, "to", outcome), cex = 1.4, adj = 0.5)
    text(0.5, 0.80, format(Sys.Date(), "%B %d, %Y"),
         cex = 1, col = "gray40", adj = 0.5)

    y <- 0.70
    text(0.05, y, "Primary MR Results:", cex = 1.2, font = 2, adj = 0)
    y <- y - 0.02
    for (i in seq_len(nrow(mr_results))) {
        y <- y - 0.04
        text(0.05, y, sprintf("  %s:  beta=%.4f  SE=%.4f  p=%.2e  (n=%d)",
                              mr_results$method[i], mr_results$b[i], mr_results$se[i],
                              mr_results$pval[i], mr_results$nsnp[i]),
             cex = 0.85, adj = 0, family = "mono")
    }

    y <- y - 0.06
    text(0.05, y, "Sensitivity Analyses:", cex = 1.2, font = 2, adj = 0)
    y <- y - 0.02
    for (i in seq_len(nrow(het))) {
        y <- y - 0.04
        text(0.05, y, sprintf("  Heterogeneity (%s): Q=%.2f, p=%.2e",
                              het$method[i], het$Q[i], het$Q_pval[i]),
             cex = 0.85, adj = 0, family = "mono")
    }
    y <- y - 0.04
    text(0.05, y, sprintf("  Egger intercept: %.4f, p=%.2e",
                           plei$egger_intercept[1], plei$pval[1]),
         cex = 0.85, adj = 0, family = "mono")

    y <- y - 0.06
    text(0.05, y, "Conclusions:", cex = 1.2, font = 2, adj = 0)
    y <- y - 0.04
    methods_agree <- length(unique(sign(mr_results$b))) == 1
    het_ok <- all(het$Q_pval > 0.05)
    plei_ok <- all(plei$pval > 0.05)
    ivw_sig <- ivw$pval[1] < 0.05

    if (ivw_sig && methods_agree && het_ok && plei_ok) {
        verdict <- "Strong evidence for causal effect"
    } else if (ivw_sig && methods_agree) {
        verdict <- "Suggestive evidence (sensitivity concerns)"
    } else if (ivw_sig) {
        verdict <- "Weak evidence (methods disagree or sensitivity violations)"
    } else {
        verdict <- "Insufficient evidence (IVW not significant)"
    }
    text(0.05, y, paste(" ", verdict), cex = 0.95, adj = 0)

    # --- Pages 2-5: Plots ---
    tryCatch({
        p <- mr_scatter_plot(mr_results, dat)[[1]] + theme_prism(base_size = 12)
        print(p)
    }, error = function(e) NULL)

    tryCatch({
        p <- mr_forest_plot(sensitivity$singlesnp)[[1]] + theme_prism(base_size = 12)
        print(p)
    }, error = function(e) NULL)

    tryCatch({
        p <- mr_funnel_plot(sensitivity$singlesnp)[[1]] + theme_prism(base_size = 12)
        print(p)
    }, error = function(e) NULL)

    tryCatch({
        p <- mr_leaveoneout_plot(sensitivity$leaveoneout)[[1]] + theme_prism(base_size = 12)
        print(p)
    }, error = function(e) NULL)

    dev.off()
    cat("   Saved:", pdf_path, "(base R)\n")
}

