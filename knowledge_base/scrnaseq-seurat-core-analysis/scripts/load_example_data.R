# ============================================================================
# LOAD EXAMPLE DATA
# ============================================================================
#
# Load example single-cell RNA-seq datasets for testing and demonstrations.
# This script provides user-facing functions to load data from the SeuratData
# package for learning and testing the workflow.
#
# Functions:
#   - load_seurat_data(): Load example datasets (pbmc3k, ifnb, etc.)
#
# Usage:
#   source("scripts/load_example_data.R")
#   seurat_obj <- load_seurat_data("pbmc3k")

#' Load example data from SeuratData package
#'
#' Loads publicly available single-cell RNA-seq datasets from the SeuratData
#' package. Use this for testing the workflow with real data.
#'
#' Available datasets:
#'   - "pbmc3k": 3k PBMCs from a healthy donor (10X Genomics)
#'   - "ifnb": Immune cells stimulated with interferon-beta
#'   - Other datasets from SeuratData package
#'
#' @param dataset_name Name of dataset (e.g., "pbmc3k", "ifnb")
#' @param type Type of data to load (default: auto-detect for dataset)
#' @return Seurat object with raw counts
#' @export
#'
#' @examples
#' # Load PBMC 3k dataset for testing
#' seurat_obj <- load_seurat_data("pbmc3k")
#'
#' # Load interferon-beta dataset
#' seurat_obj <- load_seurat_data("ifnb")
load_seurat_data <- function(dataset_name, type = NULL) {

  # Set CRAN mirror
  options(repos = c(CRAN = "https://cloud.r-project.org"))

  # Check if SeuratData is installed
  if (!requireNamespace("SeuratData", quietly = TRUE)) {
    message("Installing SeuratData package (first time only)...")
    if (!requireNamespace("remotes", quietly = TRUE)) {
      install.packages("remotes")
    }
    remotes::install_github('satijalab/seurat-data')
  }

  library(SeuratData)

  message("Loading ", dataset_name, " dataset from SeuratData")

  # Install dataset if not available
  if (!dataset_name %in% InstalledData()$Dataset) {
    message("Installing ", dataset_name, " dataset (this may take a few minutes)...")
    InstallData(dataset_name)
  }

  # Auto-detect type for specific datasets
  if (is.null(type)) {
    if (dataset_name == "pbmc3k") {
      type <- "default"  # pbmc3k uses "default" not "filtered"
    } else {
      type <- "filtered"
    }
  }

  # Load dataset
  LoadData(dataset_name, type = type)

  # Get the object
  seurat_obj <- get(dataset_name)

  # Update object for Seurat v5 compatibility
  if (packageVersion("Seurat") >= "5.0.0") {
    message("Updating object for Seurat v5 compatibility...")
    # SeuratObject v5 compatibility fix
    if (!".cache" %in% slotNames(seurat_obj)) {
      seurat_obj <- UpdateSeuratObject(seurat_obj)
    }
  }

  message(sprintf("✓ Data loaded successfully: %d genes x %d cells",
                  nrow(seurat_obj), ncol(seurat_obj)))

  return(seurat_obj)
}

