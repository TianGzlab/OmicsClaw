# =============================================================================
# Survival Analysis Workflow
# =============================================================================
# Core functions for Cox proportional hazards analysis, Kaplan-Meier estimation,
# risk stratification, and assumption testing.
#
# Usage:
#   source("scripts/basic_workflow.R")
#   result <- run_survival_analysis(data)
# =============================================================================

library(survival)

# =============================================================================
# Main Entry Point
# =============================================================================

run_survival_analysis <- function(data, covariates = NULL,
                                  risk_strata_col = NULL,
                                  risk_strata_method = "median") {
    cat("\n=== Running Survival Analysis ===\n\n")

    clinical <- data$clinical
    event_col <- data$event_col
    time_col <- data$time_col
    strata_col <- data$strata_col

    # --- Validate ---
    .validate_survival_data(clinical, event_col, time_col)

    # --- 1. Kaplan-Meier estimation (overall) ---
    cat("1. Kaplan-Meier estimation (overall)...\n")
    km_formula <- as.formula(paste0("Surv(", time_col, ", ", event_col, ") ~ 1"))
    km_overall <- survfit(km_formula, data = clinical)
    median_surv <- summary(km_overall)$table["median"]
    median_reliable <- .median_is_reliable(km_overall)

    # Landmark survival rates (robust even when median is unreliable)
    max_time <- max(clinical[[time_col]], na.rm = TRUE)
    landmark_times <- if (max_time > 3) c(1, 3, 5) else c(0.5, 1, 2)
    landmark_times <- landmark_times[landmark_times < max_time]
    landmark_surv <- .compute_landmark_survival(km_overall, landmark_times)

    # Median follow-up (reverse KM — standard method)
    median_followup <- .compute_median_followup(clinical, time_col, event_col)

    event_rate <- mean(clinical[[event_col]])
    n_censored <- sum(clinical[[event_col]] == 0)
    pct_censored <- round(100 * n_censored / nrow(clinical), 1)

    cat("   Events:", sum(clinical[[event_col]]), "/", nrow(clinical),
        "(", round(100 * event_rate, 1), "% event rate)\n")
    cat("   Censored:", n_censored, "/", nrow(clinical),
        "(", pct_censored, "%)\n")
    cat("   Median follow-up (reverse KM):", round(median_followup, 2), "years\n")

    # Heavy censoring warning — explains why KM curve may drop steeply in the tail
    if (event_rate < 0.20 && pct_censored > 80) {
        cat("\n   NOTE: HEAVY CENSORING DETECTED (", pct_censored,
            "% censored, ", round(100 * event_rate, 1), "% event rate)\n", sep = "")
        cat("   The KM curve may drop steeply in the tail despite a low overall event rate.\n")
        cat("   This is mathematically correct: as patients are censored, the at-risk set\n")
        cat("   shrinks, so each late event causes a larger survival drop. The tail of the\n")
        cat("   curve (where N at risk is small) is UNRELIABLE. Use landmark survival rates.\n")
    }

    if (median_reliable) {
        cat("   Median survival:", round(median_surv, 2), "years\n")
    } else {
        cat("   Median survival: NOT REACHED (KM curve does not cross 50%)\n")
    }

    # Always show landmark survival for transparency
    cat("   Landmark survival rates:\n")
    for (i in seq_len(nrow(landmark_surv))) {
        cat(sprintf("     %g-year OS: %.1f%% (95%% CI: %.1f%%-%.1f%%), n at risk: %d\n",
            landmark_surv$time[i],
            100 * landmark_surv$survival[i],
            100 * landmark_surv$lower_ci[i],
            100 * landmark_surv$upper_ci[i],
            landmark_surv$n_risk[i]))
    }
    cat("\n")

    # --- 2. Kaplan-Meier by strata ---
    km_strata <- NULL
    strata_logrank <- NULL
    if (!is.null(strata_col) && strata_col %in% colnames(clinical)) {
        cat("2. Kaplan-Meier by", strata_col, "...\n")
        # Remove NAs in strata
        strata_data <- clinical[!is.na(clinical[[strata_col]]), ]
        strata_formula <- as.formula(
            paste0("Surv(", time_col, ", ", event_col, ") ~ ", strata_col)
        )
        km_strata <- survfit(strata_formula, data = strata_data)
        strata_logrank <- survdiff(strata_formula, data = strata_data)
        logrank_p <- 1 - pchisq(strata_logrank$chisq, length(strata_logrank$n) - 1)
        cat("   Groups:", paste(names(strata_logrank$n), "=", strata_logrank$n,
            collapse = ", "), "\n")
        cat("   Log-rank chi-sq:", round(strata_logrank$chisq, 2),
            "df:", length(strata_logrank$n) - 1,
            "p:", format.pval(logrank_p, digits = 3), "\n")

        # Warn about unreliable per-stratum medians (upper CI = NA)
        strata_tbl <- summary(km_strata)$table
        if (is.matrix(strata_tbl)) {
            unreliable <- rownames(strata_tbl)[is.na(strata_tbl[, "0.95UCL"])]
            if (length(unreliable) > 0) {
                cat("   NOTE: Median survival NOT RELIABLY ESTIMABLE for:",
                    paste(sub(paste0("^", strata_col, "="), "", unreliable), collapse = ", "),
                    "\n")
                cat("   (Upper 95% CI = NA — KM curve does not cross 50% for these groups.\n")
                cat("    Reported medians are extrapolations. Use landmark rates instead.)\n")
            }
        }
        cat("\n")
    } else {
        cat("2. Skipping stratified KM (no strata column specified)\n\n")
    }

    # --- 3. Cox Proportional Hazards ---
    cat("3. Fitting Cox proportional hazards model...\n")

    # Missing covariate assessment BEFORE fitting
    # For any covariate with >5% missing, compare event rates between groups
    diagnostics <- list()
    missing_assessment <- list()
    exclude_cols <- c(event_col, time_col, "sample_id", "risk_group")
    all_candidates <- setdiff(colnames(clinical), exclude_cols)
    for (col in all_candidates) {
        pct_missing <- mean(is.na(clinical[[col]]))
        if (pct_missing > 0.05) {
            has_val <- !is.na(clinical[[col]])
            event_with <- mean(clinical[[event_col]][has_val])
            event_without <- mean(clinical[[event_col]][!has_val])
            n_missing <- sum(!has_val)
            # Fisher's exact test: is event rate different between groups?
            tbl <- table(
                group = ifelse(has_val, "non_missing", "missing"),
                event = clinical[[event_col]]
            )
            p <- tryCatch(fisher.test(tbl)$p.value, error = function(e) NA)
            informative <- !is.na(p) && p < 0.05
            missing_assessment[[col]] <- list(
                n_missing = n_missing,
                pct_missing = round(100 * pct_missing, 1),
                event_rate_missing = round(event_without, 3),
                event_rate_nonmissing = round(event_with, 3),
                fisher_p = p,
                informative = informative
            )
            if (informative) {
                cat("   WARNING: Potentially informative missingness in '", col,
                    "' (", n_missing, " missing, ", round(100*pct_missing,1),
                    "%): event rate ", round(100*event_without,1),
                    "% (missing) vs ", round(100*event_with,1),
                    "% (non-missing), Fisher p=", format.pval(p, digits=3),
                    "\n", sep = "")
            }
        }
    }
    diagnostics$missing_assessment <- missing_assessment

    # Update clinical with releveled factors from fit_cox_model
    cox_result <- fit_cox_model(clinical, event_col, time_col, covariates)
    # Apply releveled factors back to clinical for downstream use
    if (!is.null(cox_result$clinical_releveled)) clinical <- cox_result$clinical_releveled

    cat("   Concordance (C-index):", round(cox_result$concordance, 3), "\n")
    cat("   Significant covariates (p<0.05):",
        sum(cox_result$coefficients$pval < 0.05, na.rm = TRUE), "/",
        nrow(cox_result$coefficients), "\n")

    # Events per variable (EPV) — warn if underpowered
    n_params <- length(coef(cox_result$model))
    epv <- cox_result$nevent / n_params
    cat("   Events per variable (EPV):", round(epv, 1))
    if (epv < 10) {
        cat(" ** LOW (recommend >= 10; model may be overfitted)\n")
    } else {
        cat(" (adequate)\n")
    }

    # Excluded patients (missing covariates)
    n_in_model <- cox_result$n
    n_excluded <- nrow(clinical) - n_in_model
    if (n_excluded > 0) {
        cat("   Excluded from Cox model:", n_excluded, "/", nrow(clinical),
            "(", round(100 * n_excluded / nrow(clinical), 1),
            "%) due to missing covariates\n")
    }

    # Report dropped covariates
    if (length(cox_result$dropped_covariates) > 0) {
        cat("   Dropped covariates:\n")
        for (nm in names(cox_result$dropped_covariates)) {
            cat("     -", nm, ":", cox_result$dropped_covariates[[nm]], "\n")
        }
    }

    cat("\n")

    # Follow-up anomaly check
    max_obs_time <- max(clinical[[time_col]], na.rm = TRUE)
    followup_anomaly <- FALSE
    if (!is.na(median_followup) && median_followup < 2 && max_obs_time > 5) {
        followup_anomaly <- TRUE
        cat("   WARNING: Median follow-up (", round(median_followup, 2),
            " yr) is very short relative to max observation time (",
            round(max_obs_time, 1), " yr).\n", sep = "")
        cat("   This may indicate missing follow-up times for censored patients",
            " or a data freeze artifact.\n")
        cat("   Investigate days_to_last_followup completeness before",
            " interpreting survival estimates.\n\n")
    }
    diagnostics$followup_anomaly <- followup_anomaly
    diagnostics$max_obs_time <- max_obs_time

    # --- 4. Proportional hazards assumption test ---
    cat("4. Testing proportional hazards assumption...\n")
    ph_test <- test_assumptions(cox_result$model)
    global_p <- ph_test$table["GLOBAL", "p"]
    if (global_p < 0.05) {
        cat("   WARNING: Global PH test p =", format.pval(global_p, digits = 3),
            "- assumption may be violated\n")
        violated <- rownames(ph_test$table)[ph_test$table[, "p"] < 0.05]
        violated <- violated[violated != "GLOBAL"]
        if (length(violated) > 0) {
            cat("   Problematic covariates:", paste(violated, collapse = ", "), "\n")
        }
    } else {
        cat("   PH assumption satisfied (global p =",
            format.pval(global_p, digits = 3), ")\n")
    }
    cat("\n")

    # --- 5. Risk stratification ---
    cat("5. Creating risk groups...\n")
    risk_col <- risk_strata_col
    if (is.null(risk_col)) {
        # Use Cox linear predictor for risk stratification
        risk_groups <- stratify_risk_groups(
            cox_result$risk_scores,
            method = risk_strata_method
        )
        clinical$risk_group <- risk_groups
        risk_col <- "risk_group"
    }

    risk_data <- clinical[!is.na(clinical[[risk_col]]), ]
    risk_formula <- as.formula(
        paste0("Surv(", time_col, ", ", event_col, ") ~ ", risk_col)
    )
    km_risk <- survfit(risk_formula, data = risk_data)
    risk_logrank <- survdiff(risk_formula, data = risk_data)
    risk_p <- 1 - pchisq(risk_logrank$chisq, length(risk_logrank$n) - 1)
    cat("   Risk group log-rank chi-sq:", round(risk_logrank$chisq, 2),
        "df:", length(risk_logrank$n) - 1,
        "p:", format.pval(risk_p, digits = 3), "\n")

    tab <- table(clinical[[risk_col]])
    cat("   Groups:", paste(names(tab), "=", tab, collapse = ", "), "\n\n")

    # --- Assemble result ---
    result <- list(
        # KM estimates
        km_overall = km_overall,
        km_strata = km_strata,
        km_risk = km_risk,
        strata_logrank = strata_logrank,
        risk_logrank = risk_logrank,

        # Cox model
        cox = cox_result,
        ph_test = ph_test,

        # Data
        clinical = clinical,
        event_col = event_col,
        time_col = time_col,
        strata_col = strata_col,
        risk_col = risk_col,

        # Metadata
        dataset_name = data$dataset_name,
        description = data$description,
        report_context = data$report_context,
        n_total = nrow(clinical),
        n_events = sum(clinical[[event_col]]),
        median_survival = median_surv,
        concordance = cox_result$concordance,
        risk_strata_method = risk_strata_method,

        # Reliability metrics
        landmark_survival = landmark_surv,
        median_followup = median_followup,
        median_reliable = median_reliable,
        epv = epv,
        n_excluded = n_excluded,

        # Diagnostics (new)
        dropped_covariates = cox_result$dropped_covariates,
        reference_levels = cox_result$reference_levels,
        diagnostics = diagnostics
    )

    cat("✓ Survival analysis completed successfully!\n")
    cat("  C-index:", round(cox_result$concordance, 3), "\n")
    cat("  Events:", result$n_events, "/", result$n_total, "\n")
    if (median_reliable) {
        cat("  Median survival:", round(median_surv, 2), "years\n")
    } else {
        cat("  Median survival: Not reached\n")
        if (nrow(landmark_surv) > 0) {
            best <- landmark_surv[nrow(landmark_surv), ]
            cat(sprintf("  %g-year survival: %.1f%%\n",
                best$time, 100 * best$survival))
        }
    }

    return(result)
}


