# ATAC-seq Power Analysis
# Functions for calculating statistical power for ATAC-seq and other peak-based assays
# Based on: ssizeRNA package methodology

#' Calculate power for ATAC-seq experiment
#'
#' @param m Total number of peaks to be tested
#' @param m1 Expected number of differentially accessible peaks
#' @param fold_change Minimum fold-change to detect
#' @param fdr False discovery rate threshold (default: 0.05)
#' @param n_per_group Number of replicates per condition (if NULL, will calculate required n)
#' @param mu Mean read count per peak per sample
#' @param disp Dispersion parameter (typically 0.1-0.3 for ATAC-seq)
#' @param power Target power if calculating sample size (default: 0.8)
#' @return Power estimate or required sample size
#' @export
#' @examples
#' # Calculate power for 4 replicates per group
#' calc_power_atac(m = 10000, m1 = 500, fold_change = 2, n_per_group = 4, mu = 10, disp = 0.1)
#'
#' # Calculate required sample size for 80% power
#' calc_power_atac(m = 10000, m1 = 500, fold_change = 2, mu = 10, disp = 0.1, power = 0.8)
calc_power_atac <- function(m,
                            m1,
                            fold_change,
                            fdr = 0.05,
                            n_per_group = NULL,
                            mu = 10,
                            disp = 0.1,
                            power = NULL) {

  # Check required package
  if (!requireNamespace("ssizeRNA", quietly = TRUE)) {
    stop("Package 'ssizeRNA' is required. Install with BiocManager::install('ssizeRNA')")
  }

  # Validate inputs
  if (m <= 0 || m1 <= 0 || m1 > m) {
    stop("Invalid parameters: m and m1 must be positive, and m1 must be <= m")
  }

  if (fold_change <= 1 || mu <= 0 || disp < 0) {
    stop("Invalid parameters: fold_change must be >1, mu must be positive, disp must be non-negative")
  }

  # Calculate pi0 (proportion of non-differential peaks)
  pi0 <- 1 - (m1 / m)

  # Calculate power or sample size using ssizeRNA
  if (!is.null(n_per_group)) {
    # Calculate power for given n
    result <- ssizeRNA::ssizeRNA_vary(
      nGenes = m,
      pi0 = pi0,
      m = n_per_group,
      mu = mu,
      disp = disp,
      fc = fold_change,
      fdr = fdr,
      power = NULL
    )

    power_value <- result$power

    output <- list(
      power = power_value,
      n_per_group = n_per_group,
      parameters = list(
        total_peaks = m,
        differential_peaks = m1,
        fold_change = fold_change,
        fdr = fdr,
        mean_count = mu,
        dispersion = disp
      ),
      interpretation = interpret_power_atac(power_value, n_per_group)
    )

  } else if (!is.null(power)) {
    # Calculate required sample size for target power
    result <- ssizeRNA::ssizeRNA_vary(
      nGenes = m,
      pi0 = pi0,
      mu = mu,
      disp = disp,
      fc = fold_change,
      fdr = fdr,
      power = power,
      m = NULL
    )

    required_n <- ceiling(result$m)

    output <- list(
      required_n_per_group = required_n,
      target_power = power,
      parameters = list(
        total_peaks = m,
        differential_peaks = m1,
        fold_change = fold_change,
        fdr = fdr,
        mean_count = mu,
        dispersion = disp
      ),
      total_samples = required_n * 2,
      recommendation = recommend_atac_design(required_n, fold_change)
    )

  } else {
    stop("Must provide either n_per_group (to calculate power) or power (to calculate required n)")
  }

  return(output)
}


#' Estimate ATAC-seq parameters from pilot data
#'
#' @param pilot_counts Matrix of peak counts from pilot ATAC-seq data (peaks x samples)
#' @return List with estimated mu and dispersion
#' @export
#' @examples
#' # pilot_counts <- read.csv("pilot_atac_peaks.csv", row.names = 1)
#' # params <- estimate_atac_params(pilot_counts)
estimate_atac_params <- function(pilot_counts) {

  if (!requireNamespace("DESeq2", quietly = TRUE)) {
    stop("Package 'DESeq2' is required for parameter estimation. Install with BiocManager::install('DESeq2')")
  }

  # Convert to matrix if data frame
  if (is.data.frame(pilot_counts)) {
    pilot_counts <- as.matrix(pilot_counts)
  }

  # Remove very low count peaks
  mean_counts <- rowMeans(pilot_counts)
  pilot_counts <- pilot_counts[mean_counts >= 5, ]

  # Estimate mean count across peaks
  estimated_mu <- mean(rowMeans(pilot_counts))

  # Estimate dispersion using DESeq2 approach (simplified)
  # Create a simple condition vector
  condition <- factor(rep(c("A", "B"), length.out = ncol(pilot_counts)))

  # Create DESeq2 dataset
  coldata <- data.frame(condition = condition, row.names = colnames(pilot_counts))
  dds <- DESeq2::DESeqDataSetFromMatrix(
    countData = pilot_counts,
    colData = coldata,
    design = ~ condition
  )

  # Estimate dispersions
  dds <- DESeq2::estimateSizeFactors(dds)
  dds <- DESeq2::estimateDispersions(dds)

  # Get median dispersion
  estimated_disp <- median(DESeq2::dispersions(dds), na.rm = TRUE)

  result <- list(
    estimated_mu = estimated_mu,
    estimated_dispersion = estimated_disp,
    n_peaks_used = nrow(pilot_counts),
    recommendation = recommend_atac_params(estimated_mu, estimated_disp)
  )

  return(result)
}


#' Interpret ATAC-seq power
#' @keywords internal
interpret_power_atac <- function(power, n) {
  interpretation <- paste0("Power = ", round(power, 3), " with n=", n, " per group\n")

  if (power >= 0.8) {
    interpretation <- paste0(interpretation, "Good: Adequate power for detecting differential peaks")
  } else {
    interpretation <- paste0(interpretation, "Low: Consider increasing replicates to n=", n + 2, " or detecting larger effects")
  }

  return(interpretation)
}


#' Recommend ATAC-seq design
#' @keywords internal
recommend_atac_design <- function(n, fc) {
  recommendation <- paste0(
    "Recommended: ", n, " replicates per group for fold-change=", fc, "\n"
  )

  if (n < 3) {
    recommendation <- paste0(recommendation, "Warning: ATAC-seq typically needs at least 3 replicates\n")
  }

  if (n >= 3 && n <= 5) {
    recommendation <- paste0(recommendation, "This is a reasonable design for ATAC-seq\n")
  }

  return(recommendation)
}


#' Recommend interpretation of ATAC parameters
#' @keywords internal
recommend_atac_params <- function(mu, disp) {
  recommendation <- paste0(
    "Estimated parameters from pilot data:\n",
    "  Mean count per peak: ", round(mu, 1), "\n",
    "  Dispersion: ", round(disp, 3), "\n\n"
  )

  if (mu < 5) {
    recommendation <- paste0(recommendation, "Low mean counts: Consider deeper sequencing\n")
  } else if (mu > 50) {
    recommendation <- paste0(recommendation, "High mean counts: Good coverage for power\n")
  }

  if (disp < 0.2) {
    recommendation <- paste0(recommendation, "Low dispersion: Data has low variability (good for power)\n")
  } else if (disp > 0.5) {
    recommendation <- paste0(recommendation, "High dispersion: High variability may require more replicates\n")
  }

  return(recommendation)
}

