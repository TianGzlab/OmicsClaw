# Load Example Data for Experimental Design
# Provides pilot data for testing power analysis and sample size calculations

#' Load example pilot data for experimental design testing
#'
#' Downloads and prepares example RNA-seq count data with known variability
#' characteristics for testing power analysis and sample size calculations.
#'
#' @return List with components:
#'   - counts: Raw count matrix
#'   - metadata: Sample metadata (condition, batch, etc.)
#'   - dds: DESeqDataSet object (for DESeq2-based calculations)
#'   - dispersions: Gene-level dispersion estimates
#'   - cv: Coefficient of variation summary
#'
#' @export
load_example_data <- function() {

  # Set CRAN mirror
  options(repos = c(CRAN = "https://cloud.r-project.org"))

  message("\n=== Loading Example Pilot Data ===\n")

  # Check and install required packages
  required_packages <- c("pasilla", "DESeq2")

  for (pkg in required_packages) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
      message(paste0("Installing ", pkg, " package..."))
      if (pkg %in% c("pasilla", "DESeq2")) {
        if (!requireNamespace("BiocManager", quietly = TRUE)) {
          install.packages("BiocManager")
        }
        BiocManager::install(pkg, update = FALSE, ask = FALSE)
      } else {
        install.packages(pkg)
      }
    }
  }

  # Load libraries
  suppressPackageStartupMessages({
    library(pasilla)
    library(DESeq2)
  })

  message("Creating example pilot data (RNA-seq simulation)...")

  # Generate realistic example RNA-seq data for testing
  # Based on typical RNA-seq characteristics
  set.seed(123)  # For reproducibility

  n_genes <- 2000  # Moderate number for quick testing
  n_samples_per_group <- 4  # 4 replicates per condition

  # Create sample metadata
  metadata <- data.frame(
    sample_id = paste0("sample_", 1:(2 * n_samples_per_group)),
    condition = rep(c("control", "treated"), each = n_samples_per_group),
    batch = rep(c("batch1", "batch2"), times = n_samples_per_group),
    stringsAsFactors = FALSE
  )
  rownames(metadata) <- metadata$sample_id

  # Generate realistic count data
  # Simulate negative binomial distribution typical of RNA-seq
  base_counts <- matrix(
    rnbinom(n_genes * n_samples_per_group * 2,
            mu = runif(n_genes, 50, 5000),
            size = runif(n_genes, 0.1, 2)),
    nrow = n_genes,
    ncol = n_samples_per_group * 2
  )

  # Add some differential expression (20% of genes)
  de_genes <- sample(1:n_genes, size = round(0.2 * n_genes))
  for (i in de_genes) {
    fold_change <- sample(c(0.5, 2), 1)  # 2-fold up or down
    base_counts[i, (n_samples_per_group + 1):(2 * n_samples_per_group)] <-
      round(base_counts[i, (n_samples_per_group + 1):(2 * n_samples_per_group)] * fold_change)
  }

  # Ensure all counts are integers
  base_counts <- round(base_counts)

  # Set gene names
  rownames(base_counts) <- paste0("gene_", 1:n_genes)
  colnames(base_counts) <- metadata$sample_id

  counts_filtered <- base_counts

  message(paste0("  Samples: ", ncol(counts_filtered)))
  message(paste0("  Genes: ", nrow(counts_filtered)))
  message(paste0("  Conditions: ", paste(unique(metadata$condition), collapse = ", ")))

  # Create DESeqDataSet
  dds <- DESeqDataSetFromMatrix(
    countData = counts_filtered,
    colData = metadata,
    design = ~ condition
  )

  # Run DESeq2 to get dispersion estimates
  message("\nCalculating dispersion estimates for power analysis...")
  dds <- DESeq(dds, quiet = TRUE)

  # Extract dispersion estimates
  dispersions <- dispersions(dds)

  # Calculate coefficient of variation (CV)
  # CV is useful for power calculations
  normalized_counts <- counts(dds, normalized = TRUE)
  gene_means <- rowMeans(normalized_counts)
  gene_sds <- apply(normalized_counts, 1, sd)
  gene_cvs <- gene_sds / gene_means

  # Summary CV (median is more robust than mean)
  median_cv <- median(gene_cvs[is.finite(gene_cvs) & gene_cvs > 0], na.rm = TRUE)
  mean_cv <- mean(gene_cvs[is.finite(gene_cvs) & gene_cvs > 0], na.rm = TRUE)

  message(paste0("\nVariability estimates from pilot data:"))
  message(paste0("  Median CV: ", round(median_cv, 3)))
  message(paste0("  Mean CV: ", round(mean_cv, 3)))
  message(paste0("  Median dispersion: ", round(median(dispersions, na.rm = TRUE), 4)))

  message("\n✓ Example pilot data loaded successfully!\n")
  message("This pilot data can be used for:")
  message("  • Power analysis with realistic variability estimates")
  message("  • Sample size calculations")
  message("  • Testing batch assignment algorithms")

  # Return all components
  return(list(
    counts = counts_filtered,
    metadata = metadata,
    dds = dds,
    dispersions = dispersions,
    cv = list(
      median = median_cv,
      mean = mean_cv,
      per_gene = gene_cvs[is.finite(gene_cvs)]
    )
  ))
}


#' Load tissue-specific CV database
#'
#' Loads literature-derived coefficient of variation values for different
#' tissue types when pilot data is not available.
#'
#' @param tissue_type Optional: filter to specific tissue
#' @return Data frame with tissue-specific CV values
#'
#' @export
load_cv_database <- function(tissue_type = NULL) {

  cv_file <- "references/cv_tissue_database.csv"

  if (!file.exists(cv_file)) {
    stop(paste0("CV database not found: ", cv_file,
                "\nPlease ensure you are in the experimental-design-statistics directory."))
  }

  cv_db <- read.csv(cv_file, stringsAsFactors = FALSE)

  if (!is.null(tissue_type)) {
    cv_db <- cv_db[cv_db$tissue == tissue_type, ]
    if (nrow(cv_db) == 0) {
      stop(paste0("Tissue type '", tissue_type, "' not found in database."))
    }
  }

  message(paste0("✓ Loaded CV estimates for ", nrow(cv_db), " tissue type(s)"))

  return(cv_db)
}


#' Quick test of experimental design workflow
#'
#' Demonstrates complete workflow with example data
#'
#' @export
test_workflow <- function() {

  message("\n=== Testing Experimental Design Workflow ===\n")

  # Load example data
  pilot_data <- load_example_data()

  message("\n--- Step 1: Example data loaded ---")
  message("Use pilot_data$dds for power calculations")
  message("Use pilot_data$cv$median for sample size estimation")
  message("Use pilot_data$metadata for batch design testing\n")

  message("Next steps:")
  message("  1. Run power analysis: source('scripts/power_rnaseq.R')")
  message("  2. Calculate sample size: source('scripts/sample_size_de.R')")
  message("  3. Design batch layout: source('scripts/batch_assignment.R')")
  message("  4. Export design: source('scripts/export_design.R')")

  invisible(pilot_data)
}

