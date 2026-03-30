#!/usr/bin/env Rscript

cat("=== Fixing Installation Issues ===\n\n")

# Set CRAN mirror
options(repos = c(CRAN = "https://cloud.r-project.org"))

# Fix 1: Install remotes (lighter than devtools)
cat("1. Installing remotes (alternative to devtools)...\n")
if (!requireNamespace("remotes", quietly = TRUE)) {
  install.packages("remotes", dependencies = TRUE)
}
cat("✓ remotes installed\n\n")

# Fix 2: Install DoubletFinder from GitHub
cat("2. Installing DoubletFinder from GitHub...\n")
if (!requireNamespace("DoubletFinder", quietly = TRUE)) {
  tryCatch({
    remotes::install_github('chris-mcginnis-ucsf/DoubletFinder', upgrade = "never")
    cat("✓ DoubletFinder installed from GitHub\n")
  }, error = function(e) {
    cat("⚠ DoubletFinder install failed:", conditionMessage(e), "\n")
    cat("  Continuing without DoubletFinder (can skip doublet detection)\n")
  })
} else {
  cat("✓ DoubletFinder already installed\n")
}

cat("\n3. Installing SeuratData from GitHub...\n")
if (!requireNamespace("SeuratData", quietly = TRUE)) {
  tryCatch({
    remotes::install_github('satijalab/seurat-data', upgrade = "never")
    cat("✓ SeuratData installed from GitHub\n")
  }, error = function(e) {
    cat("⚠ SeuratData install failed:", conditionMessage(e), "\n")
  })
} else {
  cat("✓ SeuratData already installed\n")
}

cat("\n=== Fix Complete ===\n\n")

# Verify critical packages
cat("Verifying installation:\n")
critical_packages <- c("Seurat", "SeuratData", "DoubletFinder")
all_ok <- TRUE

for (pkg in critical_packages) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    version <- as.character(packageVersion(pkg))
    cat("✓", pkg, version, "\n")
  } else {
    cat("✗", pkg, "NOT INSTALLED\n")
    if (pkg == "SeuratData") all_ok <- FALSE
  }
}

if (!all_ok) {
  cat("\n⚠ SeuratData is required for example data. Trying alternative approach...\n")

  # Alternative: Download pbmc3k directly
  cat("\nAttempting direct pbmc3k download...\n")
  if (!requireNamespace("Seurat", quietly = TRUE)) {
    stop("Seurat is required")
  }

  library(Seurat)

  # Create a function to download pbmc3k directly
  cat("Downloading PBMC 3k dataset from 10X Genomics...\n")
  pbmc_url <- "https://cf.10xgenomics.com/samples/cell/pbmc3k/pbmc3k_filtered_gene_bc_matrices.tar.gz"

  if (!dir.exists("temp_data")) dir.create("temp_data")

  tryCatch({
    download.file(pbmc_url, "temp_data/pbmc3k.tar.gz", mode = "wb")
    untar("temp_data/pbmc3k.tar.gz", exdir = "temp_data")
    cat("✓ Downloaded and extracted pbmc3k data\n")
    cat("  Data location: temp_data/filtered_gene_bc_matrices/hg19/\n")
  }, error = function(e) {
    cat("✗ Download failed:", conditionMessage(e), "\n")
  })
}

cat("\nReady for testing!\n")

