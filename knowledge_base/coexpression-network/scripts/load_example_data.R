#' Load Example WGCNA Dataset
#'
#' Loads the female mouse liver dataset from the WGCNA tutorial.
#' This dataset contains 135 samples of liver tissue from female mice
#' with multiple physiological traits measured.
#'
#' Auto-installs required packages if missing.
#'
#' @return List with three elements:
#'   \item{datExpr}{Expression matrix in WGCNA format (samples × genes)}
#'   \item{meta}{Sample metadata with traits}
#'   \item{description}{Character string describing the dataset}
#' @export
#'
#' @examples
#' \dontrun{
#' data <- load_example_wgcna_data()
#' datExpr <- data$datExpr
#' meta <- data$meta
#' }
load_example_wgcna_data <- function() {
  # Set CRAN mirror FIRST (common failure point)
  if (length(getOption("repos")) == 0 || getOption("repos")["CRAN"] == "@CRAN@") {
    options(repos = c(CRAN = "https://cloud.r-project.org"))
  }

  # Auto-install BiocManager if needed
  if (!requireNamespace("BiocManager", quietly = TRUE)) {
    cat("Installing BiocManager...\n")
    install.packages("BiocManager")
  }

  # Auto-install WGCNA if needed
  if (!requireNamespace("WGCNA", quietly = TRUE)) {
    cat("Installing WGCNA package (~5 min)...\n")
    BiocManager::install("WGCNA", update = FALSE, ask = FALSE)
  }

  library(WGCNA)

  # Download tutorial data from WGCNA website
  cat("Downloading female mouse liver dataset (~2MB)...\n")

  # URLs for the female mouse liver data
  expr_url <- "https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/Tutorials/FemaleLiver-Data/LiverFemale3600.csv"
  traits_url <- "https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/Tutorials/FemaleLiver-Data/ClinicalTraits.csv"

  # Create temporary directory for downloads
  temp_dir <- tempdir()
  expr_file <- file.path(temp_dir, "LiverFemale3600.csv")
  traits_file <- file.path(temp_dir, "ClinicalTraits.csv")

  # Download files
  tryCatch({
    download.file(expr_url, expr_file, method = "auto", quiet = FALSE)
    download.file(traits_url, traits_file, method = "auto", quiet = FALSE)
  }, error = function(e) {
    stop("Failed to download example data. Please check your internet connection.\n",
         "Error: ", e$message)
  })

  # Load expression data
  cat("Loading expression data...\n")
  femData <- read.csv(expr_file)

  # Transpose to WGCNA format (samples × genes)
  # First column is gene names, rest are samples
  datExpr0 <- as.data.frame(t(femData[, -1]))
  colnames(datExpr0) <- femData[, 1]
  rownames(datExpr0) <- names(femData)[-1]

  # Check for excessive missing values and outliers
  gsg <- goodSamplesGenes(datExpr0, verbose = 3)

  if (!gsg$allOK) {
    # Optionally, print the gene and sample names that were removed
    if (sum(!gsg$goodGenes) > 0)
      cat("Removing genes:", paste(names(datExpr0)[!gsg$goodGenes], collapse = ", "), "\n")
    if (sum(!gsg$goodSamples) > 0)
      cat("Removing samples:", paste(rownames(datExpr0)[!gsg$goodSamples], collapse = ", "), "\n")
    # Remove the offending genes and samples from the data
    datExpr0 <- datExpr0[gsg$goodSamples, gsg$goodGenes]
  }

  # Load clinical traits
  cat("Loading clinical traits...\n")
  traitData <- read.csv(traits_file)

  # Match samples between expression and traits
  # Remove columns that hold information we do not need
  allTraits <- traitData[, -c(31, 16)]
  allTraits <- allTraits[, c(2, 11:36)]

  # Form a data frame analogous to expression data that will hold the clinical traits
  femaleSamples <- rownames(datExpr0)
  traitRows <- match(femaleSamples, allTraits$Mice)
  datTraits <- allTraits[traitRows, -1]
  rownames(datTraits) <- allTraits[traitRows, 1]

  # Ensure sample names match exactly
  if (!all(rownames(datExpr0) == rownames(datTraits))) {
    warning("Sample names don't match exactly. Subsetting to common samples.")
    common_samples <- intersect(rownames(datExpr0), rownames(datTraits))
    datExpr0 <- datExpr0[common_samples, ]
    datTraits <- datTraits[common_samples, ]
  }

  cat("\n")
  cat("✓ Successfully loaded female mouse liver dataset\n")
  cat("  Samples:", nrow(datExpr0), "\n")
  cat("  Genes:", ncol(datExpr0), "\n")
  cat("  Traits:", ncol(datTraits), "\n")
  cat("  Available traits:", paste(colnames(datTraits)[1:5], collapse = ", "), "...\n")
  cat("\n")

  # Return standardized format
  return(list(
    datExpr = datExpr0,
    meta = datTraits,
    description = paste(
      "Female mouse liver dataset from WGCNA tutorial.",
      nrow(datExpr0), "samples,", ncol(datExpr0), "genes.",
      "Microarray expression data with", ncol(datTraits), "clinical traits",
      "including weight, glucose, insulin, and lipid measurements."
    )
  ))
}


