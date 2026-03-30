# =============================================================================
# Export Survival Analysis Results
# =============================================================================
# Exports all results: CSVs, RDS objects, summary tables, and PDF report.
#
# Usage:
#   source("scripts/export_results.R")
#   export_all(result, output_dir = "results")
# =============================================================================

export_all <- function(result, output_dir = "results") {
    cat("\n=== Exporting Survival Analysis Results ===\n\n")

    if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

    # --- 1. Cox model coefficients ---
    cat("1. Cox model coefficients...\n")
    coef_out <- result$cox$coefficients
    # Remove reference level rows (NA coefficients) for clean output
    coef_out <- coef_out[!is.na(coef_out$pval), ]
    write.csv(coef_out,
              file.path(output_dir, "cox_coefficients.csv"),
              row.names = FALSE)
    cat("   Saved: cox_coefficients.csv\n\n")

    # --- 2. Patient risk scores ---
    cat("2. Patient risk scores...\n")
    scores_df <- data.frame(
        sample_id = result$clinical$sample_id,
        risk_score = result$cox$risk_scores,
        risk_group = result$clinical[[result$risk_col]],
        stringsAsFactors = FALSE
    )
    write.csv(scores_df, file.path(output_dir, "risk_scores.csv"),
              row.names = FALSE)
    cat("   Saved: risk_scores.csv\n\n")

    # --- 3. Clinical data with risk groups ---
    cat("3. Annotated clinical data...\n")
    write.csv(result$clinical,
              file.path(output_dir, "clinical_annotated.csv"),
              row.names = FALSE)
    cat("   Saved: clinical_annotated.csv\n\n")

    # --- 4. Survival summary table ---
    cat("4. Survival summary statistics...\n")
    summary_df <- .build_summary_table(result)
    write.csv(summary_df, file.path(output_dir, "survival_summary.csv"),
              row.names = FALSE)
    cat("   Saved: survival_summary.csv\n\n")

    # --- 5. PH assumption test ---
    cat("5. Proportional hazards test results...\n")
    ph_df <- data.frame(
        variable = rownames(result$ph_test$table),
        chisq = result$ph_test$table[, "chisq"],
        df = result$ph_test$table[, "df"],
        p = result$ph_test$table[, "p"],
        stringsAsFactors = FALSE,
        row.names = NULL
    )
    write.csv(ph_df, file.path(output_dir, "ph_assumption_test.csv"),
              row.names = FALSE)
    cat("   Saved: ph_assumption_test.csv\n\n")

    # --- 6. Analysis object (RDS) - CRITICAL for downstream skills ---
    cat("6. Saving analysis object (RDS)...\n")
    saveRDS(result, file.path(output_dir, "survival_model.rds"))
    cat("   Saved: survival_model.rds\n")
    cat("   (Load with: model <- readRDS('results/survival_model.rds'))\n\n")

    # --- 7. Markdown report ---
    cat("7. Generating markdown report...\n")
    md_content <- .build_markdown_report(result)
    writeLines(md_content, file.path(output_dir, "survival_report.md"))
    cat("   Saved: survival_report.md\n\n")

    cat("\n=== Export Complete ===\n")
    cat("\nFiles in", output_dir, ":\n")
    files <- list.files(output_dir, recursive = FALSE)
    for (f in files) {
        size <- file.info(file.path(output_dir, f))$size
        cat("  ", f, "(", .format_size(size), ")\n")
    }
}


# =============================================================================
# Helpers
# =============================================================================