# =============================================================================
# Cox Proportional Hazards Model
# =============================================================================

fit_cox_model <- function(clinical, event_col, time_col, covariates = NULL) {
    dropped_covariates <- list()  # Track all dropped covariates with reasons

    # Auto-detect covariates if not specified
    if (is.null(covariates)) {
        exclude <- c(event_col, time_col, "sample_id", "risk_group")
        candidates <- setdiff(colnames(clinical), exclude)

        # Keep only variables with reasonable data (>80% non-missing, >1 unique value)
        # Also drop factor levels with <5 observations to avoid quasi-separation
        covariates <- c()
        for (col in candidates) {
            vals <- clinical[[col]]
            pct_non_na <- mean(!is.na(vals))
            n_unique <- length(unique(na.omit(vals)))
            if (pct_non_na >= 0.80 && n_unique > 1 && n_unique < nrow(clinical) * 0.9) {
                # For factors/characters: drop if any level has <5 observations
                if (is.factor(vals) || is.character(vals)) {
                    tab <- table(vals)
                    if (any(tab < 5)) {
                        cat("   Dropping", col, "- rare factor level(s):",
                            paste(names(tab[tab < 5]), collapse = ", "), "\n")
                        dropped_covariates[[col]] <- paste0(
                            "rare factor level(s): ",
                            paste(names(tab[tab < 5]), collapse = ", "))
                        next
                    }
                }
                covariates <- c(covariates, col)
            } else {
                reason <- c()
                if (pct_non_na < 0.80) reason <- c(reason,
                    paste0("too many missing (", round(100*(1-pct_non_na),1), "%)"))
                if (n_unique <= 1) reason <- c(reason, "only 1 unique value")
                if (n_unique >= nrow(clinical) * 0.9) reason <- c(reason, "near-unique (ID-like)")
                if (length(reason) > 0)
                    dropped_covariates[[col]] <- paste(reason, collapse = "; ")
            }
        }
    }

    if (length(covariates) == 0) {
        stop("No valid covariates found for Cox model. ",
             "Provide covariates explicitly or check data quality.")
    }

    # --- Collinearity check ---
    cat_covs <- covariates[sapply(covariates, function(col)
        is.factor(clinical[[col]]) || is.character(clinical[[col]]))]
    num_covs <- covariates[sapply(covariates, function(col)
        is.numeric(clinical[[col]]))]

    # 1. Derived-variable check: numeric + binned categorical (e.g., age → age_group)
    if (length(cat_covs) >= 1 && length(num_covs) >= 1) {
        for (nc in num_covs) {
            for (cc in cat_covs) {
                if (startsWith(cc, paste0(nc, "_")) || startsWith(cc, paste0(nc, "."))) {
                    cat("   Dropping", cc, "- derived from numeric", nc,
                        "(collinear)\n")
                    dropped_covariates[[cc]] <- paste0("collinear with numeric ", nc)
                    covariates <- setdiff(covariates, cc)
                    cat_covs <- setdiff(cat_covs, cc)
                }
            }
        }
    }

    # 2. Cramer's V for categorical pairs (V > 0.7 → drop the more specific one)
    if (length(cat_covs) >= 2) {
        for (i in seq_along(cat_covs)) {
            for (j in seq_len(i - 1)) {
                ci <- cat_covs[i]; cj <- cat_covs[j]
                if (!(ci %in% covariates) || !(cj %in% covariates)) next
                complete <- complete.cases(clinical[[ci]], clinical[[cj]])
                if (sum(complete) < 10) next
                tbl <- table(clinical[[ci]][complete], clinical[[cj]][complete])
                k <- min(nrow(tbl), ncol(tbl))
                if (k < 2) next  # Can't compute Cramer's V for 1xN tables
                n <- sum(tbl)
                chi2 <- suppressWarnings(chisq.test(tbl, correct = FALSE)$statistic)
                cramers_v <- sqrt(chi2 / (n * (k - 1)))
                if (cramers_v > 0.7) {
                    # Drop the one with more levels (less general)
                    ni <- nlevels(factor(clinical[[ci]]))
                    nj <- nlevels(factor(clinical[[cj]]))
                    to_drop <- if (ni >= nj) ci else cj
                    to_keep <- if (ni >= nj) cj else ci
                    cat("   Dropping", to_drop, "- collinear with", to_keep,
                        "(Cramer's V =", round(cramers_v, 2), ")\n")
                    dropped_covariates[[to_drop]] <- paste0(
                        "collinear with ", to_keep,
                        " (Cramer's V = ", round(cramers_v, 2), ")")
                    covariates <- setdiff(covariates, to_drop)
                }
            }
        }
    }

    if (length(covariates) == 0) {
        stop("All covariates were dropped. Check data quality or provide covariates.")
    }

    # --- Reference group releveling ---
    # Set reference level to largest group for each factor covariate
    reference_levels <- list()
    for (col in covariates) {
        vals <- clinical[[col]]
        if (is.factor(vals) || is.character(vals)) {
            clinical[[col]] <- factor(clinical[[col]])
            tab <- table(clinical[[col]])
            largest <- names(which.max(tab))
            clinical[[col]] <- relevel(clinical[[col]], ref = largest)
            reference_levels[[col]] <- list(
                reference = largest, n = as.integer(tab[largest]))
            if (tab[largest] < 50) {
                cat("   WARNING: Reference group for", col, "is '", largest,
                    "' (N=", tab[largest],
                    ") — small reference may produce unstable HRs\n", sep = "")
            }
        }
    }

    cat("   Covariates in model:", paste(covariates, collapse = ", "), "\n")

    # Build formula
    formula_str <- paste0("Surv(", time_col, ", ", event_col, ") ~ ",
                          paste(covariates, collapse = " + "))
    cox_formula <- as.formula(formula_str)

    # Fit model (na.action = na.exclude to preserve alignment)
    model <- tryCatch(
        coxph(cox_formula, data = clinical, na.action = na.exclude),
        error = function(e) {
            cat("   Cox model failed with all covariates, trying stepwise...\n")
            # Try each covariate individually, keep those that work
            good_covs <- c()
            for (cov in covariates) {
                f <- as.formula(paste0("Surv(", time_col, ", ", event_col,
                                       ") ~ ", cov))
                m <- tryCatch(coxph(f, data = clinical, na.action = na.exclude),
                             error = function(e2) NULL)
                if (!is.null(m)) good_covs <- c(good_covs, cov)
            }
            if (length(good_covs) == 0) stop("No covariates could be fit.")
            f2 <- as.formula(paste0("Surv(", time_col, ", ", event_col,
                                    ") ~ ", paste(good_covs, collapse = " + ")))
            coxph(f2, data = clinical, na.action = na.exclude)
        }
    )

    # Extract coefficients
    smry <- summary(model)
    coef_df <- data.frame(
        variable = rownames(smry$coefficients),
        coefficient = smry$coefficients[, "coef"],
        hazard_ratio = smry$coefficients[, "exp(coef)"],
        se = smry$coefficients[, "se(coef)"],
        hr_lower = smry$conf.int[, "lower .95"],
        hr_upper = smry$conf.int[, "upper .95"],
        z = smry$coefficients[, "z"],
        pval = smry$coefficients[, "Pr(>|z|)"],
        stringsAsFactors = FALSE,
        row.names = NULL
    )

    # Risk scores (use model's internal data to avoid new-factor-level errors)
    risk_scores <- predict(model, type = "risk")

    list(
        model = model,
        coefficients = coef_df,
        risk_scores = risk_scores,
        concordance = smry$concordance[1],
        formula = formula_str,
        n = model$n,
        nevent = model$nevent,
        dropped_covariates = dropped_covariates,
        reference_levels = reference_levels,
        clinical_releveled = clinical
    )
}


