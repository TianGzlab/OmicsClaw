# Load example/demo data for clustering analysis testing
#
# This script loads the ALL (Acute Lymphoblastic Leukemia) dataset
# from Bioconductor for quick testing and learning.

#' Load ALL (Acute Lymphoblastic Leukemia) Microarray Data
#'
#' This function loads real patient gene expression data from the classic ALL
#' dataset (Chiaretti et al. 2004), which contains 128 pediatric ALL patients
#' with B-cell and T-cell subtypes. The data is pre-processed and suitable for
#' demonstrating clustering methods on real biological data.
#'
#' @param n_top_variable_genes Number of most variable genes to keep (default: 1000)
#'
#' @return A list containing:
#'   \item{data}{Normalized data matrix (samples × genes)}
#'   \item{metadata}{Sample annotations with cell type labels}
#'   \item{feature_names}{Gene probe IDs}
#'   \item{sample_names}{Sample identifiers}
#'   \item{true_labels}{Ground truth cell type labels (B vs T)}
#'   \item{description}{Dataset description}
#'   \item{n_samples}{Number of samples}
#'   \item{n_features}{Number of features}
#'   \item{cell_types}{Vector of cell type names}
#'
#' @details
#' - Data is log2-transformed and quantile-normalized microarray data
#' - Contains 128 samples from pediatric ALL patients
#' - Main subtypes: B-cell ALL (95 samples) vs T-cell ALL (33 samples)
#' - Runtime: ~30 seconds on first run (downloads/installs), <5 seconds cached
#' - Citation: Chiaretti et al. (2004) Blood 103(7):2771-2781
#'
#' @examples
#' \dontrun{
#' data_list <- load_example_clustering_data()
#' data <- data_list$data  # 128 samples × 1000 genes
#' metadata <- data_list$metadata
#' }
#'
#' @export
load_example_clustering_data <- function(n_top_variable_genes = 1000) {
  cat("Loading ALL (Acute Lymphoblastic Leukemia) dataset...\n")
  cat("  Source: Chiaretti et al. (2004) - 128 pediatric ALL patients\n")

  # Set CRAN mirror
  options(repos = c(CRAN = "https://cloud.r-project.org"))

  # Install BiocManager if needed
  if (!requireNamespace("BiocManager", quietly = TRUE)) {
    cat("  Installing BiocManager...\n")
    install.packages("BiocManager")
  }

  # Install ALL package if needed
  if (!requireNamespace("ALL", quietly = TRUE)) {
    cat("  Installing ALL dataset package (~5MB, ~1 min)...\n")
    BiocManager::install("ALL", update = FALSE)
  }

  # Load the dataset
  cat("  Loading data from Bioconductor...\n")
  suppressPackageStartupMessages({
    library(ALL)
    library(Biobase)
  })

  data(ALL)

  # Get expression data (genes × samples)
  expr_data <- exprs(ALL)

  # Get phenotype data
  pheno_data <- pData(ALL)

  # Extract cell type (BT = B-cell or T-cell)
  # The BT column has values like "B", "B1", "B2", "B3", "B4", "T", "T1", "T2"
  pheno_data$cell_type <- ifelse(grepl("^B", pheno_data$BT), "B", "T")

  # Transpose so samples are rows, genes are columns
  data_t <- t(expr_data)

  # Select top variable genes
  gene_vars <- apply(data_t, 2, var)
  top_genes <- names(sort(gene_vars, decreasing = TRUE)[1:n_top_variable_genes])
  data_subset <- data_t[, top_genes]

  # Z-score normalize (scale each gene)
  data_normalized <- scale(data_subset)

  # Create metadata data frame
  sample_names <- rownames(data_normalized)
  metadata <- data.frame(
    sample_id = sample_names,
    cell_type = pheno_data[sample_names, "cell_type"],
    bt_subtype = pheno_data[sample_names, "BT"],
    stringsAsFactors = FALSE
  )

  # Create numeric labels for evaluation
  true_labels <- ifelse(metadata$cell_type == "B", 0, 1)
  names(true_labels) <- sample_names

  cat("\n✓ Data loaded successfully!\n")
  cat(sprintf("  Data shape: %d samples × %d genes\n",
              nrow(data_normalized), ncol(data_normalized)))
  cat("  Data type: Microarray (log2, quantile-normalized)\n")
  cat(sprintf("  Cell types: B-cell ALL (n=%d), T-cell ALL (n=%d)\n",
              sum(metadata$cell_type == "B"),
              sum(metadata$cell_type == "T")))

  # Return list
  list(
    data = data_normalized,
    metadata = metadata,
    feature_names = colnames(data_normalized),
    sample_names = sample_names,
    true_labels = true_labels,
    description = sprintf(
      "ALL (Acute Lymphoblastic Leukemia) microarray data: 128 pediatric patients with B-cell or T-cell ALL subtypes. Data is log2-transformed, quantile-normalized, filtered to %d most variable genes. Citation: Chiaretti et al. (2004) Blood 103(7):2771-2781",
      n_top_variable_genes
    ),
    n_samples = nrow(data_normalized),
    n_features = ncol(data_normalized),
    cell_types = c("B-cell ALL", "T-cell ALL")
  )
}


#' Load a Smaller Subset of ALL Dataset for Very Quick Testing
#'
#' @return Same structure as load_example_clustering_data() but with:
#'   - 128 samples (same as full dataset)
#'   - 100 most variable genes (vs 1000 default)
#'
#' @details
#' Use this for rapid testing (<5 seconds). For learning, use the
#' default load_example_clustering_data() with 1000 genes.
#'
#' @examples
#' \dontrun{
#' small_data <- load_example_clustering_data_small()
#' }
#'
#' @export
load_example_clustering_data_small <- function() {
  load_example_clustering_data(n_top_variable_genes = 100)
}


# Test the function when sourced directly
if (sys.nframe() == 0) {
  cat(rep("=", 80), "\n", sep = "")
  cat("Testing Example Data Loader\n")
  cat(rep("=", 80), "\n", sep = "")

  # Test default parameters
  cat("\n1. Loading default example data...\n")
  data_list <- load_example_clustering_data()
  cat("\nReturned components:", paste(names(data_list), collapse = ", "), "\n")
  cat("Description:", data_list$description, "\n")

  # Test small version
  cat("\n", rep("=", 80), "\n", sep = "")
  cat("2. Loading small example data...\n")
  small_data_list <- load_example_clustering_data_small()
  cat("\nReturned components:", paste(names(small_data_list), collapse = ", "), "\n")
  cat("Description:", small_data_list$description, "\n")

  cat("\n", rep("=", 80), "\n", sep = "")
  cat("✓ All tests passed!\n")
}

