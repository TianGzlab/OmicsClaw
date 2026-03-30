# Example data loaders and validation functions for DESeq2 workflows
#
# This script provides:
# 1. Example data loading functions for testing/learning (load_pasilla_data, load_airway_data)
# 2. Validation functions for user-provided RNA-seq data (validate_input_data)
#
# Usage - Load example data:
#   source("scripts/load_example_data.R")
#   data <- load_pasilla_data()  # or load_airway_data()
#   counts <- data$counts
#   coldata <- data$coldata
#
# Usage - Validate user data:
#   source("scripts/load_example_data.R")
#   validated <- validate_input_data(counts, coldata, design_col = "condition")
#   counts <- validated$counts
#   coldata <- validated$coldata

#' Validate user-provided count matrix and metadata
#'
#' Checks that count data and metadata meet DESeq2 requirements
#'
#' @param counts Count matrix (genes × samples)
#' @param coldata Sample metadata data.frame
#' @param design_col Column name in coldata for primary comparison (default: "condition")
#' @return List with validated counts and coldata, or stops with informative error
validate_input_data <- function(counts, coldata, design_col = "condition") {
  errors <- character()

  # Check that inputs exist
  if (missing(counts) || is.null(counts)) {
    stop("counts parameter is required")
  }
  if (missing(coldata) || is.null(coldata)) {
    stop("coldata parameter is required")
  }

  # Check counts is matrix-like
  if (!is.matrix(counts) && !is.data.frame(counts)) {
    errors <- c(errors, "counts must be a matrix or data.frame")
  }

  # Check coldata is data.frame
  if (!is.data.frame(coldata)) {
    errors <- c(errors, "coldata must be a data.frame")
  }

  # Check sample IDs match
  if (!all(colnames(counts) %in% rownames(coldata))) {
    missing_samples <- setdiff(colnames(counts), rownames(coldata))
    errors <- c(errors, paste0(
      "Count matrix columns not found in coldata row names: ",
      paste(head(missing_samples, 5), collapse = ", "),
      if (length(missing_samples) > 5) " ..." else ""
    ))
  }

  # Check design column exists
  if (!design_col %in% colnames(coldata)) {
    errors <- c(errors, paste0(
      "Design column '", design_col, "' not found in coldata. ",
      "Available columns: ", paste(colnames(coldata), collapse = ", ")
    ))
  }

  # Check counts are non-negative
  if (is.matrix(counts) || is.data.frame(counts)) {
    if (any(counts < 0, na.rm = TRUE)) {
      errors <- c(errors, "counts contains negative values")
    }
  }

  # Check for NAs
  if (any(is.na(counts))) {
    errors <- c(errors, "counts contains NA values (DESeq2 requires complete data)")
  }

  # Report errors or success
  if (length(errors) > 0) {
    stop("Input validation failed:\n  - ", paste(errors, collapse = "\n  - "))
  }

  # Reorder coldata to match counts
  coldata <- coldata[colnames(counts), , drop = FALSE]

  # Convert counts to matrix if needed
  if (is.data.frame(counts)) {
    counts <- as.matrix(counts)
  }

  cat("✓ Input data validated successfully\n")
  cat("  Dimensions:", nrow(counts), "genes x", ncol(counts), "samples\n")
  cat("  Design column:", design_col, "\n")
  if (design_col %in% colnames(coldata)) {
    cat("  Groups:", paste(unique(coldata[[design_col]]), collapse = ", "), "\n")
  }

  return(list(counts = counts, coldata = coldata))
}

# =============================================================================
# EXAMPLE DATA LOADING FUNCTIONS (for testing/learning)
# =============================================================================

