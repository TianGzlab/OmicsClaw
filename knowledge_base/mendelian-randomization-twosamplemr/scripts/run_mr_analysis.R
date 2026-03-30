# =============================================================================
# Mendelian Randomization - Core Analysis & Sensitivity Tests
# =============================================================================
# Functions:
#   run_mr(dat)                  - Primary MR methods (IVW, Egger, WM, WMode)
#   run_sensitivity(dat, res)    - Sensitivity analyses (heterogeneity, pleiotropy, etc.)
# =============================================================================

suppressPackageStartupMessages({
    library(TwoSampleMR)
})

# --- Primary MR Analysis ----------------------------------------------------

#' Run primary MR analysis with standard methods
#'
#' Methods applied:
#'   - Inverse-Variance Weighted (IVW): primary estimate
#'   - MR-Egger: allows all instruments to have pleiotropic effects
#'   - Weighted Median: consistent if >50% instruments are valid
#'   - Weighted Mode: consistent if plurality of instruments are valid
#'
#' @param dat Harmonized data from load_data.R
#' @return Data frame of MR results (one row per method)
run_mr <- function(dat) {
    cat("\n=== Running Primary MR Analysis ===\n\n")

    n_snps <- nrow(dat)
    cat("  Using", n_snps, "instruments\n")
    cat("  Exposure:", unique(dat$exposure), "\n")
    cat("  Outcome: ", unique(dat$outcome), "\n\n")

    # F-statistics for instrument strength
    fstats <- (dat$beta.exposure / dat$se.exposure)^2
    mean_f <- mean(fstats)
    min_f <- min(fstats)
    n_weak <- sum(fstats < 10)
    cat("  Instrument strength (F-statistics):\n")
    cat("    Mean F:", round(mean_f, 1), "| Min F:", round(min_f, 1),
        "| Weak (F<10):", n_weak, "of", n_snps, "\n")
    if (n_weak > 0) {
        cat("    \u26a0 ", n_weak, " instrument(s) with F < 10 (weak instruments may bias toward null)\n")
    }
    if (mean_f < 10) {
        cat("    \u26a0 WARNING: Mean F < 10 suggests widespread weak instrument bias\n")
    }
    cat("\n")

    # Define methods
    methods <- c(
        "mr_ivw",
        "mr_egger_regression",
        "mr_weighted_median",
        "mr_weighted_mode"
    )
    method_names <- c("IVW", "MR-Egger", "Weighted Median", "Weighted Mode")

    # Run MR
    mr_results <- mr(dat, method_list = methods)

    # Print results summary
    cat("  Results:\n")
    cat("  ", paste(rep("-", 72), collapse = ""), "\n")
    cat(sprintf("  %-20s %10s %10s %10s %6s\n", "Method", "Beta", "SE", "P-value", "nSNP"))
    cat("  ", paste(rep("-", 72), collapse = ""), "\n")
    for (i in seq_len(nrow(mr_results))) {
        cat(sprintf("  %-20s %10.4f %10.4f %10.2e %6d\n",
                    mr_results$method[i],
                    mr_results$b[i],
                    mr_results$se[i],
                    mr_results$pval[i],
                    mr_results$nsnp[i]))
    }
    cat("  ", paste(rep("-", 72), collapse = ""), "\n")

    # Interpret IVW result
    ivw <- mr_results[mr_results$method == "Inverse variance weighted", ]
    if (nrow(ivw) > 0) {
        direction <- if (ivw$b > 0) "positive" else "negative"
        sig <- if (ivw$pval < 0.05) "statistically significant" else "not statistically significant"
        cat("\n  IVW estimate: ", round(ivw$b, 4),
            " (", sig, ", p = ", formatC(ivw$pval, format = "e", digits = 2), ")\n", sep = "")
        cat("  Direction: ", direction, " effect of exposure on outcome\n", sep = "")
    }

    # Method concordance check
    all_directions <- sign(mr_results$b)
    nonsig_methods <- mr_results$method[mr_results$pval >= 0.05]
    discordant_methods <- mr_results$method[all_directions != sign(ivw$b)]

    if (length(discordant_methods) > 0) {
        cat("\n  \u26a0 METHOD DISAGREEMENT: ", paste(discordant_methods, collapse = ", "),
            " point(s) in opposite direction to IVW\n", sep = "")
    }
    if (length(nonsig_methods) > 0) {
        cat("  Non-significant methods: ", paste(nonsig_methods, collapse = ", "), "\n")
        cat("  (Investigate whether non-significance reflects low power or genuine absence of effect)\n")
    }

    cat("\n✓ MR analysis completed successfully! (", length(methods), " methods applied)\n", sep = "")

    return(mr_results)
}

