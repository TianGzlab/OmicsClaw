# Software Requirements and Installation

Complete guide to installing and configuring all required software for the experimental-design-statistics workflow.

---

## Required R Packages

### Core Bioconductor Packages

| Package | Version | License | Commercial Use | Purpose |
|---------|---------|---------|----------------|---------|
| **RNASeqPower** | ≥1.36.0 | GPL-2+ | ✅ Permitted | RNA-seq power calculations |
| **ssizeRNA** | ≥1.4.0 | GPL-2+ | ✅ Permitted | ATAC-seq and general sample size |
| **DESeq2** | ≥1.40.0 | LGPL | ✅ Permitted | Dispersion estimation from pilot data |
| **powsimR** | ≥1.2.3 | GPL-3 | ✅ Permitted | Single-cell RNA-seq power analysis |
| **sva** | ≥3.48.0 | Artistic-2.0 | ✅ Permitted | Surrogate variable analysis |
| **qvalue** | ≥2.32.0 | LGPL | ✅ Permitted | Q-value multiple testing correction |
| **IHW** | ≥1.28.0 | Artistic-2.0 | ✅ Permitted | Independent hypothesis weighting |

### Core CRAN Packages

| Package | Version | License | Commercial Use | Purpose |
|---------|---------|---------|----------------|---------|
| **osat** | ≥0.1.3 | Artistic-2.0 | ✅ Permitted | Optimal sample assignment to batches |
| **ggplot2** | ≥3.4.0 | MIT | ✅ Permitted | Data visualization |
| **ggprism** | ≥1.0.4 | GPL-3 | ✅ Permitted | Publication-quality themes |
| **pwr** | ≥1.3 | GPL-3+ | ✅ Permitted | General power calculations |

### Optional Advanced Packages

| Package | Version | License | Use Case |
|---------|---------|---------|----------|
| **PROPER** | ≥1.32.0 | GPL-2+ | Simulation-based power analysis |
| **ashr** | ≥2.2-54 | GPL-3+ | Adaptive shrinkage for FDR |
| **locfdr** | ≥1.1-8 | GPL-2+ | Local FDR estimates |
| **blockTools** | ≥0.6-3 | GPL-2+ | Incomplete block designs |
| **SingleCellExperiment** | ≥1.22.0 | GPL-3 | scRNA-seq data structures |

---

## Installation Instructions

### Step 1: Install R and RStudio

Ensure you have R ≥4.0 and optionally RStudio for easier development.

