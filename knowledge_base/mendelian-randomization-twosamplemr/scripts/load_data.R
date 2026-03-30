# =============================================================================
# Mendelian Randomization - Data Loading & Harmonization
# =============================================================================
# Three entry points:
#   load_example_data()       - LDL Cholesterol → CHD demo (OpenGWAS)
#   load_from_opengwas()      - Any exposure/outcome by OpenGWAS ID
#   load_from_files()         - User-provided GWAS summary statistics
# =============================================================================

# --- Package setup -----------------------------------------------------------

.ensure_packages <- function() {
    options(repos = c(CRAN = "https://cloud.r-project.org"))

    if (!requireNamespace("remotes", quietly = TRUE)) {
        install.packages("remotes")
    }

    if (!requireNamespace("TwoSampleMR", quietly = TRUE)) {
        cat("Installing TwoSampleMR from GitHub (~2 min)...\n")
        remotes::install_github("MRCIEU/TwoSampleMR", upgrade = "never")
    }

    if (!requireNamespace("ieugwasr", quietly = TRUE)) {
        install.packages("ieugwasr")
    }

    suppressPackageStartupMessages({
        library(TwoSampleMR)
        library(ieugwasr)
        library(dplyr)
    })
}

# --- OpenGWAS data loading ---------------------------------------------------

#' Load exposure and outcome data from OpenGWAS and harmonize
#'
#' @param exposure_id OpenGWAS ID for exposure (e.g., "ieu-a-300" for LDL cholesterol)
#' @param outcome_id OpenGWAS ID for outcome (e.g., "ieu-a-7" for CHD)
#' @param p_threshold P-value threshold for instrument selection (default: 5e-8)
#' @param clump_r2 LD clumping r-squared threshold (default: 0.001)
#' @param clump_kb LD clumping window in kb (default: 10000)
#' @return Harmonized data frame ready for MR analysis
load_from_opengwas <- function(exposure_id, outcome_id,
                                p_threshold = 5e-8,
                                clump_r2 = 0.001,
                                clump_kb = 10000) {
    .ensure_packages()

    cat("\n=== Loading MR Data from OpenGWAS ===\n")
    cat("  Exposure:", exposure_id, "\n")
    cat("  Outcome: ", outcome_id, "\n\n")

    # Step 1: Extract instruments for exposure
    cat("Step 1/4: Extracting genome-wide significant instruments (p <", p_threshold, ")...\n")
    exposure_dat <- extract_instruments(
        outcomes = exposure_id,
        p1 = p_threshold,
        clump = TRUE,
        r2 = clump_r2,
        kb = clump_kb
    )

    if (is.null(exposure_dat) || nrow(exposure_dat) == 0) {
        stop("No instruments found for exposure '", exposure_id,
             "'. Check the ID or try a less stringent p-value threshold.")
    }
    cat("  Found", nrow(exposure_dat), "instruments after LD clumping\n\n")

    # Step 2: Extract outcome data for these SNPs
    cat("Step 2/4: Extracting outcome data for instruments...\n")
    outcome_dat <- extract_outcome_data(
        snps = exposure_dat$SNP,
        outcomes = outcome_id
    )

    if (is.null(outcome_dat) || nrow(outcome_dat) == 0) {
        stop("No outcome data found for '", outcome_id,
             "'. Check the ID or ensure SNPs are available in the outcome GWAS.")
    }
    cat("  Found outcome data for", nrow(outcome_dat), "SNPs\n\n")

    # Step 3: Harmonize
    cat("Step 3/4: Harmonizing exposure and outcome data...\n")
    dat <- harmonise_data(
        exposure_dat = exposure_dat,
        outcome_dat = outcome_dat,
        action = 2
    )
    dat <- dat[dat$mr_keep, ]
    cat("  Retained", nrow(dat), "SNPs after harmonization\n\n")

    if (nrow(dat) < 3) {
        stop("Only ", nrow(dat), " SNPs retained after harmonization. ",
             "Need at least 3 for MR-Egger. Consider relaxing parameters.")
    }

    # Step 4: Summary
    cat("Step 4/4: Summary\n")
    cat("  Exposure: ", unique(dat$exposure), "\n")
    cat("  Outcome:  ", unique(dat$outcome), "\n")
    cat("  Instruments: ", nrow(dat), " SNPs\n")

    cat("\n✓ Data loaded and harmonized successfully! (",
        nrow(dat), " instruments after harmonization)\n", sep = "")

    return(dat)
}