#' Validate Input Data for WGCNA
#'
#' Checks if user-provided data meets WGCNA requirements.
#' Validates format, sample size, missing values, and data quality.
#'
#' @param expr_data Expression matrix (samples × genes) or (genes × samples)
#' @param meta_data Sample metadata (optional)
#' @param min_samples Minimum required samples (default: 15)
#'
#' @return List with validation results and reformatted data if successful
#' @export
validate_input_data <- function(expr_data, meta_data = NULL, min_samples = 15) {

  cat("Validating input data...\n")

  # Check if data is a data frame or matrix
  if (!is.data.frame(expr_data) && !is.matrix(expr_data)) {
    stop("Expression data must be a data frame or matrix")
  }

  # Determine orientation (genes × samples or samples × genes)
  if (nrow(expr_data) > ncol(expr_data)) {
    cat("  Detected genes × samples format. Transposing to samples × genes...\n")
    expr_data <- t(expr_data)
  }

  # Check sample size
  n_samples <- nrow(expr_data)
  n_genes <- ncol(expr_data)

  cat("  Samples:", n_samples, "\n")
  cat("  Genes:", n_genes, "\n")

  if (n_samples < min_samples) {
    stop("Insufficient samples: WGCNA requires at least ", min_samples, " samples. ",
         "You have ", n_samples, " samples.")
  }

  if (n_samples < 20) {
    warning("Sample size is low (", n_samples, " samples). ",
            "WGCNA works best with 20+ samples. Results may be less robust.")
  }

  # Check for missing values
  missing_pct <- sum(is.na(expr_data)) / (nrow(expr_data) * ncol(expr_data)) * 100
  cat("  Missing values:", round(missing_pct, 2), "%\n")

  if (missing_pct > 5) {
    warning("High proportion of missing values (", round(missing_pct, 2), "%). ",
            "Consider imputation or removing genes/samples with excessive missingness.")
  }

  # Check for sample metadata if provided
  if (!is.null(meta_data)) {
    if (nrow(meta_data) != n_samples) {
      stop("Metadata has ", nrow(meta_data), " rows but expression data has ",
           n_samples, " samples")
    }
    cat("  Metadata:", ncol(meta_data), "traits\n")
  }

  # Use WGCNA's goodSamplesGenes function
  if (requireNamespace("WGCNA", quietly = TRUE)) {
    library(WGCNA)
    gsg <- goodSamplesGenes(expr_data, verbose = 0)

    if (!gsg$allOK) {
      cat("  Removing", sum(!gsg$goodGenes), "genes and",
          sum(!gsg$goodSamples), "samples with excessive missing values...\n")
      expr_data <- expr_data[gsg$goodSamples, gsg$goodGenes]
      if (!is.null(meta_data)) {
        meta_data <- meta_data[gsg$goodSamples, ]
      }
    }
  }

  cat("✓ Data validation successful\n\n")

  return(list(
    datExpr = expr_data,
    meta = meta_data,
    n_samples = nrow(expr_data),
    n_genes = ncol(expr_data)
  ))
}

