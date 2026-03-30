# Multiple Testing Correction Methods
# Functions for applying various multiple testing correction approaches

#' Apply Benjamini-Hochberg FDR correction (standard method)
#'
#' @param pvalues Vector of p-values
#' @param q_threshold FDR threshold (default: 0.05)
#' @return List with adjusted p-values and significant results
#' @export
#' @examples
#' # pvalues <- c(0.001, 0.01, 0.05, 0.1, 0.5)
#' # bh_results <- apply_bh_fdr(pvalues, q_threshold = 0.05)
apply_bh_fdr <- function(pvalues, q_threshold = 0.05) {

  # Remove NAs
  valid_idx <- !is.na(pvalues)
  valid_pvalues <- pvalues[valid_idx]

  # Apply BH correction
  adjusted_p <- p.adjust(valid_pvalues, method = "BH")

  # Determine significance
  is_significant <- adjusted_p < q_threshold

  # Create result vector with NAs in original positions
  full_adjusted_p <- rep(NA, length(pvalues))
  full_adjusted_p[valid_idx] <- adjusted_p

  full_is_sig <- rep(NA, length(pvalues))
  full_is_sig[valid_idx] <- is_significant

  result <- list(
    method = "Benjamini-Hochberg FDR",
    adjusted_pvalues = full_adjusted_p,
    is_significant = full_is_sig,
    n_significant = sum(is_significant, na.rm = TRUE),
    n_tested = sum(valid_idx),
    threshold = q_threshold,
    interpretation = interpret_bh_results(sum(is_significant, na.rm = TRUE), sum(valid_idx), q_threshold)
  )

  return(result)
}


#' Apply Bonferroni correction (most stringent)
#'
#' @param pvalues Vector of p-values
#' @param alpha Significance threshold (default: 0.05)
#' @return List with adjusted p-values and significant results
#' @export
apply_bonferroni <- function(pvalues, alpha = 0.05) {

  valid_idx <- !is.na(pvalues)
  valid_pvalues <- pvalues[valid_idx]

  # Apply Bonferroni correction
  adjusted_p <- p.adjust(valid_pvalues, method = "bonferroni")

  # Determine significance
  is_significant <- adjusted_p < alpha

  # Create full result vectors
  full_adjusted_p <- rep(NA, length(pvalues))
  full_adjusted_p[valid_idx] <- adjusted_p

  full_is_sig <- rep(NA, length(pvalues))
  full_is_sig[valid_idx] <- is_significant

  # Bonferroni threshold
  bonf_threshold <- alpha / sum(valid_idx)

  result <- list(
    method = "Bonferroni",
    adjusted_pvalues = full_adjusted_p,
    is_significant = full_is_sig,
    n_significant = sum(is_significant, na.rm = TRUE),
    n_tested = sum(valid_idx),
    threshold = alpha,
    bonferroni_threshold = bonf_threshold,
    interpretation = interpret_bonf_results(sum(is_significant, na.rm = TRUE), bonf_threshold)
  )

  return(result)
}


#' Apply q-value method (provides gene-specific FDR)
#'
#' @param pvalues Vector of p-values
#' @param fdr_threshold FDR threshold (default: 0.05)
#' @return List with q-values and significant results
#' @export
apply_qvalue <- function(pvalues, fdr_threshold = 0.05) {

  if (!requireNamespace("qvalue", quietly = TRUE)) {
    stop("Package 'qvalue' is required. Install with BiocManager::install('qvalue')")
  }

  # Remove NAs
  valid_idx <- !is.na(pvalues)
  valid_pvalues <- pvalues[valid_idx]

  # Calculate q-values
  qobj <- qvalue::qvalue(valid_pvalues)

  # Get q-values and significance
  qvalues <- qobj$qvalues
  is_significant <- qvalues < fdr_threshold

  # Create full result vectors
  full_qvalues <- rep(NA, length(pvalues))
  full_qvalues[valid_idx] <- qvalues

  full_is_sig <- rep(NA, length(pvalues))
  full_is_sig[valid_idx] <- is_significant

  # Estimate pi0 (proportion of true nulls)
  pi0 <- qobj$pi0

  result <- list(
    method = "Q-value",
    qvalues = full_qvalues,
    is_significant = full_is_sig,
    n_significant = sum(is_significant, na.rm = TRUE),
    n_tested = sum(valid_idx),
    threshold = fdr_threshold,
    pi0 = pi0,
    estimated_true_positives = round((1 - pi0) * sum(valid_idx)),
    interpretation = interpret_qvalue_results(sum(is_significant, na.rm = TRUE), pi0, sum(valid_idx))
  )

  return(result)
}


