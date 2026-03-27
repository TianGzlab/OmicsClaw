#!/usr/bin/env Rscript
# OmicsClaw R Dependencies Installation Script
#
# Installs all R packages required for OmicsClaw's R-based analysis methods:
#   • DESeq2      — differential expression (with apeglm/ashr LFC shrinkage)
#   • WGCNA       — weighted gene co-expression network analysis
#   • sva         — ComBat batch effect correction
#   • survival    — Kaplan-Meier, Cox PH, log-rank test
#   • clusterProfiler — GSEA / ORA pathway enrichment
#   • msigdbr     — MSigDB gene set database access
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
#
# Prerequisites:
#   R >= 4.3.0 on PATH
#   Internet access (CRAN / Bioconductor / GitHub)
#
# Usage:
#   Rscript install_r_dependencies.R                 # install all
#   Rscript install_r_dependencies.R --tier bulkrna  # install only bulk RNA-seq tier
#   Rscript install_r_dependencies.R --tier spatial   # install only spatial tier
#   Rscript install_r_dependencies.R --tier singlecell # install only single-cell tier
#   Rscript install_r_dependencies.R --check          # check only, no install
#   # or from within R:
#   source("install_r_dependencies.R")

cat("\n")
cat("========================================\n")
cat("OmicsClaw R Dependencies Installer\n")
cat("========================================\n\n")

# Set CRAN mirror
options(repos = c(CRAN = "https://cran.r-project.org"))

# ---------------------------------------------------------------------------
# CLI argument parsing: --tier <name> and --check
# ---------------------------------------------------------------------------

args <- commandArgs(trailingOnly = TRUE)
selected_tier <- NULL
check_only    <- FALSE

if ("--check" %in% args) {
  check_only <- TRUE
  args <- args[args != "--check"]
}
if ("--tier" %in% args) {
  tier_idx <- which(args == "--tier")
  if (tier_idx < length(args)) {
    selected_tier <- args[tier_idx + 1]
  }
}

valid_tiers <- c("bulkrna", "spatial", "singlecell", "all")
if (!is.null(selected_tier) && !(selected_tier %in% valid_tiers)) {
  cat(sprintf("ERROR: Unknown tier '%s'. Valid tiers: %s\n",
              selected_tier, paste(valid_tiers, collapse=", ")))
  quit(status = 1)
}
if (is.null(selected_tier)) selected_tier <- "all"

cat(sprintf("Mode: %s\n", ifelse(check_only, "CHECK ONLY", "INSTALL")))
cat(sprintf("Tier: %s\n\n", selected_tier))

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

