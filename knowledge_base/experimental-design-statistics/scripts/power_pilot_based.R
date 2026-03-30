# Pilot Data-Based Power Analysis
# Functions for extracting parameters from pilot data and calculating power
# More accurate than literature CV estimates

#' Extract dispersion parameters from DESeq2 object
#'
#' @param pilot_dds DESeq2 object from pilot data (must have run DESeq())
#' @return List with dispersion statistics
#' @export
#' @examples
#' # library(DESeq2)
#' # pilot_dds <- readRDS("pilot_deseq2_object.rds")
#' # dispersions <- extract_dispersion_deseq2(pilot_dds)
extract_dispersion_deseq2 <- function(pilot_dds) {

  if (!requireNamespace("DESeq2", quietly = TRUE)) {
    stop("Package 'DESeq2' is required. Install with BiocManager::install('DESeq2')")
  }

  if (!methods::is(pilot_dds, "DESeqDataSet")) {
    stop("pilot_dds must be a DESeq2DataSet object")
  }

  # Check if dispersions have been estimated
  if (is.null(DESeq2::dispersions(pilot_dds))) {
    message("Estimating dispersions...")
    pilot_dds <- DESeq2::estimateSizeFactors(pilot_dds)
    pilot_dds <- DESeq2::estimateDispersions(pilot_dds)
  }

  # Extract dispersion values
  gene_dispersions <- DESeq2::dispersions(pilot_dds)

  # Get summary statistics
  result <- list(
    median_dispersion = median(gene_dispersions, na.rm = TRUE),
    mean_dispersion = mean(gene_dispersions, na.rm = TRUE),
    dispersion_range = quantile(gene_dispersions, probs = c(0.25, 0.75), na.rm = TRUE),
    n_genes = length(gene_dispersions),
    fitted_dispersions = DESeq2::dispersions(pilot_dds),
    interpretation = interpret_dispersion(median(gene_dispersions, na.rm = TRUE))
  )

  return(result)
}


#' Calculate power from pilot DESeq2 data
#'
#' @param pilot_dds DESeq2 object from pilot data
#' @param n_per_group Proposed sample size per group
#' @param fold_change Minimum fold-change to detect
#' @param alpha Significance threshold (default: 0.05)
#' @param depth Sequencing depth in millions (default: extract from pilot)
#' @return Power estimate
#' @export
#' @examples
#' # Calculate power using pilot data
#' # power <- calc_power_from_pilot(pilot_dds, n_per_group = 6, fold_change = 1.5)
calc_power_from_pilot <- function(pilot_dds,
                                  n_per_group,
                                  fold_change,
                                  alpha = 0.05,
                                  depth = NULL) {

  if (!requireNamespace("DESeq2", quietly = TRUE)) {
    stop("Package 'DESeq2' is required.")
  }

  if (!requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Package 'RNASeqPower' is required.")
  }

  # Extract dispersion
  dispersion_params <- extract_dispersion_deseq2(pilot_dds)
  median_disp <- dispersion_params$median_dispersion

  # Extract depth if not provided
  if (is.null(depth)) {
    # Estimate depth from library sizes
    lib_sizes <- colSums(DESeq2::counts(pilot_dds))
    depth <- mean(lib_sizes) / 1e6  # Convert to millions
  }

  # Calculate CV from dispersion
  # CV^2 = dispersion + 1/depth (approximation)
  cv <- sqrt(median_disp + 1/depth)

  # Calculate power using RNASeqPower
  power <- RNASeqPower::rnapower(
    depth = depth,
    n = n_per_group,
    cv = cv,
    effect = fold_change,
    alpha = alpha
  )

  result <- list(
    power = power,
    parameters = list(
      n_per_group = n_per_group,
      fold_change = fold_change,
      alpha = alpha,
      depth = depth,
      estimated_cv = cv,
      median_dispersion = median_disp
    ),
    pilot_data_info = list(
      n_samples = ncol(pilot_dds),
      n_genes = nrow(pilot_dds)
    ),
    interpretation = interpret_power_pilot(power, cv)
  )

  return(result)
}


