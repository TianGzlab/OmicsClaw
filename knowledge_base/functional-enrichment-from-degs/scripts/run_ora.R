#' Run Over-Representation Analysis (ORA)
#'
#' Performs ORA to test if a gene list overlaps with pathways more than expected by chance.
#' Uses Fisher's exact test / hypergeometric test.
#'
#' @param gene_list Character vector of gene symbols
#' @param term2gene Data frame in TERM2GENE format (columns: term, gene)
#' @param background Character vector of all tested genes (important for correct statistics)
#' @param direction Description of gene list direction (e.g., "upregulated", "downregulated", "all")
#' @param pvalue_cutoff P-value cutoff for reporting (default: 0.05)
#' @param min_size Minimum gene set size (default: 10)
#' @param max_size Maximum gene set size (default: 500)
#' @return enrichResult object from clusterProfiler, or NULL if no genes
#' @export
#'
#' @examples
#' # Upregulated genes
#' ora_up <- run_ora(sig_genes$up, term2gene, sig_genes$background, direction = "upregulated")
#'
#' # Downregulated genes
#' ora_down <- run_ora(sig_genes$down, term2gene, sig_genes$background, direction = "downregulated")

library(clusterProfiler)

run_ora <- function(gene_list, term2gene, background, direction = "all",
                    pvalue_cutoff = 0.05, min_size = 10, max_size = 500) {

  if (length(gene_list) == 0) {
    message(sprintf("No %s genes for ORA", direction))
    return(NULL)
  }

  message(sprintf("\n=== Running ORA (%s, n=%d genes) ===", direction, length(gene_list)))

  ora_result <- enricher(
    gene = gene_list,
    TERM2GENE = term2gene,
    universe = background,  # CRITICAL: specify background
    pvalueCutoff = pvalue_cutoff,
    pAdjustMethod = "BH",
    minGSSize = min_size,
    maxGSSize = max_size
  )

  if (!is.null(ora_result) && nrow(ora_result@result) > 0) {
    n_sig <- sum(ora_result@result$p.adjust < 0.05)
    message(sprintf("ORA complete: %d significant gene sets (FDR < 0.05)", n_sig))
  } else {
    message("No significant enrichments found")
  }

  return(ora_result)
}

