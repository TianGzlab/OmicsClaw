#' Run enrichment analysis on module genes
#'
#' Performs GO and KEGG enrichment analysis on genes within each module.
#' Supports multiple organisms with automatic installation of required packages.
#'
#' @param gene_info Data frame with gene-module assignments (must have 'gene' and 'module' columns)
#' @param organism Character string specifying organism. One of:
#'   "human", "mouse", "rat", "zebrafish", "fly", "worm", "yeast"
#'   Default: "human"
#' @param modules Character vector of modules to analyze (default: all non-grey modules)
#' @param ont GO ontology to use: "BP" (Biological Process), "MF" (Molecular Function),
#'   "CC" (Cellular Component), or "ALL". Default: "BP"
#' @param pvalueCutoff P-value cutoff for enrichment (default: 0.05)
#' @param qvalueCutoff Q-value cutoff for enrichment (default: 0.1)
#'
#' @return List of enrichment results per module. Each element contains a data frame
#'   with enriched GO terms, p-values, q-values, and gene lists.
#'
#' @details
#' Supported organisms and their annotation packages:
#' \itemize{
#'   \item human: org.Hs.eg.db
#'   \item mouse: org.Mm.eg.db
#'   \item rat: org.Rn.eg.db
#'   \item zebrafish: org.Dr.eg.db
#'   \item fly: org.Dm.eg.db
#'   \item worm: org.Ce.eg.db
#'   \item yeast: org.Sc.sgd.db
#' }
#'
#' The function automatically installs the required organism annotation package
#' if it's not already installed.
#'
#' @examples
#' \dontrun{
#' # Human genes
#' enrichment_results <- module_enrichment(gene_info, organism = "human")
#'
#' # Mouse genes
#' enrichment_results <- module_enrichment(gene_info, organism = "mouse")
#'
#' # Specific modules only
#' enrichment_results <- module_enrichment(gene_info, organism = "human",
#'                                        modules = c("blue", "turquoise"))
#' }
#'
#' @export
module_enrichment <- function(gene_info,
                              organism = "human",
                              modules = NULL,
                              ont = "BP",
                              pvalueCutoff = 0.05,
                              qvalueCutoff = 0.1) {

  # Set CRAN mirror if not set
  if (length(getOption("repos")) == 0 || getOption("repos")["CRAN"] == "@CRAN@") {
    options(repos = c(CRAN = "https://cloud.r-project.org"))
  }

  # Map organism names to annotation packages
  organism_map <- c(
    "human" = "org.Hs.eg.db",
    "mouse" = "org.Mm.eg.db",
    "rat" = "org.Rn.eg.db",
    "zebrafish" = "org.Dr.eg.db",
    "fly" = "org.Dm.eg.db",
    "worm" = "org.Ce.eg.db",
    "yeast" = "org.Sc.sgd.db"
  )

  # Validate organism
  if (!organism %in% names(organism_map)) {
    stop("Unsupported organism: ", organism, "\n",
         "Supported organisms: ", paste(names(organism_map), collapse = ", "))
  }

  org_pkg <- organism_map[organism]
  cat("Using organism:", organism, "(", org_pkg, ")\n")

  # Auto-install BiocManager if needed
  if (!requireNamespace("BiocManager", quietly = TRUE)) {
    cat("Installing BiocManager...\n")
    install.packages("BiocManager")
  }

  # Auto-install clusterProfiler if needed
  if (!requireNamespace("clusterProfiler", quietly = TRUE)) {
    cat("Installing clusterProfiler...\n")
    BiocManager::install("clusterProfiler", update = FALSE, ask = FALSE)
  }

  # Auto-install organism package if needed
  if (!requireNamespace(org_pkg, quietly = TRUE)) {
    cat("Installing", org_pkg, "annotation package (~50MB, ~2 min)...\n")
    BiocManager::install(org_pkg, update = FALSE, ask = FALSE)
  }

  # Load required libraries
  library(clusterProfiler)
  library(org_pkg, character.only = TRUE)

  # Get OrgDb object
  orgDb <- get(org_pkg)

  # Determine modules to analyze
  if (is.null(modules)) {
    modules <- unique(gene_info$module)
    modules <- modules[modules != "grey"]
  }

  cat("Analyzing", length(modules), "modules\n\n")

  enrichment_results <- list()

  for (mod in modules) {
    mod_genes <- gene_info$gene[gene_info$module == mod]

    cat("Module", mod, "(", length(mod_genes), "genes):\n")

    # GO enrichment
    tryCatch({
      ego <- enrichGO(
        gene = mod_genes,
        OrgDb = orgDb,
        keyType = "SYMBOL",
        ont = ont,
        pAdjustMethod = "BH",
        pvalueCutoff = pvalueCutoff,
        qvalueCutoff = qvalueCutoff
      )

      if (nrow(ego) > 0) {
        enrichment_results[[mod]] <- list(
          GO = as.data.frame(ego)
        )
        cat("  ✓ Found", nrow(ego), "enriched GO terms\n")

        # Show top 3 terms
        top_terms <- head(ego@result$Description, 3)
        for (i in seq_along(top_terms)) {
          cat("   ", i, ".", top_terms[i], "\n")
        }
      } else {
        cat("  No significant GO enrichment found\n")
      }
    }, error = function(e) {
      cat("  ✗ Error in GO enrichment:", e$message, "\n")
    })

    cat("\n")
  }

  if (length(enrichment_results) == 0) {
    warning("No enrichment results found for any module. ",
            "Check that gene symbols match the organism annotation.")
  }

  return(enrichment_results)
}