.build_summary_table <- function(result) {
    clinical <- result$clinical
    risk_col <- result$risk_col
    time_col <- result$time_col
    event_col <- result$event_col

    groups <- unique(clinical[[risk_col]])
    groups <- groups[!is.na(groups)]

    rows <- lapply(groups, function(g) {
        subset <- clinical[clinical[[risk_col]] == g & !is.na(clinical[[risk_col]]), ]
        f <- as.formula(paste0("Surv(", time_col, ", ", event_col, ") ~ 1"))
        fit <- survival::survfit(f, data = subset)
        tbl <- summary(fit)$table
        median_surv <- tbl["median"]
        lcl <- tbl["0.95LCL"]
        ucl <- tbl["0.95UCL"]
        median_reliable <- !is.na(ucl)

        data.frame(
            group = g,
            n = nrow(subset),
            events = sum(subset[[event_col]], na.rm = TRUE),
            event_rate = round(mean(subset[[event_col]], na.rm = TRUE), 3),
            median_survival = if (median_reliable) round(median_surv, 2) else NA_real_,
            median_lower_ci = round(lcl, 2),
            median_upper_ci = round(ucl, 2),
            median_reliable = median_reliable,
            stringsAsFactors = FALSE
        )
    })

    do.call(rbind, rows)
}

