#!/usr/bin/env Rscript
# OmicsClaw R Dependencies Installation Script
#
# Installs all R packages required for OmicsClaw's R-based analysis methods:
#   • RCTD        — robust cell type decomposition (spacexr)
#   • SPOTlight   — NMF-based deconvolution (SPOTlight + Bioc deps)
#   • CARD        — conditional autoregressive deconvolution
#   • CellChat    — cell-cell communication inference
#   • Numbat      — copy number variation from scRNA-seq
#   • SPARK-X     — spatially variable gene detection
#   • SingleR     — reference-based cell type annotation
#   • scDblFinder — doublet detection
#   • SoupX       — ambient RNA removal
#   • batchelor   — fastMNN integration
#   • DESeq2      — pseudobulk differential expression
#
# Prerequisites:
#   R >= 4.3.0 on PATH
#   Internet access (CRAN / Bioconductor / GitHub)
#
# Usage:
#   Rscript install_r_dependencies.R
#   # or from within R:
#   source("install_r_dependencies.R")

cat("\n")
cat("========================================\n")
cat("OmicsClaw R Dependencies Installer\n")
cat("========================================\n\n")

# Set CRAN mirror
options(repos = c(CRAN = "https://cran.r-project.org"))

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

install_if_missing <- function(pkg, source = "CRAN", install_cmd = NULL) {
  cat(sprintf("Checking %-20s [%s] ...", pkg, source))

  if (requireNamespace(pkg, quietly = TRUE)) {
    cat(" already installed\n")
    return(TRUE)
  }

  cat(" installing...\n")

  tryCatch({
    if (!is.null(install_cmd)) {
      eval(parse(text = install_cmd))
    } else {
      install.packages(pkg, quiet = FALSE)
    }

    if (requireNamespace(pkg, quietly = TRUE)) {
      cat(sprintf("  [OK] %s\n", pkg))
      return(TRUE)
    } else {
      cat(sprintf("  [FAIL] %s — installation verification failed\n", pkg))
      return(FALSE)
    }
  }, error = function(e) {
    cat(sprintf("  [FAIL] %s — %s\n", pkg, conditionMessage(e)))
    return(FALSE)
  })
}

# Track results
failed_packages <- character(0)
success_count   <- 0L
total_count     <- 0L

record <- function(ok, label) {
  total_count   <<- total_count + 1L
  if (ok) {
    success_count <<- success_count + 1L
  } else {
    failed_packages <<- c(failed_packages, label)
  }
}

# ---------------------------------------------------------------------------
# Step 1 — Bootstrap tools
# ---------------------------------------------------------------------------

cat("Step 1: Bootstrap tools (devtools, BiocManager)\n")
cat("------------------------------------------------\n")

record(install_if_missing("devtools",    "CRAN"), "devtools (CRAN)")
record(install_if_missing("BiocManager", "CRAN"), "BiocManager (CRAN)")

# ---------------------------------------------------------------------------
# Step 2 — CRAN packages
# ---------------------------------------------------------------------------

cat("\nStep 2: CRAN packages\n")
cat("---------------------\n")

cran_pkgs <- c(
  "dplyr",        # data manipulation (CellChat, Numbat, scType)
  "ggplot2",      # plotting (CellChat, SPOTlight visualisation)
  "openxlsx",     # Excel file reading (scType marker DB)
  "HGNChelper",   # gene name validation (scType)
  "sctransform",  # SCTransform v2 normalisation
  "Matrix",       # sparse matrix operations
  "mclust",       # model-based clustering (GraphST)
  "Seurat",       # single-cell analysis framework (RCTD, Numbat)
  "NMF",          # non-negative matrix factorisation (SPOTlight)
  "harmony",      # Harmony integration in Seurat
  "SoupX"         # ambient RNA removal
)

for (pkg in cran_pkgs) {
  record(install_if_missing(pkg, "CRAN"), paste0(pkg, " (CRAN)"))
}

# ---------------------------------------------------------------------------
# Step 3 — Bioconductor packages
# ---------------------------------------------------------------------------

cat("\nStep 3: Bioconductor packages\n")
cat("-----------------------------\n")

bioc_pkgs <- list(
  list(name = "SingleCellExperiment",
       cmd  = "BiocManager::install('SingleCellExperiment', update=FALSE, ask=FALSE)"),
  list(name = "SpatialExperiment",
       cmd  = "BiocManager::install('SpatialExperiment',   update=FALSE, ask=FALSE)"),
  list(name = "scran",
       cmd  = "BiocManager::install('scran',               update=FALSE, ask=FALSE)"),
  list(name = "scuttle",
       cmd  = "BiocManager::install('scuttle',             update=FALSE, ask=FALSE)"),
  list(name = "SPOTlight",
       cmd  = "BiocManager::install('SPOTlight',           update=FALSE, ask=FALSE)"),
  list(name = "SingleR",
       cmd  = "BiocManager::install('SingleR',             update=FALSE, ask=FALSE)"),
  list(name = "celldex",
       cmd  = "BiocManager::install('celldex',             update=FALSE, ask=FALSE)"),
  list(name = "scDblFinder",
       cmd  = "BiocManager::install('scDblFinder',         update=FALSE, ask=FALSE)"),
  list(name = "batchelor",
       cmd  = "BiocManager::install('batchelor',           update=FALSE, ask=FALSE)"),
  list(name = "DESeq2",
       cmd  = "BiocManager::install('DESeq2',              update=FALSE, ask=FALSE)"),
  list(name = "muscat",
       cmd  = "BiocManager::install('muscat',              update=FALSE, ask=FALSE)"),
  list(name = "edgeR",
       cmd  = "BiocManager::install('edgeR',               update=FALSE, ask=FALSE)"),
  list(name = "limma",
       cmd  = "BiocManager::install('limma',               update=FALSE, ask=FALSE)")
)

