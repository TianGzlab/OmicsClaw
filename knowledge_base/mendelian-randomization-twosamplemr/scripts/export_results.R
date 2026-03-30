# =============================================================================
# Mendelian Randomization - Export Results
# =============================================================================
# Functions:
#   export_all()  - Export all MR results, sensitivity analyses, RDS object, and PDF report
# =============================================================================

#' Export all MR analysis results
#'
#' Saves:
#'   1. mr_results.csv - Primary MR estimates (all methods)
#'   2. heterogeneity_results.csv - Cochran's Q test results
#'   3. pleiotropy_results.csv - MR-Egger intercept test
#'   4. directionality_results.csv - Steiger directionality test
#'   5. harmonized_data.csv - SNP-level harmonized data
#'   6. single_snp_results.csv - Per-SNP Wald ratio estimates
#'   7. leaveoneout_results.csv - Leave-one-out estimates
#'   8. mr_object.rds - Complete analysis object for downstream use
#'   9. mr_report.pdf - Structured analysis report (auto-generated)
#'
#' @param mr_results MR results from run_mr()
#' @param sensitivity_results Sensitivity list from run_sensitivity()
#' @param dat Harmonized data from load_data.R
#' @param output_dir Directory for saving results (default: "mr_results")
export_all <- function(mr_results, sensitivity_results, dat,
                        output_dir = "mr_results") {
    cat("\n=== Exporting MR Results ===\n\n")

    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
    }

    file_count <- 0

    # 1. Primary MR results
    cat("1. MR results (all methods)...\n")
    write.csv(mr_results, file.path(output_dir, "mr_results.csv"), row.names = FALSE)
    cat("   Saved: mr_results.csv\n")
    file_count <- file_count + 1

    # 2. Heterogeneity results
    cat("2. Heterogeneity test results...\n")
    write.csv(sensitivity_results$heterogeneity,
              file.path(output_dir, "heterogeneity_results.csv"), row.names = FALSE)
    cat("   Saved: heterogeneity_results.csv\n")
    file_count <- file_count + 1

    # 3. Pleiotropy results
    cat("3. Pleiotropy test results...\n")
    write.csv(sensitivity_results$pleiotropy,
              file.path(output_dir, "pleiotropy_results.csv"), row.names = FALSE)
    cat("   Saved: pleiotropy_results.csv\n")
    file_count <- file_count + 1

    # 4. Directionality results
    cat("4. Directionality test results...\n")
    if (!is.null(sensitivity_results$directionality)) {
        write.csv(sensitivity_results$directionality,
                  file.path(output_dir, "directionality_results.csv"), row.names = FALSE)
        cat("   Saved: directionality_results.csv\n")
        file_count <- file_count + 1
    } else {
        cat("   Skipped (directionality test was not available)\n")
    }

    # 5. Harmonized data
    cat("5. Harmonized SNP-level data...\n")
    write.csv(dat, file.path(output_dir, "harmonized_data.csv"), row.names = FALSE)
    cat("   Saved: harmonized_data.csv\n")
    file_count <- file_count + 1

    # 6. Single-SNP results
    cat("6. Single-SNP Wald ratio results...\n")
    write.csv(sensitivity_results$singlesnp,
              file.path(output_dir, "single_snp_results.csv"), row.names = FALSE)
    cat("   Saved: single_snp_results.csv\n")
    file_count <- file_count + 1

    # 7. Leave-one-out results
    cat("7. Leave-one-out results...\n")
    write.csv(sensitivity_results$leaveoneout,
              file.path(output_dir, "leaveoneout_results.csv"), row.names = FALSE)
    cat("   Saved: leaveoneout_results.csv\n")
    file_count <- file_count + 1

    # 8. Complete analysis object (RDS)
    cat("8. Complete analysis object (RDS)...\n")
    mr_object <- list(
        mr_results = mr_results,
        sensitivity = sensitivity_results,
        harmonized_data = dat,
        metadata = list(
            date = Sys.time(),
            exposure = unique(dat$exposure),
            outcome = unique(dat$outcome),
            n_instruments = nrow(dat),
            methods = mr_results$method,
            r_version = R.version.string,
            twosamplemr_version = as.character(packageVersion("TwoSampleMR"))
        )
    )
    saveRDS(mr_object, file.path(output_dir, "mr_object.rds"))
    cat("   Saved: mr_object.rds\n")
    cat("   (Load with: mr_obj <- readRDS('mr_results/mr_object.rds'))\n")
    file_count <- file_count + 1

    # 9. Generate analysis report (PDF)
    cat("9. Generating analysis report...\n")
    tryCatch({
        source("scripts/generate_report.R")
        generate_report(mr_results, sensitivity_results, dat, output_dir)
        file_count <- file_count + 1
    }, error = function(e) {
        cat("   Warning: Report generation failed (", conditionMessage(e), ")\n")
        cat("   All other exports completed successfully.\n")
    })

    # Summary
    cat("\n  Files saved to:", output_dir, "/\n")
    cat("  Total files:", file_count, "\n")

    cat("\n=== Export Complete ===\n")
}

