# Run complete WGCNA analysis workflow
# This script consolidates all WGCNA analysis steps into a single function

library(WGCNA)

#' Run complete WGCNA analysis
#'
#' @param datExpr Expression matrix (samples x genes)
#' @param meta Sample metadata with traits
#' @param traits Character vector of trait column names to correlate with modules
#' @param min_module_size Minimum genes per module (default: 30)
#' @param merge_cut_height Height for merging similar modules (default: 0.25)
#' @param n_hub Number of hub genes to identify per module (default: 10)
#' @param organism Organism for enrichment analysis ("human", "mouse", "rat", or NULL to skip)
#' @return List containing all WGCNA results
run_wgcna_analysis <- function(datExpr, meta, traits = NULL,
                               min_module_size = 30,
                               merge_cut_height = 0.25,
                               n_hub = 10,
                               organism = NULL) {

  cat("\n=== Starting WGCNA Analysis ===\n\n")

  # Step 1: Pick soft-thresholding power
  cat("Step 1/5: Selecting soft-thresholding power...\n")
  source("scripts/pick_soft_power.R")
  power_result <- pick_soft_power(datExpr, output_file = "soft_power_selection")
  soft_power <- power_result$power
  cat("  → Selected power:", soft_power, "\n\n")

  # Step 2: Build network and detect modules
  cat("Step 2/5: Building network and detecting modules...\n")
  source("scripts/build_network.R")
  network <- build_network(datExpr, power = soft_power,
                          min_module_size = min_module_size,
                          merge_cut_height = merge_cut_height)
  module_colors <- network$module_colors
  cat("  → Detected", length(unique(module_colors)) - 1, "modules\n\n")

  # Step 3: Correlate modules with traits
  cat("Step 3/5: Correlating modules with traits...\n")
  source("scripts/correlate_modules_traits.R")

  if (is.null(traits)) {
    # Use all numeric columns from metadata
    trait_cols <- sapply(meta, is.numeric)
    if (sum(trait_cols) == 0) {
      stop("No numeric trait columns found in metadata. Please specify trait columns.")
    }
    traits_data <- meta[, trait_cols, drop = FALSE]
  } else {
    traits_data <- meta[, traits, drop = FALSE]
  }

  trait_results <- correlate_modules_traits(datExpr, module_colors, traits_data)
  cat("  → Analyzed", ncol(traits_data), "traits\n\n")

  # Step 4: Identify hub genes
  cat("Step 4/5: Identifying hub genes...\n")
  source("scripts/identify_hub_genes.R")
  hub_results <- identify_hub_genes(datExpr, module_colors, soft_power, n_hub = n_hub)
  cat("  → Identified top", n_hub, "hub genes per module\n\n")

  # Step 5: Module enrichment (optional)
  enrichment_results <- NULL
  if (!is.null(organism)) {
    cat("Step 5/5: Running enrichment analysis...\n")
    source("scripts/module_enrichment.R")
    tryCatch({
      enrichment_results <- module_enrichment(hub_results$gene_info, organism = organism)
      cat("  → Enrichment analysis completed\n\n")
    }, error = function(e) {
      cat("  (Enrichment analysis skipped:", e$message, ")\n\n")
    })
  } else {
    cat("Step 5/5: Skipping enrichment analysis (no organism specified)\n\n")
  }

  cat("✓ WGCNA analysis completed successfully!\n\n")

  # Return all results
  return(list(
    datExpr = datExpr,
    meta = meta,
    power_result = power_result,
    soft_power = soft_power,
    network = network,
    module_colors = module_colors,
    trait_results = trait_results,
    hub_results = hub_results,
    enrichment_results = enrichment_results
  ))
}

