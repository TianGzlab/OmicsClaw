#' Load Example Data for Testing
#'
#' Functions to load example DE results for testing enrichment analysis workflows.
#' These are user-facing functions for learning and testing the skill.


#' Load Airway DE Results (human dexamethasone treatment)
#'
#' Himes et al. (2014) - RNA-seq of airway smooth muscle cells treated with dexamethasone
#' Runs DESeq2 analysis and returns DE results ready for enrichment analysis.
#'
#' @return Data frame with standardized DE results (gene, log2FC, padj, stat, pvalue)
#' @export
#'
#' @examples
#' de_results <- load_airway_de_results()
#' head(de_results)
load_airway_de_results <- function() {
  # Set CRAN mirror (required for package installation)
  if (length(getOption("repos")) == 0 || getOption("repos")["CRAN"] == "@CRAN@") {
    options(repos = c(CRAN = "https://cloud.r-project.org"))
  }

  # Install BiocManager if needed
  if (!requireNamespace("BiocManager", quietly = TRUE)) {
    cat("Installing BiocManager...\n")
    install.packages("BiocManager")
  }

  # Install required packages
  required_pkgs <- c("airway", "DESeq2", "org.Hs.eg.db")
  for (pkg in required_pkgs) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
      cat(sprintf("Installing %s package...\n", pkg))
      BiocManager::install(pkg, update = FALSE, ask = FALSE)
    }
  }

  # Load packages
  library(airway)
  library(DESeq2)
  library(org.Hs.eg.db)

  cat("Loading airway dataset and running DESeq2...\n")

  # Load data
  data("airway")

  # Create DESeqDataSet
  dds <- DESeqDataSet(airway, design = ~ cell + dex)

  # Pre-filter low count genes
  keep <- rowSums(counts(dds)) >= 10
  dds <- dds[keep, ]

  # Set reference level
  dds$dex <- relevel(dds$dex, ref = "untrt")

  # Run DESeq2 (takes ~30-60 seconds)
  cat("Running DESeq2 differential expression analysis (~1 min)...\n")
  dds <- DESeq(dds)

  # Get results
  res <- results(dds, contrast = c("dex", "trt", "untrt"), alpha = 0.05)

  # Convert to data frame with standardized column names
  de_results <- as.data.frame(res)
  de_results$ensembl_id <- rownames(de_results)
  rownames(de_results) <- NULL

  # Standardize column names for enrichment analysis
  colnames(de_results)[colnames(de_results) == "log2FoldChange"] <- "log2FC"

  # Convert Ensembl IDs to gene symbols (required for MSigDB)
  cat("Converting Ensembl IDs to gene symbols...\n")
  symbols <- mapIds(org.Hs.eg.db, keys = de_results$ensembl_id, column = "SYMBOL",
                    keytype = "ENSEMBL", multiVals = "first")
  de_results$gene <- as.character(symbols)

  # Remove rows without gene symbol mapping
  initial_count <- nrow(de_results)
  de_results <- de_results[!is.na(de_results$gene), ]
  cat(sprintf("  Mapped %d/%d Ensembl IDs to gene symbols\n", nrow(de_results), initial_count))

  # Reorder columns (keep ensembl_id for reference)
  de_results <- de_results[, c("gene", "ensembl_id", "baseMean", "log2FC", "lfcSE", "stat", "pvalue", "padj")]

  # Remove NA padj values
  de_results <- de_results[!is.na(de_results$padj), ]

  cat("\n✓ Data loaded successfully\n")
  cat("  Dataset: Human airway smooth muscle cells, dexamethasone treatment vs untreated\n")
  cat("  Total genes with symbols:", nrow(de_results), "\n")
  cat("  Significant genes (padj < 0.05):", sum(de_results$padj < 0.05, na.rm = TRUE), "\n")
  cat("  Upregulated (padj < 0.05, log2FC > 0):", sum(de_results$padj < 0.05 & de_results$log2FC > 0, na.rm = TRUE), "\n")
  cat("  Downregulated (padj < 0.05, log2FC < 0):", sum(de_results$padj < 0.05 & de_results$log2FC < 0, na.rm = TRUE), "\n")
  cat("  Expected enriched pathways: Inflammatory response, Glucocorticoid signaling, TNF-alpha signaling\n\n")

  return(de_results)
}


#' Load Pasilla DE Results (Drosophila RNAi knockdown)
#'
#' Brooks et al. (2011) - Effect of pasilla gene knockdown on splicing
#' Runs DESeq2 analysis and returns DE results ready for enrichment analysis.
#'
#' Note: Uses Drosophila data, so enrichment databases must support fly genes.
#'
#' @return Data frame with standardized DE results (gene, log2FC, padj, stat, pvalue)
#' @export
#'
#' @examples
#' de_results <- load_pasilla_de_results()
#' head(de_results)
load_pasilla_de_results <- function() {
  # Set CRAN mirror
  if (length(getOption("repos")) == 0 || getOption("repos")["CRAN"] == "@CRAN@") {
    options(repos = c(CRAN = "https://cloud.r-project.org"))
  }

  # Install BiocManager if needed
  if (!requireNamespace("BiocManager", quietly = TRUE)) {
    cat("Installing BiocManager...\n")
    install.packages("BiocManager")
  }

  # Install required packages
  required_pkgs <- c("pasilla", "DESeq2")
  for (pkg in required_pkgs) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
      cat(sprintf("Installing %s package (~50MB, ~1-2 minutes)...\n", pkg))
      BiocManager::install(pkg, update = FALSE, ask = FALSE)
    }
  }

  # Load packages
  library(pasilla)
  library(DESeq2)

  cat("Loading pasilla dataset and running DESeq2...\n")

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
  rownames(coldata) <- gsub("fb$", "", rownames(coldata))

  # Convert to factors
  coldata$condition <- factor(coldata$condition)
  coldata$type <- factor(coldata$type)

  # Reorder metadata to match count matrix
  coldata <- coldata[colnames(counts), , drop = FALSE]

  # Create DESeqDataSet
  dds <- DESeqDataSetFromMatrix(
    countData = counts,
    colData = coldata,
    design = ~ type + condition
  )

  # Pre-filter
  keep <- rowSums(counts(dds)) >= 10
  dds <- dds[keep, ]

  # Set reference level
  dds$condition <- relevel(dds$condition, ref = "untreated")

  # Run DESeq2
  cat("Running DESeq2 differential expression analysis (~1 min)...\n")
  dds <- DESeq(dds)

  # Get results
  res <- results(dds, contrast = c("condition", "treated", "untreated"), alpha = 0.05)

  # Convert to data frame with standardized column names
  de_results <- as.data.frame(res)
  de_results$gene <- rownames(de_results)
  rownames(de_results) <- NULL

  # Standardize column names
  colnames(de_results)[colnames(de_results) == "log2FoldChange"] <- "log2FC"

  # Reorder columns
  de_results <- de_results[, c("gene", "baseMean", "log2FC", "lfcSE", "stat", "pvalue", "padj")]

  # Remove NA values
  de_results <- de_results[!is.na(de_results$padj), ]

  cat("\n✓ Data loaded successfully\n")
  cat("  Dataset: Drosophila pasilla gene RNAi knockdown\n")
  cat("  Total genes:", nrow(de_results), "\n")
  cat("  Significant genes (padj < 0.05):", sum(de_results$padj < 0.05, na.rm = TRUE), "\n")
  cat("  Note: For enrichment analysis with Drosophila, use species-specific gene sets\n\n")

  return(de_results)
}

