#' Run Gene Set Enrichment Analysis (GSEA)
#'
#' Performs GSEA on a ranked gene list to identify enriched pathways.
#' Tests whether genes in pathways are coordinately up- or down-regulated.
#'
#' @param ranked_genes Named numeric vector (gene names = names, rank metric = values)
#' @param term2gene Data frame in TERM2GENE format (columns: term, gene)
#' @param min_size Minimum gene set size (default: 15)
#' @param max_size Maximum gene set size (default: 500)
#' @param pvalue_cutoff P-value cutoff for reporting (default: 0.05)
#' @param n_perm Number of permutations (default: 10000)
#' @return enrichResult object from clusterProfiler
#' @export
#'
#' @examples
#' gsea_result <- run_gsea(ranked_genes, term2gene, n_perm = 10000)
#' head(as.data.frame(gsea_result))

library(clusterProfiler)

run_gsea <- function(ranked_genes, term2gene, min_size = 15, max_size = 500,
                     pvalue_cutoff = 0.05, n_perm = 10000) {

  message("\n=== Running GSEA ===")

  gsea_result <- GSEA(
    geneList = ranked_genes,
    TERM2GENE = term2gene,
    minGSSize = min_size,
    maxGSSize = max_size,
    pvalueCutoff = pvalue_cutoff,
    pAdjustMethod = "BH",
    nPermSimple = n_perm,
    seed = TRUE,
    verbose = TRUE
  )

  n_sig <- sum(gsea_result@result$p.adjust < 0.05)
  message(sprintf("GSEA complete: %d significant gene sets (FDR < 0.05)", n_sig))

  cat("\n✓ Analysis completed successfully!\n\n")

  return(gsea_result)
}

