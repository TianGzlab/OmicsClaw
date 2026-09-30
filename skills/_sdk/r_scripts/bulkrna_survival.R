#!/usr/bin/env Rscript
# OmicsClaw: Survival analysis via R survival package
#
# Usage:
#   Rscript bulkrna_survival.R <expr_csv> <clinical_csv> <output_dir> <genes> [cutoff_method]
#
# expr_csv: genes as rows, samples as columns (first column = gene names)
# clinical_csv: must have columns: sample, time, event
# genes: comma-separated gene names
# cutoff_method: "median" (default) or "optimal"

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 4) {
    cat("Usage: Rscript bulkrna_survival.R <expr.csv> <clinical.csv> <output_dir> <genes> [cutoff_method]\n")
    quit(status = 1)
}

expr_file      <- args[1]
clinical_file  <- args[2]
output_dir     <- args[3]
gene_list      <- strsplit(args[4], ",")[[1]]
cutoff_method  <- if (length(args) >= 5) args[5] else "median"

suppressPackageStartupMessages({
    library(survival)
})

if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

tryCatch({
    cat("Loading expression data...\n")
    expr <- read.csv(expr_file, row.names = 1, check.names = FALSE)
    clinical <- read.csv(clinical_file, check.names = FALSE)

    # Match samples — clinical$sample should match colnames of expr
    # If no 'sample' column, use first column or rownames
    if (!"sample" %in% colnames(clinical)) {
        if (nrow(clinical) == ncol(expr)) {
            clinical$sample <- colnames(expr)
        } else {
            clinical$sample <- clinical[, 1]
        }
    }

    common_samples <- intersect(colnames(expr), as.character(clinical$sample))
    if (length(common_samples) == 0) stop("No matching samples between expression and clinical data")

    expr <- expr[, common_samples, drop = FALSE]
    clinical <- clinical[match(common_samples, clinical$sample), ]
    rownames(clinical) <- clinical$sample

    cat(sprintf("  %d genes x %d samples, %d events\n",
        nrow(expr), ncol(expr), sum(clinical$event)))

    # Censoring rate check
    censor_rate <- 1 - mean(clinical$event)
    if (censor_rate > 0.8) {
        cat(sprintf("  WARNING: Heavy censoring (%.0f%%). KM tail estimates may be unreliable.\n",
            censor_rate * 100))
    }

    # EPV check
    n_events <- sum(clinical$event)
    n_genes_test <- length(gene_list)
    epv <- n_events / n_genes_test
    if (n_genes_test > 1 && epv < 10) {
        cat(sprintf("  WARNING: EPV=%.1f (<10). Multi-gene model may be overfitted.\n", epv))
    }

    results <- data.frame()
    km_curves <- data.frame()

    for (gene in gene_list) {
        if (!gene %in% rownames(expr)) {
            cat(sprintf("  Skipping %s: not found in expression matrix\n", gene))
            next
        }

        expression <- as.numeric(expr[gene, ])

        # Determine cutoff
        if (cutoff_method == "optimal") {
            sorted_expr <- sort(unique(expression))
            best_chi2 <- 0
            best_cut <- median(expression)
            for (cut in sorted_expr[2:(length(sorted_expr)-1)]) {
                high <- expression >= cut
                if (sum(high) < 5 || sum(!high) < 5) next
                fit <- survdiff(Surv(clinical$time, clinical$event) ~ high)
                if (fit$chisq > best_chi2) {
                    best_chi2 <- fit$chisq
                    best_cut <- cut
                }
            }
            cutoff <- best_cut
        } else {
            cutoff <- median(expression)
        }

        high_mask <- expression >= cutoff
        group <- ifelse(high_mask, "high", "low")
        n_high <- sum(high_mask)
        n_low <- sum(!high_mask)

        if (n_high < 2 || n_low < 2) {
            cat(sprintf("  Skipping %s: insufficient samples (high=%d, low=%d)\n", gene, n_high, n_low))
            next
        }

        # Log-rank test
        sdf <- survdiff(Surv(clinical$time, clinical$event) ~ group)
        chi2 <- sdf$chisq
        pval <- 1 - pchisq(chi2, df = 1)

        # KM curves
        km_high <- survfit(Surv(clinical$time[high_mask], clinical$event[high_mask]) ~ 1)
        km_low  <- survfit(Surv(clinical$time[!high_mask], clinical$event[!high_mask]) ~ 1)

        # Median survival with reliability check
        med_high <- summary(km_high)$table["median"]
        med_low  <- summary(km_low)$table["median"]
        med_high_note <- if (is.na(med_high)) "Not reached" else "Reached"
        med_low_note  <- if (is.na(med_low))  "Not reached" else "Reached"

        # Cox PH for hazard ratio
        cox_fit <- coxph(Surv(clinical$time, clinical$event) ~ high_mask)
        cox_summary <- summary(cox_fit)
        hr <- cox_summary$conf.int[1, 1]  # exp(coef)
        hr_lower <- cox_summary$conf.int[1, 3]
        hr_upper <- cox_summary$conf.int[1, 4]
        cox_pval <- cox_summary$coefficients[1, 5]

        # Landmark survival (auto-select time points)
        max_time <- max(clinical$time)
        if (max_time > 60) {
            landmarks <- c(12, 36, 60)
        } else if (max_time > 24) {
            landmarks <- c(6, 12, 24)
        } else {
            landmarks <- c(max_time * 0.25, max_time * 0.5, max_time * 0.75)
        }

        landmark_data <- list()
        for (t in landmarks) {
            s_high <- summary(km_high, times = t, extend = TRUE)
            s_low  <- summary(km_low,  times = t, extend = TRUE)
            landmark_data[[as.character(round(t, 1))]] <- list(
                high_surv = s_high$surv,
                low_surv  = s_low$surv
            )
        }

        # Store results
        result_row <- data.frame(
            gene = gene,
            cutoff = round(cutoff, 4),
            n_high = n_high,
            n_low = n_low,
            log_rank_chi2 = round(chi2, 4),
            log_rank_pval = pval,
            median_high = if (is.na(med_high)) NA else round(med_high, 2),
            median_low = if (is.na(med_low)) NA else round(med_low, 2),
            median_high_note = med_high_note,
            median_low_note = med_low_note,
            hr = round(hr, 4),
            hr_lower = round(hr_lower, 4),
            hr_upper = round(hr_upper, 4),
            cox_pval = cox_pval,
            stringsAsFactors = FALSE
        )
        results <- rbind(results, result_row)

        # Store KM curve data for Python plotting
        for (grp_name in c("high", "low")) {
            km_obj <- if (grp_name == "high") km_high else km_low
            km_df <- data.frame(
                gene = gene,
                group = grp_name,
                time = c(0, km_obj$time),
                surv = c(1, km_obj$surv),
                stringsAsFactors = FALSE
            )
            km_curves <- rbind(km_curves, km_df)
        }

        cat(sprintf("  %s: HR=%.2f [%.2f-%.2f], log-rank p=%.4e\n",
            gene, hr, hr_lower, hr_upper, pval))
    }

    # Write outputs
    write.csv(results, file.path(output_dir, "survival_results.csv"), row.names = FALSE, quote = FALSE)
    write.csv(km_curves, file.path(output_dir, "km_data.csv"), row.names = FALSE, quote = FALSE)

    cat(sprintf("Done. Analyzed %d genes.\n", nrow(results)))

}, error = function(e) {
    cat(sprintf("ERROR: %s\n", e$message), file = stderr())
    quit(status = 1)
})