#' Apply Independent Hypothesis Weighting (IHW) - more powerful than BH
#'
#' @param pvalues Vector of p-values
#' @param covariates Vector of independent covariates (e.g., mean expression)
#' @param alpha Significance threshold (default: 0.05)
#' @return List with adjusted p-values and significant results
#' @export
#' @examples
#' # Requires covariate (e.g., mean expression level)
#' # ihw_results <- apply_ihw(pvalues, covariates = mean_expression, alpha = 0.05)
apply_ihw <- function(pvalues, covariates, alpha = 0.05) {

  if (!requireNamespace("IHW", quietly = TRUE)) {
    stop("Package 'IHW' is required. Install with BiocManager::install('IHW')")
  }

  # Remove NAs
  valid_idx <- !is.na(pvalues) & !is.na(covariates)
  valid_pvalues <- pvalues[valid_idx]
  valid_covariates <- covariates[valid_idx]

  # Apply IHW
  ihw_res <- IHW::ihw(valid_pvalues, valid_covariates, alpha = alpha)

  # Get adjusted p-values and rejections
  adjusted_p <- IHW::adj_pvalues(ihw_res)
  rejections <- IHW::rejections(ihw_res)

  # Create full result vectors
  full_adjusted_p <- rep(NA, length(pvalues))
  full_adjusted_p[valid_idx] <- adjusted_p

  full_is_sig <- rep(NA, length(pvalues))
  full_is_sig[valid_idx] <- rejections

  # Compare to BH-FDR
  bh_rejections <- sum(p.adjust(valid_pvalues, method = "BH") < alpha)
  additional_discoveries <- sum(rejections) - bh_rejections

  result <- list(
    method = "Independent Hypothesis Weighting (IHW)",
    adjusted_pvalues = full_adjusted_p,
    is_significant = full_is_sig,
    n_significant = sum(rejections),
    n_tested = sum(valid_idx),
    threshold = alpha,
    bh_rejections = bh_rejections,
    additional_discoveries = additional_discoveries,
    interpretation = interpret_ihw_results(sum(rejections), bh_rejections, additional_discoveries)
  )

  return(result)
}


#' Recommend multiple testing method based on experiment characteristics
#'
#' @param n_tests Number of statistical tests
#' @param expected_true_positives Estimated number of true effects (optional)
#' @param effect_heterogeneity Are effect sizes heterogeneous? ("low", "moderate", "high")
#' @param sample_size Sample size per group
#' @return Recommended method with justification
#' @export
recommend_method <- function(n_tests,
                             expected_true_positives = NULL,
                             effect_heterogeneity = "moderate",
                             sample_size = NULL) {

  # Decision tree for method selection

  # Very small number of tests
  if (n_tests < 100) {
    method <- "Bonferroni"
    justification <- paste0(
      "Bonferroni recommended for small number of tests (n=", n_tests, ").\n",
      "This provides strong family-wise error control.\n",
      "Use threshold: p < ", format(0.05 / n_tests, scientific = TRUE)
    )
  }

  # GWAS-scale tests
  else if (n_tests > 500000) {
    method <- "Bonferroni"
    justification <- paste0(
      "Bonferroni recommended for GWAS (n=", format(n_tests, big.mark = ","), " tests).\n",
      "Standard GWAS threshold: p < 5×10⁻⁸\n"
    )
  }

  # Standard genomics with heterogeneous effects and covariate available
  else if (effect_heterogeneity == "high" && n_tests > 5000) {
    method <- "IHW (Independent Hypothesis Weighting)"
    justification <- paste0(
      "IHW recommended for heterogeneous effect sizes (n=", format(n_tests, big.mark = ","), " tests).\n",
      "IHW typically identifies 10-20% more discoveries than BH-FDR.\n",
      "Requires independent covariate (e.g., mean expression level).\n",
      "If covariate unavailable, use BH-FDR instead.\n"
    )
  }

  # Many expected true positives
  else if (!is.null(expected_true_positives) && expected_true_positives > n_tests * 0.05) {
    method <- "Q-value"
    justification <- paste0(
      "Q-value recommended when many true positives expected (", expected_true_positives, " of ", n_tests, ").\n",
      "Q-value provides gene-specific FDR estimates and is more powerful than BH when pi0 < 0.9.\n"
    )
  }

  # Small sample size
  else if (!is.null(sample_size) && sample_size < 6) {
    method <- "Permutation-based FDR"
    justification <- paste0(
      "Permutation-based FDR recommended for small sample size (n=", sample_size, ").\n",
      "Parametric assumptions may be violated with small n.\n",
      "Use permutation tests to empirically estimate null distribution.\n"
    )
  }

  # Default: BH-FDR
  else {
    method <- "Benjamini-Hochberg FDR"
    justification <- paste0(
      "BH-FDR recommended (standard genomics choice, n=", format(n_tests, big.mark = ","), " tests).\n",
      "Use threshold: FDR < 0.05\n",
      "This is the most widely used and accepted method for genomics studies.\n"
    )
  }

  result <- list(
    recommended_method = method,
    justification = justification,
    parameters = list(
      n_tests = n_tests,
      expected_true_positives = expected_true_positives,
      effect_heterogeneity = effect_heterogeneity,
      sample_size = sample_size
    )
  )

  # Print recommendation
  cat("\n=== Multiple Testing Method Recommendation ===\n")
  cat("Recommended method:", method, "\n\n")
  cat(justification, "\n")

  return(result)
}


