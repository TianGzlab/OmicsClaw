# Pick soft-thresholding power for scale-free topology

library(WGCNA)

#' Pick soft-thresholding power for scale-free topology
#'
#' @param datExpr Expression matrix (samples x genes)
#' @param powers Vector of powers to test
#' @param output_file Path to save power selection plot
#' @return List with scale-free topology fit results and recommended power
pick_soft_power <- function(datExpr, powers = c(1:20), output_file = "soft_power_selection.svg") {

  # Calculate scale-free topology fit for each power
  sft <- pickSoftThreshold(datExpr, powerVector = powers, verbose = 5,
                           networkType = "signed")

  # Remove extension if provided
  output_file <- sub("\\.(svg|png)$", "", output_file)

  # Function to create the plot
  .make_power_plot <- function() {
    par(mfrow = c(1, 2))

    # Scale-free topology fit
    plot(sft$fitIndices[, 1], -sign(sft$fitIndices[, 3]) * sft$fitIndices[, 2],
         xlab = "Soft Threshold (power)", ylab = "Scale Free Topology Model Fit (signed R^2)",
         type = "n", main = "Scale Independence")
    text(sft$fitIndices[, 1], -sign(sft$fitIndices[, 3]) * sft$fitIndices[, 2],
         labels = powers, col = "red")
    abline(h = 0.85, col = "blue", lty = 2)

    # Mean connectivity
    plot(sft$fitIndices[, 1], sft$fitIndices[, 5],
         xlab = "Soft Threshold (power)", ylab = "Mean Connectivity",
         type = "n", main = "Mean Connectivity")
    text(sft$fitIndices[, 1], sft$fitIndices[, 5], labels = powers, col = "red")
  }

  # Save PNG (always)
  png_path <- paste0(output_file, ".png")
  png(png_path, width = 10, height = 5, units = "in", res = 300)
  .make_power_plot()
  dev.off()

  # Try SVG with fallback
  svg_path <- paste0(output_file, ".svg")
  tryCatch({
    svg(svg_path, width = 10, height = 5)
    .make_power_plot()
    dev.off()
  }, error = function(e) {
    # SVG failed silently
  })

  # Recommend power
  recommended_power <- sft$powerEstimate
  if (is.na(recommended_power)) {
    # If no power reaches R^2 > 0.85, pick the one closest
    recommended_power <- powers[which.max(-sign(sft$fitIndices[, 3]) * sft$fitIndices[, 2])]
  }

  cat("Recommended soft-thresholding power:", recommended_power, "\n")
  cat("Scale-free R^2:", sft$fitIndices[recommended_power, 2], "\n")
  cat("   Saved:", png_path, "\n")
  if (file.exists(svg_path)) {
    cat("   Saved:", svg_path, "\n")
  }

  return(list(sft = sft, power = recommended_power))
}

