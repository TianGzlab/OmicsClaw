# RNA-seq Power Analysis
# Functions for calculating statistical power and required sample size for bulk RNA-seq experiments
# Based on: Hart et al. (2013) J Comput Biol 20(12):970-978

#' Calculate power for RNA-seq experiment
#'
#' @param depth Sequencing depth in millions of reads per sample
#' @param n_per_group Number of biological replicates per condition
#' @param cv Coefficient of variation (biological variability)
#' @param fold_change Minimum fold-change to detect
#' @param alpha Significance threshold (default: 0.05)
#' @return Power estimate (0-1)
#' @export
#' @examples
#' # Calculate power for 3 replicates per group
#' calc_power_rnaseq(depth = 20, n_per_group = 3, cv = 0.4, fold_change = 2)
calc_power_rnaseq <- function(depth,
                              n_per_group,
                              cv,
                              fold_change,
                              alpha = 0.05) {

  # Check inputs
  if (!requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Package 'RNASeqPower' is required. Install with BiocManager::install('RNASeqPower')")
  }

  if (depth <= 0 || n_per_group < 2 || cv <= 0 || fold_change <= 1) {
    stop("Invalid parameters: depth, n, and cv must be positive; fold_change must be >1; n must be >=2")
  }

  # Calculate power using RNASeqPower
  power <- RNASeqPower::rnapower(
    depth = depth,
    n = n_per_group,
    cv = cv,
    effect = fold_change,
    alpha = alpha
  )

  # Return formatted result
  result <- list(
    power = power,
    parameters = list(
      depth = depth,
      n_per_group = n_per_group,
      cv = cv,
      fold_change = fold_change,
      alpha = alpha
    ),
    interpretation = interpret_power(power)
  )

  cat("✓ Power analysis completed successfully!\n")
  cat(sprintf("  Power = %.3f for n=%d, FC=%.1f, CV=%.2f\n", power, n_per_group, fold_change, cv))

  return(result)
}


#' Calculate required sample size for target power
#'
#' @param depth Sequencing depth in millions of reads per sample
#' @param cv Coefficient of variation
#' @param fold_change Minimum fold-change to detect
#' @param target_power Target statistical power (default: 0.8)
#' @param alpha Significance threshold (default: 0.05)
#' @return Required sample size per group
#' @export
#' @examples
#' # Calculate required n for 80% power
#' calc_sample_size_rnaseq(depth = 20, cv = 0.4, fold_change = 2, target_power = 0.8)
calc_sample_size_rnaseq <- function(depth,
                                    cv,
                                    fold_change,
                                    target_power = 0.8,
                                    alpha = 0.05) {

  if (!requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Package 'RNASeqPower' is required. Install with BiocManager::install('RNASeqPower')")
  }

  if (depth <= 0 || cv <= 0 || fold_change <= 1 || target_power <= 0 || target_power >= 1) {
    stop("Invalid parameters: depth and cv must be positive; fold_change must be >1; power must be 0-1")
  }

  # Calculate required sample size
  required_n <- RNASeqPower::rnapower(
    depth = depth,
    cv = cv,
    effect = fold_change,
    alpha = alpha,
    power = target_power
  )

  # Round up to nearest integer
  required_n <- ceiling(required_n)

  # Return formatted result
  result <- list(
    required_n_per_group = required_n,
    parameters = list(
      depth = depth,
      cv = cv,
      fold_change = fold_change,
      target_power = target_power,
      alpha = alpha
    ),
    total_samples = required_n * 2,  # Assuming 2 conditions
    recommendation = recommend_sample_size(required_n, cv, fold_change)
  )

  cat("✓ Sample size calculation completed successfully!\n")
  cat(sprintf("  Required n = %d per group (%d total) for power=%.2f\n", required_n, required_n * 2, target_power))

  return(result)
}


#' Estimate CV from pilot data
#'
#' @param pilot_counts Matrix of raw counts from pilot data (genes x samples)
#' @return Estimated CV
#' @export
#' @examples
#' # Estimate CV from pilot count matrix
#' # pilot_counts <- read.csv("pilot_data.csv", row.names = 1)
#' # cv_estimate <- estimate_cv_from_pilot(pilot_counts)
estimate_cv_from_pilot <- function(pilot_counts) {

  if (!is.matrix(pilot_counts) && !is.data.frame(pilot_counts)) {
    stop("pilot_counts must be a matrix or data frame")
  }

  # Convert to matrix if data frame
  if (is.data.frame(pilot_counts)) {
    pilot_counts <- as.matrix(pilot_counts)
  }

  # Remove low count genes (mean < 10)
  mean_counts <- rowMeans(pilot_counts)
  pilot_counts <- pilot_counts[mean_counts >= 10, ]

  # Calculate CV for each gene
  gene_means <- rowMeans(pilot_counts)
  gene_sds <- apply(pilot_counts, 1, sd)
  gene_cvs <- gene_sds / gene_means

  # Return median CV
  estimated_cv <- median(gene_cvs, na.rm = TRUE)

  result <- list(
    estimated_cv = estimated_cv,
    cv_range = quantile(gene_cvs, probs = c(0.25, 0.75), na.rm = TRUE),
    n_genes_used = nrow(pilot_counts),
    recommendation = recommend_cv(estimated_cv)
  )

  return(result)
}


#' Interpret power value
#' @keywords internal
interpret_power <- function(power) {
  if (power >= 0.9) {
    return("Excellent: High power to detect effect")
  } else if (power >= 0.8) {
    return("Good: Adequate power for most applications")
  } else if (power >= 0.7) {
    return("Moderate: Consider increasing sample size")
  } else {
    return("Low: Increase sample size or relax effect size threshold")
  }
}


#' Recommend sample size based on parameters
#' @keywords internal
recommend_sample_size <- function(n, cv, fc) {
  recommendation <- paste0(
    "Recommended: ", n, " replicates per group (", n * 2, " total samples)\n",
    "For CV=", round(cv, 2), " and fold-change=", fc, "\n"
  )

  if (n < 3) {
    recommendation <- paste0(recommendation, "Warning: n<3 is generally too low for RNA-seq\n")
  }

  if (n > 20) {
    recommendation <- paste0(recommendation, "Note: Consider if this large n is feasible. Could you detect larger effects with fewer samples?\n")
  }

  return(recommendation)
}


#' Recommend CV interpretation
#' @keywords internal
recommend_cv <- function(cv) {
  if (cv < 0.2) {
    return("Low variability: Typical of cell lines or controlled conditions")
  } else if (cv < 0.3) {
    return("Moderate variability: Typical of inbred mice or primary cells")
  } else if (cv < 0.5) {
    return("High variability: Typical of human samples or outbred animals")
  } else {
    return("Very high variability: Consider if experimental variation can be reduced")
  }
}


#' Calculate power for range of parameters (for plotting)
#'
#' @param depth Sequencing depth
#' @param n_range Vector of sample sizes to test
#' @param cv Coefficient of variation
#' @param fold_change Fold-change threshold
#' @param alpha Significance threshold
#' @return Data frame with n and corresponding power
#' @export
calc_power_range <- function(depth, n_range, cv, fold_change, alpha = 0.05) {

  if (!requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Package 'RNASeqPower' is required.")
  }

  power_values <- sapply(n_range, function(n) {
    RNASeqPower::rnapower(
      depth = depth,
      n = n,
      cv = cv,
      effect = fold_change,
      alpha = alpha
    )
  })

  result <- data.frame(
    n_per_group = n_range,
    power = power_values,
    depth = depth,
    cv = cv,
    fold_change = fold_change
  )

  return(result)
}

