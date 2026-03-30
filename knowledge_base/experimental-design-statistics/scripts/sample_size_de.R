# Sample Size Estimation for Differential Expression
# Functions for determining required sample size for DE studies

#' Calculate required sample size for differential expression
#'
#' @param pi0 Proportion of non-differentially expressed genes (e.g., 0.9 = 90% non-DE)
#' @param m1 Expected number of differentially expressed genes
#' @param fold_change Minimum fold-change to detect
#' @param fdr Target false discovery rate threshold (default: 0.05)
#' @param power Target statistical power (default: 0.8)
#' @param mean_count Mean read count per gene (default: 20)
#' @param dispersion Dispersion parameter (default: 0.1)
#' @return Required sample size per group
#' @export
#' @examples
#' # Calculate required n for detecting 2000 DE genes with 1.5-fold change
#' calc_samplesize_de(pi0 = 0.9, m1 = 2000, fold_change = 1.5, power = 0.8)
calc_samplesize_de <- function(pi0 = 0.9,
                               m1 = 2000,
                               fold_change = 1.5,
                               fdr = 0.05,
                               power = 0.8,
                               mean_count = 20,
                               dispersion = 0.1) {

  if (!requireNamespace("ssizeRNA", quietly = TRUE)) {
    stop("Package 'ssizeRNA' is required. Install with BiocManager::install('ssizeRNA')")
  }

  # Validate inputs
  if (pi0 <= 0 || pi0 >= 1) {
    stop("pi0 must be between 0 and 1")
  }

  if (m1 <= 0 || fold_change <= 1 || power <= 0 || power >= 1) {
    stop("Invalid parameters: m1 must be positive, fold_change > 1, power must be 0-1")
  }

  # Calculate total number of genes
  m <- ceiling(m1 / (1 - pi0))

  # Use ssizeRNA to calculate required sample size
  result <- ssizeRNA::ssizeRNA_vary(
    nGenes = m,
    pi0 = pi0,
    m = NULL,  # Calculate required m (sample size)
    mu = mean_count,
    disp = dispersion,
    fc = fold_change,
    fdr = fdr,
    power = power
  )

  required_n <- ceiling(result$m)

  output <- list(
    required_n_per_group = required_n,
    total_samples = required_n * 2,
    parameters = list(
      total_genes = m,
      de_genes = m1,
      pi0 = pi0,
      fold_change = fold_change,
      fdr = fdr,
      target_power = power,
      mean_count = mean_count,
      dispersion = dispersion
    ),
    recommendation = recommend_sample_size_de(required_n, fold_change)
  )

  cat("✓ Sample size estimation completed successfully!\n")
  cat(sprintf("  Required n = %d per group (%d total samples)\n", required_n, required_n * 2))
  cat(sprintf("  For detecting %d DE genes at FC=%.1f\n", m1, fold_change))

  return(output)
}


#' Calculate sample size from pilot DESeq2 data
#'
#' @param pilot_dds DESeq2 object with pilot data
#' @param fold_change Minimum fold-change to detect
#' @param power Target power (default: 0.8)
#' @param fdr Target FDR (default: 0.05)
#' @param expected_de_prop Expected proportion of DE genes (default: 0.1)
#' @return Required sample size per group
#' @export
#' @examples
#' # library(DESeq2)
#' # pilot_dds <- readRDS("pilot_data.rds")
#' # required_n <- samplesize_from_pilot(pilot_dds, fold_change = 1.5, power = 0.8)
samplesize_from_pilot <- function(pilot_dds,
                                  fold_change,
                                  power = 0.8,
                                  fdr = 0.05,
                                  expected_de_prop = 0.1) {

  if (!requireNamespace("DESeq2", quietly = TRUE) || !requireNamespace("ssizeRNA", quietly = TRUE)) {
    stop("Packages 'DESeq2' and 'ssizeRNA' are required.")
  }

  # Extract parameters from pilot data
  if (is.null(DESeq2::dispersions(pilot_dds))) {
    pilot_dds <- DESeq2::estimateSizeFactors(pilot_dds)
    pilot_dds <- DESeq2::estimateDispersions(pilot_dds)
  }

  # Get median dispersion and mean count
  median_disp <- median(DESeq2::dispersions(pilot_dds), na.rm = TRUE)
  counts <- DESeq2::counts(pilot_dds, normalized = TRUE)
  mean_count <- mean(rowMeans(counts))

  # Calculate pi0
  pi0 <- 1 - expected_de_prop

  # Number of genes
  n_genes <- nrow(pilot_dds)
  m1 <- ceiling(n_genes * expected_de_prop)

  # Calculate required sample size
  result <- ssizeRNA::ssizeRNA_vary(
    nGenes = n_genes,
    pi0 = pi0,
    m = NULL,
    mu = mean_count,
    disp = median_disp,
    fc = fold_change,
    fdr = fdr,
    power = power
  )

  required_n <- ceiling(result$m)

  output <- list(
    required_n_per_group = required_n,
    total_samples = required_n * 2,
    pilot_parameters = list(
      median_dispersion = median_disp,
      mean_count = mean_count,
      n_genes = n_genes,
      expected_de_genes = m1
    ),
    parameters = list(
      fold_change = fold_change,
      power = power,
      fdr = fdr
    ),
    recommendation = recommend_from_pilot_de(required_n, median_disp, fold_change)
  )

  cat("✓ Sample size estimation from pilot data completed successfully!\n")
  cat(sprintf("  Required n = %d per group based on pilot dispersion=%.3f\n", required_n, median_disp))

  return(output)
}