# --- User file loading -------------------------------------------------------

#' Load exposure and outcome data from user-provided files
#'
#' @param exposure_file Path to exposure GWAS summary statistics (CSV/TSV)
#' @param outcome_file Path to outcome GWAS summary statistics (CSV/TSV)
#' @param exposure_name Name for the exposure trait
#' @param outcome_name Name for the outcome trait
#' @param sep Column separator ("," for CSV, "\t" for TSV, "auto" to detect)
#' @param snp_col Column name for SNP rsIDs
#' @param beta_col Column name for effect estimates
#' @param se_col Column name for standard errors
#' @param pval_col Column name for p-values
#' @param effect_allele_col Column name for effect allele
#' @param other_allele_col Column name for other allele
#' @param eaf_col Column name for effect allele frequency (optional)
#' @param p_threshold P-value threshold for instrument selection
#' @param clump_r2 LD clumping r-squared threshold
#' @param clump_kb LD clumping window in kb
#' @return Harmonized data frame ready for MR analysis
load_from_files <- function(exposure_file, outcome_file,
                             exposure_name = "Exposure",
                             outcome_name = "Outcome",
                             sep = "auto",
                             snp_col = "SNP",
                             beta_col = "beta",
                             se_col = "se",
                             pval_col = "pval",
                             effect_allele_col = "effect_allele",
                             other_allele_col = "other_allele",
                             eaf_col = "eaf",
                             p_threshold = 5e-8,
                             clump_r2 = 0.001,
                             clump_kb = 10000) {
    .ensure_packages()

    cat("\n=== Loading MR Data from Files ===\n")
    cat("  Exposure file:", exposure_file, "\n")
    cat("  Outcome file: ", outcome_file, "\n\n")

    # Auto-detect separator
    if (sep == "auto") {
        first_line <- readLines(exposure_file, n = 2)[2]
        sep <- if (grepl("\t", first_line)) "\t" else ","
        cat("  Auto-detected separator:", ifelse(sep == "\t", "TAB", "COMMA"), "\n")
    }

    # Read exposure data
    cat("Step 1/4: Reading exposure data...\n")
    exp_raw <- read.csv(exposure_file, sep = sep, stringsAsFactors = FALSE)

    # Validate required columns
    required_cols <- c(snp_col, beta_col, se_col, pval_col, effect_allele_col, other_allele_col)
    missing_cols <- setdiff(required_cols, names(exp_raw))
    if (length(missing_cols) > 0) {
        stop("Missing required columns in exposure file: ",
             paste(missing_cols, collapse = ", "),
             "\n  Available columns: ", paste(names(exp_raw), collapse = ", "),
             "\n  Use the column name parameters (snp_col, beta_col, etc.) to map your columns.")
    }

    # Format exposure data for TwoSampleMR
    exposure_dat <- format_data(
        exp_raw,
        type = "exposure",
        snp_col = snp_col,
        beta_col = beta_col,
        se_col = se_col,
        pval_col = pval_col,
        effect_allele_col = effect_allele_col,
        other_allele_col = other_allele_col,
        eaf_col = if (eaf_col %in% names(exp_raw)) eaf_col else NULL,
        phenotype_col = NULL
    )
    exposure_dat$exposure <- exposure_name
    cat("  Read", nrow(exposure_dat), "variants from exposure file\n")

    # Filter by p-value threshold
    exposure_dat <- exposure_dat[exposure_dat$pval.exposure < p_threshold, ]
    cat("  ", nrow(exposure_dat), "variants below p <", p_threshold, "\n")

    if (nrow(exposure_dat) == 0) {
        stop("No variants below p-value threshold ", p_threshold,
             ". Try a less stringent threshold.")
    }

    # LD clump
    cat("\nStep 2/4: LD clumping (r² <", clump_r2, ", window", clump_kb, "kb)...\n")
    exposure_dat <- tryCatch({
        clump_data(exposure_dat, clump_r2 = clump_r2, clump_kb = clump_kb)
    }, error = function(e) {
        cat("  Warning: LD clumping via API failed (", conditionMessage(e), ").\n")
        cat("  Proceeding without LD clumping - results may be affected by LD.\n")
        exposure_dat
    })
    cat("  ", nrow(exposure_dat), "instruments after clumping\n")

    # Read outcome data
    cat("\nStep 3/4: Reading outcome data...\n")
    out_raw <- read.csv(outcome_file, sep = sep, stringsAsFactors = FALSE)

    missing_cols_out <- setdiff(required_cols, names(out_raw))
    if (length(missing_cols_out) > 0) {
        stop("Missing required columns in outcome file: ",
             paste(missing_cols_out, collapse = ", "))
    }

    outcome_dat <- format_data(
        out_raw,
        type = "outcome",
        snp_col = snp_col,
        beta_col = beta_col,
        se_col = se_col,
        pval_col = pval_col,
        effect_allele_col = effect_allele_col,
        other_allele_col = other_allele_col,
        eaf_col = if (eaf_col %in% names(out_raw)) eaf_col else NULL,
        phenotype_col = NULL
    )
    outcome_dat$outcome <- outcome_name

    # Filter outcome to only include exposure instruments
    outcome_dat <- outcome_dat[outcome_dat$SNP %in% exposure_dat$SNP, ]
    cat("  Matched", nrow(outcome_dat), "of", nrow(exposure_dat), "instruments in outcome data\n")

    # Harmonize
    cat("\nStep 4/4: Harmonizing exposure and outcome data...\n")
    dat <- harmonise_data(
        exposure_dat = exposure_dat,
        outcome_dat = outcome_dat,
        action = 2
    )
    dat <- dat[dat$mr_keep, ]
    cat("  Retained", nrow(dat), "SNPs after harmonization\n")

    if (nrow(dat) < 3) {
        stop("Only ", nrow(dat), " SNPs retained after harmonization. ",
             "Need at least 3 for MR-Egger.")
    }

    cat("\n✓ Data loaded and harmonized successfully! (",
        nrow(dat), " instruments after harmonization)\n", sep = "")

    return(dat)
}

# --- Example data loader -----------------------------------------------------

#' Load example data: LDL Cholesterol → Coronary Heart Disease
#'
#' Uses OpenGWAS IDs:
#'   Exposure: ieu-a-300 (LDL cholesterol, Willer et al. 2013 GLGC)
#'   Outcome: ieu-a-7 (CHD, CARDIoGRAMplusC4D)
#'
#' @return Harmonized data frame ready for MR analysis
load_example_data <- function() {
    cat("\n========================================\n")
    cat("  MR Example: LDL Cholesterol → Coronary Heart Disease\n")
    cat("========================================\n")
    cat("  Exposure: LDL cholesterol (ieu-a-300, GLGC 2013)\n")
    cat("  Outcome:  CHD (ieu-a-7, CARDIoGRAMplusC4D)\n")
    cat("  Expected: Positive causal effect of LDL on CHD risk\n")
    cat("========================================\n\n")

    dat <- load_from_opengwas(
        exposure_id = "ieu-a-300",
        outcome_id = "ieu-a-7"
    )

    return(dat)
}