install_if_missing <- function(pkg, source = "CRAN", install_cmd = NULL) {
  cat(sprintf("Checking %-20s [%s] ...", pkg, source))

  if (requireNamespace(pkg, quietly = TRUE)) {
    cat(" already installed\n")
    return(TRUE)
  }

  if (check_only) {
    cat(" MISSING\n")
    return(FALSE)
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
# Step 2 — CRAN packages (tier-filtered)
# ---------------------------------------------------------------------------

# Tag each CRAN package with its tier
cran_pkgs_with_tier <- list(
  # Tools (always needed)
  list(pkg="dplyr",       tier=c("all","singlecell","spatial")),
  list(pkg="ggplot2",     tier=c("all","singlecell","spatial")),
  list(pkg="Matrix",      tier=c("all","singlecell","spatial","bulkrna")),
  # Single-cell
  list(pkg="Seurat",      tier=c("all","singlecell")),
  list(pkg="sctransform", tier=c("all","singlecell")),
  list(pkg="harmony",     tier=c("all","singlecell")),
  list(pkg="SoupX",       tier=c("all","singlecell")),
  list(pkg="openxlsx",    tier=c("all","singlecell")),
  list(pkg="HGNChelper",  tier=c("all","singlecell")),
  # Spatial
  list(pkg="NMF",         tier=c("all","spatial")),
  list(pkg="mclust",      tier=c("all","spatial")),
  # Bulk RNA-seq
  list(pkg="survival",    tier=c("all","bulkrna")),
  list(pkg="msigdbr",     tier=c("all","bulkrna")),
  list(pkg="ashr",        tier=c("all","bulkrna"))
)

cat("\nStep 2: CRAN packages\n")
cat("---------------------\n")
for (info in cran_pkgs_with_tier) {
  if (selected_tier %in% info$tier) {
    record(install_if_missing(info$pkg, "CRAN"), paste0(info$pkg, " (CRAN)"))
  }
}

# ---------------------------------------------------------------------------
# Step 3 — Bioconductor packages (tier-filtered)
# ---------------------------------------------------------------------------

cat("\nStep 3: Bioconductor packages\n")
cat("-----------------------------\n")

bioc_pkgs <- list(
  # Single-cell
  list(name="SingleCellExperiment", tier=c("all","singlecell"),
       cmd="BiocManager::install('SingleCellExperiment', update=FALSE, ask=FALSE)"),
  list(name="scran",  tier=c("all","singlecell"),
       cmd="BiocManager::install('scran', update=FALSE, ask=FALSE)"),
  list(name="scuttle", tier=c("all","singlecell"),
       cmd="BiocManager::install('scuttle', update=FALSE, ask=FALSE)"),
  list(name="SingleR", tier=c("all","singlecell"),
       cmd="BiocManager::install('SingleR', update=FALSE, ask=FALSE)"),
  list(name="celldex", tier=c("all","singlecell"),
       cmd="BiocManager::install('celldex', update=FALSE, ask=FALSE)"),
  list(name="scDblFinder", tier=c("all","singlecell"),
       cmd="BiocManager::install('scDblFinder', update=FALSE, ask=FALSE)"),
  list(name="batchelor", tier=c("all","singlecell"),
       cmd="BiocManager::install('batchelor', update=FALSE, ask=FALSE)"),
  list(name="muscat",  tier=c("all","singlecell"),
       cmd="BiocManager::install('muscat', update=FALSE, ask=FALSE)"),
  # Spatial
  list(name="SpatialExperiment", tier=c("all","spatial"),
       cmd="BiocManager::install('SpatialExperiment', update=FALSE, ask=FALSE)"),
  list(name="zellkonverter", tier=c("all","spatial"),
       cmd="BiocManager::install('zellkonverter', update=FALSE, ask=FALSE)"),
  list(name="SPOTlight", tier=c("all","spatial"),
       cmd="BiocManager::install('SPOTlight', update=FALSE, ask=FALSE)"),
  # Bulk RNA-seq
  list(name="DESeq2",  tier=c("all","bulkrna","singlecell"),
       cmd="BiocManager::install('DESeq2', update=FALSE, ask=FALSE)"),
  list(name="apeglm",  tier=c("all","bulkrna"),
       cmd="BiocManager::install('apeglm', update=FALSE, ask=FALSE)"),
  list(name="edgeR",   tier=c("all","bulkrna"),
       cmd="BiocManager::install('edgeR', update=FALSE, ask=FALSE)"),
  list(name="limma",   tier=c("all","bulkrna"),
       cmd="BiocManager::install('limma', update=FALSE, ask=FALSE)"),
  list(name="WGCNA",   tier=c("all","bulkrna"),
       cmd="BiocManager::install('WGCNA', update=FALSE, ask=FALSE)"),
  list(name="sva",     tier=c("all","bulkrna"),
       cmd="BiocManager::install('sva', update=FALSE, ask=FALSE)"),
  list(name="clusterProfiler", tier=c("all","bulkrna"),
       cmd="BiocManager::install('clusterProfiler', update=FALSE, ask=FALSE)")
)

for (info in bioc_pkgs) {
  if (selected_tier %in% info$tier) {
    record(
      install_if_missing(info$name, "Bioconductor", info$cmd),
      paste0(info$name, " (Bioconductor)")
    )
  }
}

# ---------------------------------------------------------------------------
# Step 4 — GitHub packages (tier-filtered)
# ---------------------------------------------------------------------------

cat("\nStep 4: GitHub packages\n")
cat("Note: These may take several minutes to compile\n")
cat("-----------------------------------------------\n")

github_pkgs <- list(
  list(name="spacexr", repo="dmcable/spacexr", method="RCTD deconvolution",
       tier=c("all","spatial"),
       cmd="devtools::install_github('dmcable/spacexr', build_vignettes=FALSE, upgrade='never')"),
  list(name="CARD", repo="YMa-lab/CARD", method="CARD deconvolution",
       tier=c("all","spatial"),
       cmd="devtools::install_github('YMa-lab/CARD', upgrade='never')"),
  list(name="CellChat", repo="jinworks/CellChat", method="cell-cell communication",
       tier=c("all","singlecell","spatial"),
       cmd="devtools::install_github('jinworks/CellChat', upgrade='never')"),
  list(name="numbat", repo="kharchenkolab/numbat", method="CNV analysis",
       tier=c("all","spatial"),
       cmd="devtools::install_github('kharchenkolab/numbat', upgrade='never')"),
  list(name="SPARK", repo="xzhoulab/SPARK", method="SPARK-X spatially variable genes",
       tier=c("all","spatial"),
       cmd="devtools::install_github('xzhoulab/SPARK', upgrade='never')"),
  list(name="DoubletFinder", repo="chris-mcginnis-ucsf/DoubletFinder", method="doublet detection",
       tier=c("all","singlecell"),
       cmd="devtools::install_github('chris-mcginnis-ucsf/DoubletFinder', upgrade='never')")
)

for (info in github_pkgs) {
  if (selected_tier %in% info$tier) {
    cat(sprintf("  -> %s (%s) from GitHub:%s\n",
                info$name, info$method, info$repo))
    record(
      install_if_missing(info$name,
                         paste0("GitHub:", info$repo),
                         info$cmd),
      paste0(info$name, " (GitHub:", info$repo, ")")
    )
  }
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
  cat("\n  Bulk RNA-seq:\n")
  cat("  omicsclaw.py run bulkrna-de             --method deseq2     (DESeq2 + apeglm shrinkage)\n")
  cat("  omicsclaw.py run bulkrna-coexpression   --method wgcna      (WGCNA)\n")
  cat("  omicsclaw.py run bulkrna-enrichment     --method gsea       (clusterProfiler GSEA)\n")
  cat("  omicsclaw.py run bulkrna-enrichment     --method ora        (clusterProfiler ORA)\n")
  cat("  omicsclaw.py run bulkrna-survival                           (survival + Cox PH)\n")
  cat("  omicsclaw.py run bulkrna-batch-correction                   (sva::ComBat)\n")
  cat("\n  Spatial Transcriptomics:\n")
  cat("  omicsclaw.py run spatial-deconvolution  --method rctd       (spacexr)\n")
  cat("  omicsclaw.py run spatial-deconvolution  --method card       (CARD)\n")
  cat("  omicsclaw.py run spatial-deconvolution  --method spotlight  (SPOTlight)\n")
  cat("  omicsclaw.py run spatial-cell-communication --method cellchat (CellChat)\n")
  cat("  omicsclaw.py run spatial-cnv            --method numbat     (Numbat)\n")
  cat("  omicsclaw.py run spatial-svg-detection  --method sparkx     (SPARK-X)\n")
  cat("\n  Single-Cell:\n")
  cat("  omicsclaw.py run sc-cell-annotation     --method singler    (SingleR)\n")
  cat("  omicsclaw.py run sc-doublet-detection   --method scdblfinder (scDblFinder)\n")
  cat("  omicsclaw.py run sc-doublet-detection   --method doubletfinder (DoubletFinder)\n")
  cat("  omicsclaw.py run sc-ambient-removal     --method soupx      (SoupX)\n")
  cat("  omicsclaw.py run sc-batch-integration   --method fastmnn    (batchelor)\n")
  cat("  omicsclaw.py run sc-batch-integration   --method seurat_cca (Seurat CCA)\n")
  cat("  omicsclaw.py run sc-de                  --method deseq2_r   (DESeq2 pseudobulk)\n")
  cat("  omicsclaw.py run sc-cell-communication  --method cellchat_r (CellChat)\n\n")
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