# =============================================================================
# Proportional Hazards Assumption Test
# =============================================================================

test_assumptions <- function(cox_model) {
    ph_test <- cox.zph(cox_model)
    return(ph_test)
}


# =============================================================================
# Risk Stratification
# =============================================================================

stratify_risk_groups <- function(risk_scores, method = "median",
                                 n_groups = NULL, cutpoints = NULL) {
    if (method == "median") {
        med <- median(risk_scores, na.rm = TRUE)
        groups <- ifelse(risk_scores > med, "High Risk", "Low Risk")
    } else if (method == "tertiles") {
        q <- quantile(risk_scores, probs = c(1/3, 2/3), na.rm = TRUE)
        groups <- ifelse(risk_scores <= q[1], "Low Risk",
                  ifelse(risk_scores <= q[2], "Medium Risk", "High Risk"))
    } else if (method == "quartiles") {
        q <- quantile(risk_scores, probs = c(0.25, 0.5, 0.75), na.rm = TRUE)
        groups <- ifelse(risk_scores <= q[1], "Q1 (Lowest)",
                  ifelse(risk_scores <= q[2], "Q2",
                  ifelse(risk_scores <= q[3], "Q3", "Q4 (Highest)")))
    } else if (method == "custom" && !is.null(cutpoints)) {
        groups <- cut(risk_scores, breaks = c(-Inf, cutpoints, Inf),
                     labels = paste0("Group ", seq_along(cutpoints) + 1))
    } else {
        stop("Unknown risk stratification method: ", method)
    }

    return(groups)
}