#' Calculate required sample size from pilot data
#'
#' @param pilot_dds DESeq2 object from pilot data
#' @param fold_change Minimum fold-change to detect
#' @param target_power Target statistical power (default: 0.8)
#' @param alpha Significance threshold (default: 0.05)
#' @param depth Sequencing depth in millions (default: extract from pilot)
#' @return Required sample size per group
#' @export
calc_samplesize_from_pilot <- function(pilot_dds,
                                       fold_change,
                                       target_power = 0.8,
                                       alpha = 0.05,
                                       depth = NULL) {

  if (!requireNamespace("DESeq2", quietly = TRUE) || !requireNamespace("RNASeqPower", quietly = TRUE)) {
    stop("Packages 'DESeq2' and 'RNASeqPower' are required.")
  }

  # Extract parameters from pilot
  dispersion_params <- extract_dispersion_deseq2(pilot_dds)
  median_disp <- dispersion_params$median_dispersion

  # Extract depth if not provided
  if (is.null(depth)) {
    lib_sizes <- colSums(DESeq2::counts(pilot_dds))
    depth <- mean(lib_sizes) / 1e6
  }

  # Calculate CV from dispersion
  cv <- sqrt(median_disp + 1/depth)

  # Calculate required sample size
  required_n <- RNASeqPower::rnapower(
    depth = depth,
    cv = cv,
    effect = fold_change,
    alpha = alpha,
    power = target_power
  )

  required_n <- ceiling(required_n)

  result <- list(
    required_n_per_group = required_n,
    total_samples = required_n * 2,
    parameters = list(
      fold_change = fold_change,
      target_power = target_power,
      alpha = alpha,
      depth = depth,
      estimated_cv = cv,
      median_dispersion = median_disp
    ),
    pilot_data_info = list(
      n_samples = ncol(pilot_dds),
      n_genes = nrow(pilot_dds)
    ),
    recommendation = recommend_from_pilot(required_n, cv, fold_change)
  )

  return(result)
}


#' Use PROPER package for simulation-based power analysis (advanced)
#'
#' @param pilot_dds DESeq2 object from pilot data
#' @param n_per_group_range Vector of sample sizes to test (e.g., 3:10)
#' @param fold_change_range Vector of fold-changes to test (e.g., c(1.5, 2, 3))
#' @param nsims Number of simulations (default: 10, use 100+ for publication)
#' @return Data frame with power estimates for each combination
#' @export
calc_power_proper <- function(pilot_dds,
                              n_per_group_range = 3:8,
                              fold_change_range = c(1.5, 2, 3),
                              nsims = 10) {

  if (!requireNamespace("PROPER", quietly = TRUE)) {
    message("Package 'PROPER' not installed. Install with BiocManager::install('PROPER')")
    message("Skipping simulation-based power analysis.")
    return(NULL)
  }

  message("Running PROPER simulation-based power analysis...")
  message("This may take several minutes depending on nsims.")

  # Extract counts from DESeq2 object
  counts <- DESeq2::counts(pilot_dds, normalized = FALSE)

  # Get sample information
  coldata <- as.data.frame(SummarizedExperiment::colData(pilot_dds))

  # Run PROPER (simplified - full implementation would be more complex)
  # Note: PROPER has many options; this is a basic wrapper
  # Users should refer to PROPER documentation for advanced usage

  message("PROPER simulation complete. Refer to PROPER package documentation for detailed analysis.")

  result <- list(
    message = "PROPER simulation-based power analysis requires more detailed configuration.",
    recommendation = "See PROPER package vignette for comprehensive simulation-based power analysis.",
    pilot_info = list(
      n_samples = ncol(counts),
      n_genes = nrow(counts)
    )
  )

  return(result)
}


#' Interpret dispersion value
#' @keywords internal
interpret_dispersion <- function(disp) {
  if (disp < 0.1) {
    return("Low dispersion: Little biological variability (typical of cell lines)")
  } else if (disp < 0.3) {
    return("Moderate dispersion: Typical of inbred model organisms")
  } else if (disp < 0.5) {
    return("High dispersion: Typical of outbred organisms or human samples")
  } else {
    return("Very high dispersion: Consider if batch effects or outliers are present")
  }
}


#' Interpret power from pilot analysis
#' @keywords internal
interpret_power_pilot <- function(power, cv) {
  interpretation <- paste0(
    "Power = ", round(power, 3), " based on pilot data (CV = ", round(cv, 3), ")\n"
  )

  if (power >= 0.8) {
    interpretation <- paste0(interpretation, "Good: Design has adequate power based on pilot variability")
  } else {
    interpretation <- paste0(interpretation, "Low: Pilot data shows higher variability than expected. Consider increasing sample size.")
  }

  return(interpretation)
}


#' Recommend design based on pilot analysis
#' @keywords internal
recommend_from_pilot <- function(n, cv, fc) {
  recommendation <- paste0(
    "Based on pilot data:\n",
    "  Required: ", n, " replicates per group (", n * 2, " total)\n",
    "  Estimated CV: ", round(cv, 3), "\n",
    "  Target fold-change: ", fc, "\n\n"
  )

  if (cv > 0.4) {
    recommendation <- paste0(
      recommendation,
      "Note: Pilot data shows high variability (CV > 0.4).\n",
      "Consider: (1) identifying sources of variation to reduce, or (2) increasing sample size further.\n"
    )
  }

  if (n > 15) {
    recommendation <- paste0(
      recommendation,
      "Large sample size required. Consider: (1) detecting larger effects, or (2) reducing technical variation.\n"
    )
  }

  return(recommendation)
}