- **R:** Download from [https://cran.r-project.org/](https://cran.r-project.org/)
- **RStudio:** Download from [https://posit.co/products/open-source/rstudio/](https://posit.co/products/open-source/rstudio/)

### Step 2: Install Bioconductor Manager

```r
if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")
```

### Step 3: Install Core Bioconductor Packages

```r
BiocManager::install(c(
  "RNASeqPower",
  "ssizeRNA",
  "DESeq2",
  "powsimR",
  "sva",
  "qvalue",
  "IHW"
))
```

### Step 4: Install Core CRAN Packages

```r
install.packages(c(
  "osat",
  "ggplot2",
  "ggprism",
  "pwr"
))
```

### Step 5: Install Optional Advanced Packages

```r
# Optional: Only if you need advanced features
BiocManager::install(c("PROPER", "SingleCellExperiment"))
install.packages(c("ashr", "locfdr", "blockTools"))
```

### Step 6: Verify Installation

```r
# Test that all core packages load
library(RNASeqPower)
library(ssizeRNA)
library(DESeq2)
library(osat)
library(qvalue)
library(IHW)
library(ggplot2)
library(ggprism)

# If all load without errors, installation is successful
print("✓ All core packages installed successfully")
```

---

## Complete Installation Script

Copy and run this complete script:

```r
# Complete installation script for experimental-design-statistics workflow
# Run this once to install all required packages

cat("Installing experimental-design-statistics workflow dependencies...\n\n")

# Install BiocManager
if (!requireNamespace("BiocManager", quietly = TRUE)) {
  cat("Installing BiocManager...\n")
  install.packages("BiocManager")
}

# Core Bioconductor packages
cat("\nInstalling core Bioconductor packages...\n")
BiocManager::install(c(
  "RNASeqPower",
  "ssizeRNA",
  "DESeq2",
  "powsimR",
  "sva",
  "qvalue",
  "IHW"
), update = FALSE, ask = FALSE)

# Core CRAN packages
cat("\nInstalling core CRAN packages...\n")
install.packages(c(
  "osat",
  "ggplot2",
  "ggprism",
  "pwr"
), repos = "https://cran.r-project.org")

# Verify installation
cat("\n\nVerifying installation...\n")
packages_to_test <- c("RNASeqPower", "ssizeRNA", "DESeq2", "osat", "qvalue", "IHW", "ggplot2", "ggprism")
all_installed <- TRUE

for (pkg in packages_to_test) {
  if (requireNamespace(pkg, quietly = TRUE)) {
    cat("✓", pkg, "\n")
  } else {
    cat("✗", pkg, "FAILED\n")
    all_installed <- FALSE
  }
}

if (all_installed) {
  cat("\n✓ All core packages installed successfully!\n")
  cat("You are ready to use the experimental-design-statistics workflow.\n")
} else {
  cat("\n✗ Some packages failed to install. Please check error messages above.\n")
}
```

---

## License Compliance for Commercial AI Use

### All Packages Verified for Commercial Use

This workflow is designed for use in a **commercial AI agent tool**. All recommended software has been verified for compatibility:

**GPL/LGPL Licenses (GPL-2+, GPL-3, LGPL):**
- Permit commercial use
- Require source code sharing only if distributing modified binaries
- **For AI agent use:** No distribution of binaries occurs, only execution
- **Compliance:** ✅ Permitted for commercial AI use

**MIT License:**
- Highly permissive
- Allows commercial use with attribution
- **Compliance:** ✅ Permitted for commercial AI use

**Artistic-2.0 License (Bioconductor standard):**
- Permits commercial use
- Standard for Bioconductor packages
- **Compliance:** ✅ Permitted for commercial AI use

### Attribution Requirements

When using these methods in publications or reports:

1. **Cite primary papers:**
   - RNASeqPower: Hart et al. (2013) J Comput Biol
   - DESeq2: Love et al. (2014) Genome Biology
   - IHW: Ignatiadis et al. (2016) Nature Methods
   - See main workflow document for complete citations

2. **Cite software packages:**
   - Include package names and versions in methods sections
   - Example: "Power analysis performed using RNASeqPower v1.36.0"

3. **No licensing fees required** for any of these packages

---

## Troubleshooting Installation

### Issue: BiocManager installation fails

```r
# Try specifying CRAN mirror explicitly
install.packages("BiocManager", repos = "https://cran.r-project.org")
```

### Issue: Bioconductor package installation fails

```r
# Update Bioconductor to latest version
BiocManager::install(version = "3.18")  # Use latest version number

# Then retry package installation
BiocManager::install("RNASeqPower")
```

### Issue: powsimR installation is very slow

powsimR is a large package with many dependencies. Installation can take 10-30 minutes.

```r
# Install with more verbose output to monitor progress
BiocManager::install("powsimR", update = TRUE, ask = FALSE, verbose = TRUE)
```

### Issue: Package version conflicts

```r
# Update all packages to latest compatible versions
BiocManager::install(ask = FALSE)
```

### Issue: Compilation errors on macOS

Ensure you have Xcode Command Line Tools installed:

```bash
xcode-select --install
```

### Issue: Compilation errors on Linux

Install required development libraries:

```bash
# Ubuntu/Debian
sudo apt-get install libcurl4-openssl-dev libssl-dev libxml2-dev

# CentOS/RHEL
sudo yum install libcurl-devel openssl-devel libxml2-devel
```

---

## Alternative: Docker Container (Future)

A Docker container with all dependencies pre-installed is planned for future releases. This will provide:

- Pre-configured environment
- No installation required
- Consistent across platforms
- Isolated from system R installation

Check repository for updates on Docker availability.

---

## System Requirements

**Minimum:**
- R ≥4.0
- 4 GB RAM
- 2 GB free disk space

**Recommended:**
- R ≥4.2
- 8 GB RAM (for powsimR simulations)
- 5 GB free disk space

**Operating Systems:**
- macOS (Intel or Apple Silicon)
- Linux (Ubuntu, CentOS, Debian)
- Windows 10/11

---

## Getting Help

**Package-specific issues:**
- Check package documentation: `?packageName`
- Visit Bioconductor support: [https://support.bioconductor.org/](https://support.bioconductor.org/)
- CRAN package pages: `https://cran.r-project.org/package=packageName`

**Workflow-specific issues:**
- Check [troubleshooting_guide.md](troubleshooting_guide.md)
- Review [README.md](../README.md) for examples

---

**Last Updated:** 2026-01-28
**Maintained by:** Knowhows Repository
