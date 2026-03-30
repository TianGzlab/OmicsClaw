# Build co-expression network and detect modules

library(WGCNA)

#' Build co-expression network and detect modules
#'
#' @param datExpr Expression matrix (samples x genes)
#' @param power Soft-thresholding power
#' @param min_module_size Minimum genes per module
#' @param merge_cut_height Height for merging similar modules
#' @return List containing network object, module colors, and module labels
build_network <- function(datExpr, power, min_module_size = 30, merge_cut_height = 0.25) {

  cat("Building network with power =", power, "\n")

  # One-step network construction and module detection
  net <- blockwiseModules(
    datExpr,
    power = power,
    TOMType = "signed",
    networkType = "signed",
    minModuleSize = min_module_size,
    reassignThreshold = 0,
    mergeCutHeight = merge_cut_height,
    numericLabels = TRUE,
    pamRespectsDendro = FALSE,
    saveTOMs = FALSE,
    verbose = 3
  )

  # Convert numeric labels to colors
  module_colors <- labels2colors(net$colors)

  cat("\nModule detection complete:\n")
  cat("Number of modules:", length(unique(module_colors)) - 1, "(excluding grey/unassigned)\n")
  print(table(module_colors))

  return(list(
    net = net,
    module_colors = module_colors,
    module_labels = net$colors
  ))
}

