# Identify hub genes within each module

library(WGCNA)

#' Identify hub genes within each module
#'
#' @param datExpr Expression matrix
#' @param module_colors Module assignments
#' @param power Soft-thresholding power
#' @param n_hub Number of hub genes per module
#' @return List with gene info and hub genes per module
identify_hub_genes <- function(datExpr, module_colors, power, n_hub = 10) {

  # Calculate module membership (correlation with module eigengene)
  MEs <- moduleEigengenes(datExpr, colors = module_colors)$eigengenes

  # Calculate gene-module membership
  gene_module_membership <- as.data.frame(cor(datExpr, MEs, use = "p"))
  colnames(gene_module_membership) <- gsub("ME", "MM_", colnames(gene_module_membership))

  # Calculate intramodular connectivity
  adj <- adjacency(datExpr, power = power, type = "signed")

  # Get connectivity for each gene
  connectivity <- intramodularConnectivity(adj, module_colors)

  # Combine results
  gene_info <- data.frame(
    gene = colnames(datExpr),
    module = module_colors,
    kWithin = connectivity$kWithin,
    kOut = connectivity$kOut,
    kTotal = connectivity$kTotal,
    stringsAsFactors = FALSE
  )

  # Add module membership
  gene_info <- cbind(gene_info, gene_module_membership)

  # Identify hub genes per module
  hub_genes <- list()
  modules <- unique(module_colors)
  modules <- modules[modules != "grey"]  # Exclude unassigned

  for (mod in modules) {
    mod_genes <- gene_info[gene_info$module == mod, ]
    mm_col <- paste0("MM_", mod)

    if (mm_col %in% colnames(mod_genes)) {
      # Rank by module membership and connectivity
      mod_genes$hub_score <- abs(mod_genes[[mm_col]]) * mod_genes$kWithin
      mod_genes <- mod_genes[order(-mod_genes$hub_score), ]
      hub_genes[[mod]] <- head(mod_genes, n_hub)
    }
  }

  cat("Identified hub genes for", length(hub_genes), "modules\n")

  return(list(
    gene_info = gene_info,
    hub_genes = hub_genes
  ))
}

