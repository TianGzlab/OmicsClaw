# Load and prepare expression data for WGCNA

library(WGCNA)

#' Load and prepare expression data for WGCNA
#'
#' @param expr_file Path to expression matrix (genes x samples)
#' @param meta_file Path to sample metadata
#' @param top_n_genes Number of most variable genes to keep
#' @param min_samples Minimum samples required
#' @return List containing datExpr, metadata, and gene info
prepare_wgcna_data <- function(expr_file, meta_file, top_n_genes = 5000, min_samples = 15) {

  # Load expression data
  if (grepl("\\.csv$", expr_file)) {
    expr_data <- read.csv(expr_file, row.names = 1, check.names = FALSE)
  } else {
    expr_data <- read.delim(expr_file, row.names = 1, check.names = FALSE)
  }

  # Load metadata
  if (grepl("\\.csv$", meta_file)) {
    meta_data <- read.csv(meta_file, row.names = 1)
  } else {
    meta_data <- read.delim(meta_file, row.names = 1)
  }

  cat("Expression matrix:", nrow(expr_data), "genes x", ncol(expr_data), "samples\n")
  cat("Metadata:", nrow(meta_data), "samples\n")

  # Check sample count
  if (ncol(expr_data) < min_samples) {
    warning(paste("Only", ncol(expr_data), "samples. WGCNA works best with 15+ samples."))
  }

  # Match samples between expression and metadata
  common_samples <- intersect(colnames(expr_data), rownames(meta_data))
  if (length(common_samples) < ncol(expr_data)) {
    cat("Using", length(common_samples), "samples present in both expression and metadata\n")
  }

  expr_data <- expr_data[, common_samples]
  meta_data <- meta_data[common_samples, , drop = FALSE]

  # Remove genes with too many missing values or zero variance
  good_genes <- apply(expr_data, 1, function(x) {
    sum(is.na(x)) < 0.1 * length(x) && var(x, na.rm = TRUE) > 0
  })
  expr_data <- expr_data[good_genes, ]
  cat("Genes after filtering:", nrow(expr_data), "\n")

  # Select top variable genes
  gene_var <- apply(expr_data, 1, var, na.rm = TRUE)
  top_genes <- names(sort(gene_var, decreasing = TRUE))[1:min(top_n_genes, nrow(expr_data))]
  expr_data <- expr_data[top_genes, ]
  cat("Selected top", nrow(expr_data), "variable genes\n")

  # Transpose for WGCNA (samples as rows, genes as columns)
  datExpr <- t(expr_data)

  # Check for outlier samples
  gsg <- goodSamplesGenes(datExpr, verbose = 3)
  if (!gsg$allOK) {
    datExpr <- datExpr[gsg$goodSamples, gsg$goodGenes]
    cat("Removed outlier samples/genes\n")
  }

  return(list(
    datExpr = datExpr,
    meta = meta_data,
    gene_info = data.frame(gene = colnames(datExpr), variance = gene_var[colnames(datExpr)])
  ))
}

