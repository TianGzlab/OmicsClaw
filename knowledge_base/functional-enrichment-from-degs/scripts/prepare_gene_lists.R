#' Prepare Gene Lists for GSEA and ORA
#'
#' This script contains functions to prepare ranked gene lists (GSEA) and
#' significant gene lists (ORA) from differential expression results.

#' Create Ranked Gene List for GSEA
#'
#' Creates a ranked vector of genes sorted by test statistic or signed p-value.
#' Prefers test statistic if available, falls back to signed -log10(pvalue).
#'
#' @param df Data frame with columns: gene, log2FC, padj, and optionally stat or pvalue
#' @return Named numeric vector sorted by rank metric (descending)
#' @export
#'
#' @examples
#' ranked_genes <- create_ranked_list(de_results)
#' head(ranked_genes)

create_ranked_list <- function(df) {
  # Handle duplicate gene names by keeping the one with best (lowest) padj
  if (any(duplicated(df$gene))) {
    n_dup <- sum(duplicated(df$gene))
    message(sprintf("Found %d duplicate gene names, keeping best p-value for each", n_dup))
    df <- df[order(df$padj), ]  # Sort by padj
    df <- df[!duplicated(df$gene), ]  # Keep first (best) of each gene
  }

  # Prefer stat column, fall back to signed p-value
  if ("stat" %in% colnames(df)) {
    df$rank_metric <- df$stat
    message("Using test statistic for ranking (recommended)")
  } else if ("pvalue" %in% colnames(df)) {
    df$rank_metric <- sign(df$log2FC) * -log10(pmax(df$pvalue, 1e-300))
    message("Using signed -log10(pvalue) for ranking")
  } else {
    df$rank_metric <- sign(df$log2FC) * -log10(pmax(df$padj, 1e-300))
    message("Using signed -log10(padj) for ranking")
  }

  # Create named vector sorted by rank
  ranked_genes <- df$rank_metric
  names(ranked_genes) <- df$gene
  ranked_genes <- sort(ranked_genes, decreasing = TRUE)

  message(sprintf("Ranked list: %d genes", length(ranked_genes)))
  message(sprintf("  Top 3: %s", paste(head(names(ranked_genes), 3), collapse = ", ")))
  message(sprintf("  Bottom 3: %s", paste(tail(names(ranked_genes), 3), collapse = ", ")))

  return(ranked_genes)
}


#' Filter Significant Genes for ORA
#'
#' Filters DE results to create separate lists of upregulated and downregulated
#' genes for over-representation analysis.
#'
#' @param df Data frame with columns: gene, log2FC, padj
#' @param padj_thresh Adjusted p-value threshold (default: 0.05)
#' @param log2fc_thresh Absolute log2 fold change threshold (default: 1.0)
#' @return List with elements: up (upregulated genes), down (downregulated genes), background (all genes)
#' @export
#'
#' @examples
#' sig_genes <- filter_significant_genes(de_results, padj_thresh = 0.05, log2fc_thresh = 1.0)
#' length(sig_genes$up)
#' length(sig_genes$down)

filter_significant_genes <- function(df, padj_thresh = 0.05, log2fc_thresh = 1.0) {
  # Handle duplicate gene names by keeping the one with best (lowest) padj
  if (any(duplicated(df$gene))) {
    df <- df[order(df$padj), ]  # Sort by padj
    df <- df[!duplicated(df$gene), ]  # Keep first (best) of each gene
  }

  sig <- df[df$padj <= padj_thresh & abs(df$log2FC) >= log2fc_thresh, ]

  up_genes <- sig$gene[sig$log2FC > 0]
  down_genes <- sig$gene[sig$log2FC < 0]
  background <- df$gene

  message(sprintf("Significant genes (padj <= %g, |log2FC| >= %g):", padj_thresh, log2fc_thresh))
  message(sprintf("  Upregulated: %d", length(up_genes)))
  message(sprintf("  Downregulated: %d", length(down_genes)))
  message(sprintf("  Background: %d genes", length(background)))

  return(list(
    up = up_genes,
    down = down_genes,
    background = background
  ))
}

