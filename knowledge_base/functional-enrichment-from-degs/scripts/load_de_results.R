#' Load and Standardize Differential Expression Results
#'
#' Reads DE results from various tools (DESeq2, limma, edgeR) and standardizes
#' column names for downstream enrichment analysis.
#'
#' @param file_path Path to DE results file (CSV or TSV)
#' @return Data frame with standardized columns: gene, log2FC, padj, stat (if available)
#' @export
#'
#' @examples
#' de_results <- load_de_results("path/to/deseq2_results.csv")
#' head(de_results)

load_de_results <- function(file_path) {
  # Read file
  if (grepl("\\.csv$", file_path)) {
    df <- read.csv(file_path, stringsAsFactors = FALSE)
  } else {
    df <- read.delim(file_path, stringsAsFactors = FALSE)
  }

  # Standardize column names
  col_mapping <- c(
    "gene_symbol" = "gene", "Gene" = "gene", "SYMBOL" = "gene",
    "log2FoldChange" = "log2FC", "logFC" = "log2FC",
    "padj" = "padj", "adj.P.Val" = "padj", "FDR" = "padj",
    "stat" = "stat", "t" = "stat", "statistic" = "stat",
    "pvalue" = "pvalue", "P.Value" = "pvalue", "PValue" = "pvalue"
  )

  for (old_name in names(col_mapping)) {
    if (old_name %in% colnames(df)) {
      colnames(df)[colnames(df) == old_name] <- col_mapping[old_name]
    }
  }

  # Handle unnamed first column (row names)
  if (colnames(df)[1] %in% c("", "X", "Unnamed..0")) {
    colnames(df)[1] <- "gene"
  }

  # Validate required columns
  required <- c("gene", "log2FC", "padj")
  missing <- setdiff(required, colnames(df))
  if (length(missing) > 0) {
    stop(paste("Missing required columns:", paste(missing, collapse = ", ")))
  }

  # Remove NA and duplicates
  initial_n <- nrow(df)
  df <- df[!is.na(df$gene) & !is.na(df$log2FC) & !is.na(df$padj), ]
  df <- df[!duplicated(df$gene), ]

  message(sprintf("Loaded %d genes (removed %d rows with NA/duplicates)",
                  nrow(df), initial_n - nrow(df)))

  cat("\n✓ Data loaded successfully\n\n")

  return(df)
}