#' Compare multiple correction methods on same data
#'
#' @param pvalues Vector of p-values
#' @param covariates Optional covariates for IHW
#' @param threshold Significance threshold (default: 0.05)
#' @return Data frame comparing methods
#' @export
compare_methods <- function(pvalues, covariates = NULL, threshold = 0.05) {

  # Apply all methods
  bh_res <- apply_bh_fdr(pvalues, threshold)
  bonf_res <- apply_bonferroni(pvalues, threshold)

  # Try qvalue
  qval_res <- tryCatch({
    apply_qvalue(pvalues, threshold)
  }, error = function(e) {
    NULL
  })

  # Try IHW if covariates provided
  ihw_res <- NULL
  if (!is.null(covariates)) {
    ihw_res <- tryCatch({
      apply_ihw(pvalues, covariates, threshold)
    }, error = function(e) {
      NULL
    })
  }

  # Create comparison table
  comparison <- data.frame(
    Method = c("Benjamini-Hochberg", "Bonferroni"),
    Significant = c(bh_res$n_significant, bonf_res$n_significant),
    Tested = c(bh_res$n_tested, bonf_res$n_tested),
    Proportion = c(
      bh_res$n_significant / bh_res$n_tested,
      bonf_res$n_significant / bonf_res$n_tested
    ),
    stringsAsFactors = FALSE
  )

  if (!is.null(qval_res)) {
    comparison <- rbind(comparison, data.frame(
      Method = "Q-value",
      Significant = qval_res$n_significant,
      Tested = qval_res$n_tested,
      Proportion = qval_res$n_significant / qval_res$n_tested,
      stringsAsFactors = FALSE
    ))
  }

  if (!is.null(ihw_res)) {
    comparison <- rbind(comparison, data.frame(
      Method = "IHW",
      Significant = ihw_res$n_significant,
      Tested = ihw_res$n_tested,
      Proportion = ihw_res$n_significant / ihw_res$n_tested,
      stringsAsFactors = FALSE
    ))
  }

  # Format proportion as percentage
  comparison$Percent <- sprintf("%.2f%%", comparison$Proportion * 100)

  # Print comparison
  cat("\n=== Multiple Testing Method Comparison ===\n")
  print(comparison[, c("Method", "Significant", "Tested", "Percent")])

  return(comparison)
}


#' Interpret BH-FDR results
#' @keywords internal
interpret_bh_results <- function(n_sig, n_tested, threshold) {
  prop_sig <- n_sig / n_tested
  interpretation <- paste0(
    "BH-FDR results: ", n_sig, " of ", n_tested, " tests significant (FDR < ", threshold, ")\n",
    "Proportion significant: ", sprintf("%.2f%%", prop_sig * 100), "\n",
    "Expected false positives: ~", round(n_sig * threshold), "\n"
  )
  return(interpretation)
}


#' Interpret Bonferroni results
#' @keywords internal
interpret_bonf_results <- function(n_sig, threshold) {
  interpretation <- paste0(
    "Bonferroni results: ", n_sig, " significant (p < ", format(threshold, scientific = TRUE), ")\n",
    "Family-wise error rate controlled at 0.05\n"
  )
  return(interpretation)
}


#' Interpret q-value results
#' @keywords internal
interpret_qvalue_results <- function(n_sig, pi0, n_tested) {
  prop_true_null <- pi0
  estimated_true_pos <- round((1 - pi0) * n_tested)

  interpretation <- paste0(
    "Q-value results: ", n_sig, " significant\n",
    "Estimated proportion of true nulls (pi0): ", sprintf("%.2f", pi0), "\n",
    "Estimated true positives among all tests: ", estimated_true_pos, " (", sprintf("%.1f%%", (1-pi0)*100), ")\n"
  )
  return(interpretation)
}


#' Interpret IHW results
#' @keywords internal
interpret_ihw_results <- function(n_sig, bh_sig, additional) {
  if (additional > 0) {
    perc_gain <- (additional / bh_sig) * 100
    interpretation <- paste0(
      "IHW results: ", n_sig, " significant\n",
      "BH-FDR would find: ", bh_sig, " significant\n",
      "Additional discoveries with IHW: ", additional, " (+", sprintf("%.1f%%", perc_gain), ")\n",
      "IHW provides more power by weighting hypotheses based on covariates.\n"
    )
  } else {
    interpretation <- paste0(
      "IHW results: ", n_sig, " significant\n",
      "Similar to BH-FDR (", bh_sig, " significant)\n",
      "Covariate may not be highly informative for weighting.\n"
    )
  }
  return(interpretation)
}