#' Load pasilla dataset (Drosophila RNAi knockdown experiment)
#'
#' Brooks et al. (2011) - Effect of pasilla gene knockdown on splicing
#' 7 samples: 4 untreated, 3 treated (RNAi knockdown)
#'
#' This function is for testing and learning purposes.
#' Auto-installs required packages if missing.
#'
#' @return List with counts (matrix), coldata (data.frame), and description
#' @examples
#' data <- load_pasilla_data()
#' counts <- data$counts
#' coldata <- data$coldata
load_pasilla_data <- function() {
  # Set CRAN mirror (required for package installation)
  if (length(getOption("repos")) == 0 || getOption("repos")["CRAN"] == "@CRAN@") {
    options(repos = c(CRAN = "https://cloud.r-project.org"))
  }

  # Install BiocManager if needed
  if (!requireNamespace("BiocManager", quietly = TRUE)) {
    cat("Installing BiocManager...\n")
    install.packages("BiocManager")
  }

  # Install pasilla if needed
  if (!requireNamespace("pasilla", quietly = TRUE)) {
    cat("Installing pasilla dataset package (~50MB, ~1-2 minutes)...\n")
    BiocManager::install("pasilla", update = FALSE, ask = FALSE)
  }

  library(pasilla)

  # Load data from package extdata directory
  pasillaDir <- system.file("extdata", package = "pasilla", mustWork = TRUE)

  # Read count matrix
  counts <- read.table(
    file.path(pasillaDir, "pasilla_gene_counts.tsv"),
    header = TRUE,
    row.names = 1,
    check.names = FALSE
  )

  # Read sample metadata
  coldata <- read.csv(
    file.path(pasillaDir, "pasilla_sample_annotation.csv"),
    row.names = 1
  )

  # Fix row names: remove 'fb' suffix to match count column names
  # Count columns: untreated1, untreated2, ...
  # Original metadata rows: untreated1fb, untreated2fb, ...
  rownames(coldata) <- gsub("fb$", "", rownames(coldata))

  # Convert to factors
  coldata$condition <- factor(coldata$condition)
  coldata$type <- factor(coldata$type)

  # Validate: ensure count columns match metadata rows
  if (!all(colnames(counts) %in% rownames(coldata))) {
    stop("Count matrix columns do not match metadata row names")
  }

  # Reorder metadata to match count matrix column order
  coldata <- coldata[colnames(counts), , drop = FALSE]

  # Convert to matrix (some functions expect matrix, not data.frame)
  counts <- as.matrix(counts)

  cat("✓ Pasilla dataset loaded successfully\n")
  cat("  Dimensions:", nrow(counts), "genes x", ncol(counts), "samples\n")
  cat("  Design: condition (treated vs untreated), type (single-read vs paired-end)\n")
  cat("  Recommended comparison: treated vs untreated\n")

  return(list(
    counts = counts,
    coldata = coldata,
    description = "Drosophila pasilla gene RNAi knockdown experiment"
  ))
}

#' Load airway dataset (human airway smooth muscle cells)
#'
#' Himes et al. (2014) - RNA-seq of airway smooth muscle cells treated with dexamethasone
#' 8 samples: 4 untreated, 4 dexamethasone-treated (2 paired cell lines × 2 replicates)
#'
#' This function is for testing and learning purposes.
#' Auto-installs required packages if missing.
#'
#' @return List with counts (matrix), coldata (data.frame), and description
#' @examples
#' data <- load_airway_data()
#' counts <- data$counts
#' coldata <- data$coldata
load_airway_data <- function() {
  # Set CRAN mirror
  if (length(getOption("repos")) == 0 || getOption("repos")["CRAN"] == "@CRAN@") {
    options(repos = c(CRAN = "https://cloud.r-project.org"))
  }

  # Install BiocManager if needed
  if (!requireNamespace("BiocManager", quietly = TRUE)) {
    cat("Installing BiocManager...\n")
    install.packages("BiocManager")
  }

  # Install airway if needed
  if (!requireNamespace("airway", quietly = TRUE)) {
    cat("Installing airway dataset package (~20MB, ~1 minute)...\n")
    BiocManager::install("airway", update = FALSE, ask = FALSE)
  }

  library(airway)

  # Load data
  data("airway")

  # Extract counts and metadata
  counts <- assay(airway)
  coldata <- as.data.frame(colData(airway))

  # Keep only essential columns for simplicity
  coldata <- coldata[, c("cell", "dex"), drop = FALSE]

  # Ensure factors
  coldata$cell <- factor(coldata$cell)
  coldata$dex <- factor(coldata$dex)

  # Validate
  if (!all(colnames(counts) %in% rownames(coldata))) {
    stop("Count matrix columns do not match metadata row names")
  }

  cat("✓ Airway dataset loaded successfully\n")
  cat("  Dimensions:", nrow(counts), "genes x", ncol(counts), "samples\n")
  cat("  Design: dex (treated vs untrt), cell (N61311 vs N052611)\n")
  cat("  Recommended comparison: treated vs untrt\n")
  cat("  Note: Can use ~ cell + dex to control for cell line effects\n")

  return(list(
    counts = counts,
    coldata = coldata,
    description = "Human airway smooth muscle cells treated with dexamethasone"
  ))
}