#' Calculate sample size for paired design
#'
#' @param pilot_dds DESeq2 object with pilot paired data (design must include pairing factor)
#' @param fold_change Minimum fold-change to detect
#' @param power Target power (default: 0.8)
#' @param fdr Target FDR (default: 0.05)
#' @return Required number of pairs
#' @export
paired_samplesize <- function(pilot_dds,
                              fold_change,
                              power = 0.8,
                              fdr = 0.05) {

  if (!requireNamespace("DESeq2", quietly = TRUE)) {
    stop("Package 'DESeq2' is required.")
  }

  # For paired designs, variance is typically reduced
  # Extract parameters similarly but account for pairing effect

  if (is.null(DESeq2::dispersions(pilot_dds))) {
    pilot_dds <- DESeq2::estimateSizeFactors(pilot_dds)
    pilot_dds <- DESeq2::estimateDispersions(pilot_dds)
  }

  median_disp <- median(DESeq2::dispersions(pilot_dds), na.rm = TRUE)

  # Paired designs typically have 20-40% lower variance
  # Adjust dispersion accordingly
  adjusted_disp <- median_disp * 0.7  # Conservative 30% reduction

  counts <- DESeq2::counts(pilot_dds, normalized = TRUE)
  mean_count <- mean(rowMeans(counts))
  n_genes <- nrow(pilot_dds)

  # Use adjusted parameters for sample size calculation
  result <- ssizeRNA::ssizeRNA_vary(
    nGenes = n_genes,
    pi0 = 0.9,
    m = NULL,
    mu = mean_count,
    disp = adjusted_disp,
    fc = fold_change,
    fdr = fdr,
    power = power
  )

  required_pairs <- ceiling(result$m)

  output <- list(
    required_pairs = required_pairs,
    total_samples = required_pairs * 2,  # Before and after for each pair
    pilot_parameters = list(
      median_dispersion = median_disp,
      adjusted_dispersion = adjusted_disp,
      mean_count = mean_count,
      n_genes = n_genes
    ),
    parameters = list(
      fold_change = fold_change,
      power = power,
      fdr = fdr
    ),
    note = "Paired design: Required number is pairs (not independent samples)",
    recommendation = recommend_paired_design(required_pairs, fold_change)
  )

  return(output)
}


#' Quick reference table for sample sizes by effect size
#'
#' @param cv Coefficient of variation (default: 0.4 for human samples)
#' @return Data frame with effect sizes and corresponding sample sizes
#' @export
quick_reference_samplesize <- function(cv = 0.4) {

  effect_sizes <- c(1.25, 1.5, 2, 3, 4)
  sample_sizes <- numeric(length(effect_sizes))

  if (!requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Package 'RNASeqPower' is required.")
  }

  for (i in seq_along(effect_sizes)) {
    sample_sizes[i] <- ceiling(RNASeqPower::rnapower(
      depth = 20,
      cv = cv,
      effect = effect_sizes[i],
      alpha = 0.05,
      power = 0.8
    ))
  }

  result <- data.frame(
    fold_change = effect_sizes,
    required_n_per_group = sample_sizes,
    total_samples = sample_sizes * 2,
    difficulty = c("Very challenging", "Challenging", "Moderate", "Easy", "Very easy")
  )

  return(result)
}


#' Recommend sample size for DE
#' @keywords internal
recommend_sample_size_de <- function(n, fc) {
  recommendation <- paste0(
    "Recommended: ", n, " replicates per group (", n * 2, " total samples)\n",
    "For fold-change = ", fc, "\n"
  )

  if (n < 3) {
    recommendation <- paste0(recommendation, "Warning: Minimum 3 replicates recommended for RNA-seq\n")
  } else if (n >= 3 && n <= 6) {
    recommendation <- paste0(recommendation, "Good: This is a standard RNA-seq design\n")
  } else if (n > 12) {
    recommendation <- paste0(recommendation, "Large n required. Consider if budget allows, or detect larger effects.\n")
  }

  return(recommendation)
}


#' Recommend based on pilot data
#' @keywords internal
recommend_from_pilot_de <- function(n, disp, fc) {
  recommendation <- paste0(
    "Based on pilot data:\n",
    "  Required: ", n, " replicates per group\n",
    "  Observed dispersion: ", round(disp, 3), "\n",
    "  Target fold-change: ", fc, "\n\n"
  )

  if (disp > 0.5) {
    recommendation <- paste0(
      recommendation,
      "High dispersion in pilot data. Consider:\n",
      "  1. Identifying and removing batch effects\n",
      "  2. Increasing sample size\n",
      "  3. Detecting larger fold-changes only\n"
    )
  }

  return(recommendation)
}


#' Recommend paired design
#' @keywords internal
recommend_paired_design <- function(n_pairs, fc) {
  recommendation <- paste0(
    "Paired design recommendation:\n",
    "  Required: ", n_pairs, " pairs (", n_pairs * 2, " total samples)\n",
    "  Target fold-change: ", fc, "\n\n",
    "Paired designs benefit from reduced variance.\n"
  )

  if (n_pairs < 5) {
    recommendation <- paste0(
      recommendation,
      "Warning: Small sample size (<5 pairs) may have limited power even with pairing.\n"
    )
  }

  return(recommendation)
}