# =============================================================================
# Validation
# =============================================================================

# =============================================================================
# Landmark Survival & Reliability Helpers
# =============================================================================

#' Compute landmark survival rates at specified timepoints
.compute_landmark_survival <- function(km_fit, times = c(1, 3, 5)) {
    s <- summary(km_fit, times = times, extend = TRUE)
    data.frame(
        time = s$time,
        survival = round(s$surv, 4),
        lower_ci = round(s$lower, 4),
        upper_ci = round(s$upper, 4),
        n_risk = s$n.risk,
        stringsAsFactors = FALSE
    )
}

#' Compute median follow-up via reverse Kaplan-Meier
#' (standard method: swap events and censoring, then estimate median)
.compute_median_followup <- function(clinical, time_col, event_col) {
    reverse_event <- 1 - clinical[[event_col]]
    f <- Surv(clinical[[time_col]], reverse_event)
    fit <- survfit(f ~ 1)
    median_fu <- summary(fit)$table["median"]
    return(median_fu)
}

#' Check if KM median survival is reliably estimable
#' Requires: (1) upper 95% CI is not NA (curve crosses 50%), AND
#'           (2) at least 20 patients at risk at the median time
.median_is_reliable <- function(km_fit) {
    tbl <- summary(km_fit)$table
    ucl <- tbl["0.95UCL"]
    if (is.na(ucl)) return(FALSE)

    # Also check N at risk at the median time
    median_time <- tbl["median"]
    if (is.na(median_time)) return(FALSE)

    idx <- which.min(abs(km_fit$time - median_time))
    n_at_risk <- km_fit$n.risk[idx]

    # Need >= 20 patients at risk for a reliable estimate
    return(n_at_risk >= 20)
}


.validate_survival_data <- function(clinical, event_col, time_col) {
    # Check required columns exist
    if (!event_col %in% colnames(clinical))
        stop("Event column '", event_col, "' not found in data.")
    if (!time_col %in% colnames(clinical))
        stop("Time column '", time_col, "' not found in data.")

    # Check data types
    if (!is.numeric(clinical[[time_col]]))
        stop("Time column '", time_col, "' must be numeric.")
    if (!all(clinical[[event_col]] %in% c(0, 1), na.rm = TRUE))
        stop("Event column '", event_col, "' must be binary (0/1). Found: ",
             paste(unique(clinical[[event_col]]), collapse = ", "))

    # Check for negatives
    if (any(clinical[[time_col]] < 0, na.rm = TRUE))
        warning("Negative survival times detected. Check time column encoding.")

    # Check for sufficient events
    n_events <- sum(clinical[[event_col]], na.rm = TRUE)
    if (n_events < 5)
        warning("Only ", n_events, " events detected. Results may be unreliable.")
    if (n_events == nrow(clinical))
        warning("All observations are events (no censoring). Check event coding.")

    cat("  Data validated:", nrow(clinical), "patients,", n_events, "events\n")
}