.build_markdown_report <- function(result) {
    ctx <- result$report_context
    coef <- result$cox$coefficients
    # Filter out NA rows (reference factor levels)
    coef <- coef[!is.na(coef$pval), ]
    median_reliable <- isTRUE(result$median_reliable)

    lines <- c(
        paste("#", result$dataset_name, "- Survival Analysis Report"),
        "",
        paste("**Date:**", Sys.Date()),
        paste("**Samples:**", result$n_total),
        paste("**Events:**", result$n_events, "(",
              round(100 * result$n_events / result$n_total, 1), "%)"),
        paste("**Concordance (C-index):**", round(result$concordance, 3)),
        if (median_reliable)
            paste("**Median survival:**", round(result$median_survival, 2), "years")
        else
            "**Median survival:** Not reached (KM curve does not cross 50%)",
        if (!is.null(result$median_followup) && !is.na(result$median_followup))
            paste("**Median follow-up (reverse KM):**",
                  round(result$median_followup, 2), "years")
        else NULL,
        if (!is.null(result$epv))
            paste("**Events per variable (EPV):**", round(result$epv, 1),
                  if (result$epv < 10) "**(low — model may be overfitted)**" else "(adequate)")
        else NULL,
        if (!is.null(result$n_excluded) && result$n_excluded > 0)
            paste("**Excluded from Cox model:**", result$n_excluded,
                  "(", round(100 * result$n_excluded / result$n_total, 1),
                  "%) due to missing covariates")
        else NULL,
        ""
    )

    # Add landmark survival table
    if (!is.null(result$landmark_survival)) {
        ls <- result$landmark_survival
        lines <- c(lines,
            "### Landmark Survival Rates",
            "",
            "| Timepoint | Survival | 95% CI | N at Risk |",
            "|-----------|----------|--------|----------|"
        )
        for (i in seq_len(nrow(ls))) {
            lines <- c(lines, sprintf("| %g-year | %.1f%% | %.1f%%-%.1f%% | %d |",
                ls$time[i], 100 * ls$survival[i],
                100 * ls$lower_ci[i], 100 * ls$upper_ci[i], ls$n_risk[i]))
        }
        lines <- c(lines, "")
    }

    lines <- c(lines,
        "## Methods",
        "",
        paste("- **Disease:**", ctx$disease %||% "Not specified"),
        paste("- **Data source:**", ctx$source %||% "Not specified"),
        paste("- **Endpoint:**", ctx$endpoints %||% "Overall survival"),
        paste("- **Cox model covariates:**",
              paste(names(coef(result$cox$model)), collapse = ", ")),
        paste("- **Risk stratification:**", result$risk_strata_method, "split")
    )

    # Report dropped covariates
    if (length(result$dropped_covariates) > 0) {
        lines <- c(lines,
            paste("- **Dropped covariates:**",
                  paste(names(result$dropped_covariates), collapse = ", ")))
        for (nm in names(result$dropped_covariates)) {
            lines <- c(lines, paste("  -", nm, ":", result$dropped_covariates[[nm]]))
        }
    }

    # Report reference levels
    if (length(result$reference_levels) > 0) {
        ref_strs <- vapply(names(result$reference_levels), function(nm) {
            rl <- result$reference_levels[[nm]]
            paste0(nm, " = ", rl$reference, " (N=", rl$n, ")")
        }, character(1))
        lines <- c(lines,
            paste("- **Reference groups:**", paste(ref_strs, collapse = "; ")))
    }

    # Report informative missingness
    if (!is.null(result$diagnostics$missing_assessment)) {
        informative <- Filter(function(x) isTRUE(x$informative),
                              result$diagnostics$missing_assessment)
        if (length(informative) > 0) {
            lines <- c(lines,
                "- **⚠️ Informative missingness detected:**")
            for (nm in names(informative)) {
                ma <- informative[[nm]]
                lines <- c(lines, sprintf(
                    "  - %s: %d missing (%.1f%%), event rate %.1f%% (missing) vs %.1f%% (non-missing), Fisher p=%s",
                    nm, ma$n_missing, ma$pct_missing,
                    100 * ma$event_rate_missing, 100 * ma$event_rate_nonmissing,
                    format.pval(ma$fisher_p, digits = 3)))
            }
        }
    }

    # Report follow-up anomaly
    if (isTRUE(result$diagnostics$followup_anomaly)) {
        lines <- c(lines, paste0(
            "- **⚠️ Follow-up anomaly:** Median follow-up (",
            round(result$median_followup, 2),
            " yr) is very short relative to max observation time (",
            round(result$diagnostics$max_obs_time, 1),
            " yr). May indicate missing follow-up data for censored patients."))
    }

    lines <- c(lines, "",
        "## Cox Proportional Hazards Results",
        "",
        "| Variable | HR | 95% CI | p-value |",
        "|----------|---:|-------:|--------:|"
    )

    for (i in seq_len(nrow(coef))) {
        lines <- c(lines, paste0(
            "| ", coef$variable[i],
            " | ", sprintf("%.2f", coef$hazard_ratio[i]),
            " | ", sprintf("%.2f", coef$hr_lower[i]),
            "-", sprintf("%.2f", coef$hr_upper[i]),
            " | ", format.pval(coef$pval[i], digits = 3), " |"
        ))
    }

    lines <- c(lines, "",
        "## Proportional Hazards Assumption",
        "")

    global_p <- result$ph_test$table["GLOBAL", "p"]
    if (global_p < 0.05) {
        lines <- c(lines,
            paste("**WARNING:** Global PH test p =", format.pval(global_p, digits = 3),
                  "- proportional hazards assumption may be violated."),
            "Consider time-varying coefficients or stratified Cox model.")
    } else {
        lines <- c(lines,
            paste("PH assumption satisfied (global p =",
                  format.pval(global_p, digits = 3), ")"))
    }

    lines <- c(lines, "",
        "## Generated Files",
        "",
        "| File | Description |",
        "|------|------------|",
        "| cox_coefficients.csv | Hazard ratios with CIs and p-values |",
        "| risk_scores.csv | Patient risk scores and group assignments |",
        "| clinical_annotated.csv | Full clinical data with risk groups |",
        "| survival_summary.csv | Summary statistics by risk group |",
        "| ph_assumption_test.csv | Schoenfeld residual test results |",
        "| survival_model.rds | Complete analysis object for downstream use |",
        "| km_overall.png/svg | Overall Kaplan-Meier survival curve |",
        "| km_stratified.png/svg | Stratified survival curves |",
        "| forest_plot.png/svg | Forest plot of hazard ratios |",
        "| km_risk_groups.png/svg | Risk group survival curves |",
        "| schoenfeld_diagnostics.png/svg | PH assumption diagnostic plots |",
        "| cumulative_hazard.png/svg | Cumulative hazard plot |",
        "",
        "## Citation",
        "",
        paste("- **Data:**", ctx$citation %||% "User-provided data"),
        "- **Methods:** Cox PH (survival R package), KM estimation (survminer)",
        "- **Visualization:** ggplot2 + ggprism theme"
    )

    paste(lines, collapse = "\n")
}

.format_size <- function(bytes) {
    if (is.na(bytes)) return("?")
    if (bytes < 1024) return(paste(bytes, "B"))
    if (bytes < 1024^2) return(paste(round(bytes / 1024, 1), "KB"))
    return(paste(round(bytes / 1024^2, 1), "MB"))
}

# Null-coalescing operator
`%||%` <- function(x, y) if (is.null(x)) y else x