# --- Sensitivity Analyses ----------------------------------------------------

#' Run comprehensive sensitivity analyses
#'
#' Tests performed:
#'   - Cochran's Q: heterogeneity across instruments
#'   - MR-Egger intercept: directional pleiotropy
#'   - Steiger directionality: confirms causal direction
#'   - Leave-one-out: identifies influential SNPs
#'   - Single SNP: per-instrument Wald ratio estimates
#'
#' @param dat Harmonized data from load_data.R
#' @param mr_results MR results from run_mr()
#' @return List with heterogeneity, pleiotropy, mr_presso, directionality,
#'   leaveoneout, singlesnp, outlier_snps
run_sensitivity <- function(dat, mr_results) {
    cat("\n=== Running Sensitivity Analyses ===\n\n")

    results <- list()

    # 1. Heterogeneity (Cochran's Q)
    cat("1/5 Heterogeneity (Cochran's Q)...\n")
    results$heterogeneity <- mr_heterogeneity(dat)
    for (i in seq_len(nrow(results$heterogeneity))) {
        q_val <- results$heterogeneity$Q[i]
        q_p <- results$heterogeneity$Q_pval[i]
        method <- results$heterogeneity$method[i]
        sig <- if (q_p < 0.05) "SIGNIFICANT heterogeneity detected" else "No significant heterogeneity"
        cat("  ", method, ": Q =", round(q_val, 2), ", p =",
            formatC(q_p, format = "e", digits = 2), "→", sig, "\n")
    }

    # MR-PRESSO if significant heterogeneity detected
    results$mr_presso <- NULL
    if (any(results$heterogeneity$Q_pval < 0.05)) {
        cat("  → Significant heterogeneity detected. Running MR-PRESSO for outlier detection...\n")
        results$mr_presso <- tryCatch({
            if (!requireNamespace("MRPRESSO", quietly = TRUE)) {
                cat("    MRPRESSO not installed. Install with: remotes::install_github('rondolab/MR-PRESSO')\n")
                cat("    Skipping outlier detection.\n")
                NULL
            } else {
                presso <- MRPRESSO::mr_presso(
                    BetaOutcome = "beta.outcome",
                    BetaExposure = "beta.exposure",
                    SdOutcome = "se.outcome",
                    SdExposure = "se.exposure",
                    OUTLIERtest = TRUE,
                    DISTORTIONtest = TRUE,
                    data = as.data.frame(dat),
                    NbDistribution = 1000,
                    SignifThreshold = 0.05
                )
                # Report global test
                global_p <- presso$`MR-PRESSO results`$`Global Test`$Pvalue
                cat("    MR-PRESSO global test p =", formatC(global_p, format = "e", digits = 2))
                if (global_p < 0.05) {
                    cat(" → SIGNIFICANT (outliers present)\n")
                    # Report outliers
                    outlier_test <- presso$`MR-PRESSO results`$`Outlier Test`
                    if (!is.null(outlier_test)) {
                        outlier_idx <- which(outlier_test$Pvalue < 0.05)
                        if (length(outlier_idx) > 0) {
                            cat("    Outlier SNPs identified by MR-PRESSO:\n")
                            for (oi in outlier_idx) {
                                cat("      ", dat$SNP[oi], " (p =",
                                    formatC(outlier_test$Pvalue[oi], format = "e", digits = 2), ")\n")
                            }
                        }
                    }
                    # Report corrected estimate
                    main_res <- presso$`Main MR results`
                    if (nrow(main_res) >= 2) {
                        cat("    Outlier-corrected IVW: beta =", round(main_res$`Causal Estimate`[2], 4),
                            ", p =", formatC(main_res$`P-value`[2], format = "e", digits = 2), "\n")
                    }
                } else {
                    cat(" → no significant outliers\n")
                }
                presso
            }
        }, error = function(e) {
            cat("    MR-PRESSO failed: ", conditionMessage(e), "\n")
            NULL
        })
    }
    cat("\n")

    # 2. Pleiotropy (MR-Egger intercept)
    cat("2/5 Directional pleiotropy (MR-Egger intercept)...\n")
    results$pleiotropy <- mr_pleiotropy_test(dat)
    egger_int <- results$pleiotropy$egger_intercept[1]
    egger_p <- results$pleiotropy$pval[1]
    sig <- if (egger_p < 0.05) "SIGNIFICANT directional pleiotropy detected" else "No evidence of directional pleiotropy"
    cat("  Egger intercept =", round(egger_int, 4), ", p =",
        formatC(egger_p, format = "e", digits = 2), "→", sig, "\n\n")

    # 3. Steiger directionality test
    cat("3/5 Steiger directionality test...\n")

    # Check if outcome is binary (log-odds scale) and correct R² if possible
    results$steiger_binary_warning <- FALSE
    is_binary_outcome <- FALSE
    if ("units.outcome" %in% names(dat)) {
        is_binary_outcome <- any(grepl("log odds|log.odds|logOR", dat$units.outcome, ignore.case = TRUE))
    }

    if (is_binary_outcome) {
        has_case_control <- "ncase.outcome" %in% names(dat) && !all(is.na(dat$ncase.outcome))
        has_eaf <- "eaf.outcome" %in% names(dat) && !all(is.na(dat$eaf.outcome))
        if (has_case_control && has_eaf) {
            cat("  Binary outcome detected - computing liability-scale R\u00b2 with get_r_from_lor()\n")
            prevalence <- dat$ncase.outcome[1] / (dat$ncase.outcome[1] + dat$ncontrol.outcome[1])
            dat$r.outcome <- get_r_from_lor(
                lor = dat$beta.outcome,
                af = dat$eaf.outcome,
                ncase = dat$ncase.outcome,
                ncontrol = dat$ncontrol.outcome,
                prevalence = prevalence
            )
        } else {
            cat("  \u26a0 Binary outcome detected but case/control counts or EAF unavailable.\n")
            cat("    Steiger R\u00b2 will use quantitative approximation (may be inaccurate).\n")
            cat("    For accurate results, pre-compute dat$r.outcome using get_r_from_lor().\n")
            results$steiger_binary_warning <- TRUE
        }
    }

    results$directionality <- tryCatch({
        dir_test <- directionality_test(dat)
        direction <- if (dir_test$correct_causal_direction[1]) "CORRECT" else "INCORRECT"
        cat("  Causal direction:", direction, "\n")
        cat("  Steiger p-value:", formatC(dir_test$steiger_pval[1], format = "e", digits = 2), "\n")
        cat("  R\u00b2 exposure:", round(dir_test$snp_r2.exposure[1], 4), "\n")
        cat("  R\u00b2 outcome: ", round(dir_test$snp_r2.outcome[1], 4), "\n")
        if (results$steiger_binary_warning) {
            cat("  \u26a0 Outcome R\u00b2 may be inaccurate for binary trait (see warning above)\n")
        }
        cat("\n")
        dir_test
    }, error = function(e) {
        cat("  Warning: Steiger test failed (", conditionMessage(e), ")\n")
        cat("  This may occur if sample sizes are unavailable.\n\n")
        NULL
    })

    # 4. Leave-one-out analysis
    cat("4/5 Leave-one-out analysis...\n")
    results$leaveoneout <- mr_leaveoneout(dat)
    n_loo <- nrow(results$leaveoneout) - 1  # Last row is "All" combined
    range_b <- range(results$leaveoneout$b[1:n_loo])
    cat("  Tested", n_loo, "leave-one-out combinations\n")
    cat("  Effect range:", round(range_b[1], 4), "to", round(range_b[2], 4), "\n")

    # Check for influential SNPs (estimate changes by >20% when removed)
    all_estimate <- results$leaveoneout$b[nrow(results$leaveoneout)]
    loo_estimates <- results$leaveoneout$b[1:n_loo]
    pct_change <- abs((loo_estimates - all_estimate) / all_estimate) * 100
    influential <- which(pct_change > 20)
    if (length(influential) > 0) {
        cat("  ⚠ Potentially influential SNPs (>20% change when removed):\n")
        for (idx in influential) {
            cat("    ", results$leaveoneout$SNP[idx], "→",
                round(pct_change[idx], 1), "% change\n")
        }
    } else {
        cat("  No single SNP changes the estimate by >20% (robust)\n")
    }
    cat("\n")

    # 5. Single-SNP analysis
    cat("5/5 Single-SNP (Wald ratio) analysis...\n")
    results$singlesnp <- mr_singlesnp(dat)
    n_snps <- nrow(results$singlesnp) - 1
    cat("  Computed Wald ratios for", n_snps, "individual instruments\n")

    # Flag discordant outlier SNPs (opposite direction to IVW)
    ivw_b <- mr_results$b[mr_results$method == "Inverse variance weighted"]
    snp_estimates <- results$singlesnp[1:n_snps, ]
    discordant_idx <- which(sign(snp_estimates$b) != sign(ivw_b))
    results$outlier_snps <- NULL
    if (length(discordant_idx) > 0) {
        results$outlier_snps <- snp_estimates[discordant_idx, ]
        cat("  \u26a0 Discordant SNPs (opposite direction to IVW):\n")
        for (di in discordant_idx) {
            cat("    ", snp_estimates$SNP[di], ": beta =",
                round(snp_estimates$b[di], 4), "\n")
        }
        cat("  These SNPs may be pleiotropic instruments — investigate biological function.\n")
    }
    cat("\n")

    # Summary interpretation
    cat("\n--- Sensitivity Summary ---\n")
    het_ok <- all(results$heterogeneity$Q_pval > 0.05)
    plei_ok <- all(results$pleiotropy$pval > 0.05)
    dir_ok <- if (!is.null(results$directionality)) results$directionality$correct_causal_direction[1] else NA
    loo_ok <- length(influential) == 0

    outlier_ok <- is.null(results$outlier_snps) || nrow(results$outlier_snps) == 0
    presso_ok <- is.null(results$mr_presso)  # NULL means not run or no outliers

    cat("  Heterogeneity:  ", if (het_ok) "\u2713 No significant heterogeneity" else "\u26a0 Heterogeneity detected (consider MR-PRESSO)", "\n")
    cat("  Pleiotropy:     ", if (plei_ok) "\u2713 No directional pleiotropy" else "\u26a0 Directional pleiotropy detected", "\n")
    cat("  Directionality: ", if (is.na(dir_ok)) "\u2014 Could not test" else if (dir_ok) "\u2713 Correct causal direction" else "\u26a0 Incorrect direction", "")
    if (results$steiger_binary_warning) cat(" (binary outcome R\u00b2 may be inaccurate)")
    cat("\n")
    cat("  Leave-one-out:  ", if (loo_ok) "\u2713 Robust to individual SNP removal" else "\u26a0 Influential SNPs detected", "\n")
    cat("  Outlier SNPs:   ", if (outlier_ok) "\u2713 No discordant instruments" else paste0("\u26a0 ", nrow(results$outlier_snps), " discordant SNP(s) detected"), "\n")
    if (!is.null(results$mr_presso)) {
        global_p <- results$mr_presso$`MR-PRESSO results`$`Global Test`$Pvalue
        cat("  MR-PRESSO:      ", if (global_p < 0.05) "\u26a0 Outliers detected (see corrected estimate above)" else "\u2713 No significant outliers", "\n")
    }

    cat("\n✓ Sensitivity analyses completed successfully!\n")

    return(results)
}

