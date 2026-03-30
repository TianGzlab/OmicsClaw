#!/usr/bin/env Rscript

# Install all required packages for scrnaseq-seurat-core-analysis skill
cat("=== Installing Required Packages ===\n\n")
cat("This will take 10-15 minutes...\n\n")

# Set CRAN mirror
options(repos = c(CRAN = "https://cloud.r-project.org"))

# Install BiocManager if needed
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  cat("Installing BiocManager...\n")
  install.packages("BiocManager", quiet = TRUE)
}

# Core packages
core_packages <- c(
  "Seurat",
  "ggplot2",
  "ggprism",
  "dplyr",
  "patchwork"
)

cat("Installing core packages...\n")
for (pkg in core_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    cat("  Installing", pkg, "...\n")
    install.packages(pkg, quiet = TRUE)
  } else {
    cat("  ✓", pkg, "already installed\n")
  }
}

# Analysis packages
analysis_packages <- c(
  "DoubletFinder",
  "harmony",
  "SoupX"
)

cat("\nInstalling analysis packages...\n")
for (pkg in analysis_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    cat("  Installing", pkg, "...\n")
    install.packages(pkg, quiet = TRUE)
  } else {
    cat("  ✓", pkg, "already installed\n")
  }
}

# Bioconductor packages
bioc_packages <- c(
  "DESeq2",
  "muscat",
  "SingleR",
  "celldex"
)

cat("\nInstalling Bioconductor packages...\n")
for (pkg in bioc_packages) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    cat("  Installing", pkg, "...\n")
    BiocManager::install(pkg, update = FALSE, ask = FALSE, quiet = TRUE)
  } else {
    cat("  ✓", pkg, "already installed\n")
  }
}

# Install SeuratData for example datasets
if (!requireNamespace("SeuratData", quietly = TRUE)) {
  cat("\nInstalling SeuratData...\n")
  if (!requireNamespace("devtools", quietly = TRUE)) {
    install.packages("devtools", quiet = TRUE)
  }
  devtools::install_github('satijalab/seurat-data', quiet = TRUE, upgrade = "never")
} else {
  cat("\n✓ SeuratData already installed\n")
}

cat("\n=== Installation Complete ===\n\n")

# Verify installations
cat("Verifying package versions:\n")
packages_to_check <- c("Seurat", "ggplot2", "dplyr", "DESeq2", "SeuratData")
for (pkg in packages_to_check) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    version <- as.character(packageVersion(pkg))
    cat("  ✓", pkg, version, "\n")
  } else {
    cat("  ✗", pkg, "NOT INSTALLED\n")
  }
}

cat("\nAll packages ready for testing!\n")