for (info in bioc_pkgs) {
  record(
    install_if_missing(info$name, "Bioconductor", info$cmd),
    paste0(info$name, " (Bioconductor)")
  )
}

# ---------------------------------------------------------------------------
# Step 4 — GitHub packages
# ---------------------------------------------------------------------------

cat("\nStep 4: GitHub packages\n")
cat("Note: These may take several minutes to compile\n")
cat("-----------------------------------------------\n")

github_pkgs <- list(
  list(
    name   = "spacexr",
    repo   = "dmcable/spacexr",
    method = "RCTD deconvolution",
    cmd    = "devtools::install_github('dmcable/spacexr', build_vignettes=FALSE, upgrade='never')"
  ),
  list(
    name   = "CARD",
    repo   = "YMa-lab/CARD",
    method = "CARD deconvolution",
    cmd    = "devtools::install_github('YMa-lab/CARD', upgrade='never')"
  ),
  list(
    name   = "CellChat",
    repo   = "jinworks/CellChat",
    method = "cell-cell communication",
    cmd    = "devtools::install_github('jinworks/CellChat', upgrade='never')"
  ),
  list(
    name   = "numbat",
    repo   = "kharchenkolab/numbat",
    method = "CNV analysis",
    cmd    = "devtools::install_github('kharchenkolab/numbat', upgrade='never')"
  ),
  list(
    name   = "SPARK",
    repo   = "xzhoulab/SPARK",
    method = "SPARK-X spatially variable genes",
    cmd    = "devtools::install_github('xzhoulab/SPARK', upgrade='never')"
  ),
  list(
    name   = "DoubletFinder",
    repo   = "chris-mcginnis-ucsf/DoubletFinder",
    method = "doublet detection",
    cmd    = "devtools::install_github('chris-mcginnis-ucsf/DoubletFinder', upgrade='never')"
  )
)

for (info in github_pkgs) {
  cat(sprintf("  -> %s (%s) from GitHub:%s\n",
              info$name, info$method, info$repo))
  record(
    install_if_missing(info$name,
                       paste0("GitHub:", info$repo),
                       info$cmd),
    paste0(info$name, " (GitHub:", info$repo, ")")
  )
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

cat("\n")
cat("========================================\n")
cat("Installation Summary\n")
cat("========================================\n")
cat(sprintf("Installed: %d / %d packages\n", success_count, total_count))

if (length(failed_packages) > 0) {
  cat("\nFailed packages:\n")
  for (pkg in failed_packages) cat(sprintf("  - %s\n", pkg))
  cat("\nTroubleshooting:\n")
  cat("  1. Ensure R >= 4.3.0  :  R --version\n")
  cat("  2. Check internet access\n")
  cat("  3. On Linux, ensure system libs are present:\n")
  cat("       sudo apt install libcurl4-openssl-dev libssl-dev libxml2-dev\n")
  cat("  4. Retry failed packages individually (see commands above)\n")
  cat("  5. See docs/INSTALLATION.md for platform-specific notes\n\n")
} else {
  cat("\nAll R dependencies installed successfully!\n\n")
  cat("Enabled OmicsClaw R-based methods:\n")
  cat("  omicsclaw.py run deconv  --method rctd        (spacexr)\n")
  cat("  omicsclaw.py run deconv  --method card        (CARD)\n")
  cat("  omicsclaw.py run deconv  --method spotlight   (SPOTlight)\n")
  cat("  omicsclaw.py run comm    --method cellchat    (CellChat via rpy2)\n")
  cat("  omicsclaw.py run cnv     --method numbat      (Numbat)\n")
  cat("  omicsclaw.py run genes   --method sparkx      (SPARK-X)\n")
  cat("  omicsclaw.py run sc-cell-annotation --method singler        (SingleR)\n")
  cat("  omicsclaw.py run sc-doublet-detection --method scdblfinder  (scDblFinder)\n")
  cat("  omicsclaw.py run sc-doublet-detection --method doubletfinder (DoubletFinder)\n")
  cat("  omicsclaw.py run sc-ambient-removal --method soupx          (SoupX)\n")
  cat("  omicsclaw.py run sc-batch-integration --method fastmnn      (batchelor)\n")
  cat("  omicsclaw.py run sc-batch-integration --method seurat_cca   (Seurat CCA)\n")
  cat("  omicsclaw.py run sc-batch-integration --method seurat_rpca  (Seurat RPCA)\n")
  cat("  omicsclaw.py run sc-de --method deseq2_r                    (DESeq2 pseudobulk)\n")
  cat("  omicsclaw.py run sc-cell-communication --method cellchat_r  (CellChat)\n\n")
  cat("Python-only methods (no R needed):\n")
  cat("  omicsclaw.py run deconv  --method flashdeconv (default, fastest)\n")
  cat("  omicsclaw.py run deconv  --method cell2location\n")
  cat("  omicsclaw.py run deconv  --method destvi\n")
  cat("  omicsclaw.py run deconv  --method stereoscope\n")
  cat("  omicsclaw.py run deconv  --method tangram\n\n")
}

cat("R session info:\n")
cat(sprintf("  R version : %s\n", R.version.string))
cat(sprintf("  Platform  : %s\n", R.version$platform))
cat(sprintf("  libPaths  : %s\n", paste(.libPaths(), collapse="\n              ")))
cat("\nDone.\n")
