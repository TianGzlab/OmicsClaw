#!/usr/bin/env Rscript
#' Hierarchical clustering with dendrogram visualization
#'
#' R implementation using base R stats + dendextend for enhanced dendrograms
#'
#' @param data Data matrix (samples x features)
#' @param n_clusters Number of clusters to cut tree
#' @param distance_method Distance metric ("euclidean", "correlation", "manhattan", "maximum")
#' @param linkage_method Linkage method ("ward.D2", "complete", "average", "single")

library(dendextend)  # For enhanced dendrograms
library(factoextra)  # For visualization

#' Perform hierarchical clustering
#'
#' @param data Numeric matrix or data frame (samples x features)
#' @param n_clusters Number of clusters (NULL for full tree)
#' @param distance_method Distance metric
#' @param linkage_method Agglomeration method
#' @param plot_dendrogram Whether to create dendrogram plot
#' @param output_path Base path for outputs
#' @return List with hclust object and cluster labels
hierarchical_clustering <- function(data,
                                     n_clusters = NULL,
                                     distance_method = "euclidean",
                                     linkage_method = "ward.D2",
                                     plot_dendrogram = TRUE,
                                     output_path = "dendrogram") {

  # Convert to matrix if needed
  if (!is.matrix(data)) {
    data <- as.matrix(data)
  }

  # Handle correlation distance (not built-in to dist())
  if (distance_method == "correlation") {
    # 1 - correlation as distance
    dist_matrix <- as.dist(1 - cor(t(data), method = "pearson"))
  } else {
    # Use built-in distance methods
    dist_matrix <- dist(data, method = distance_method)
  }

  # Perform hierarchical clustering
  hc <- hclust(dist_matrix, method = linkage_method)

  # Cut tree if n_clusters specified
  if (!is.null(n_clusters)) {
    cluster_labels <- cutree(hc, k = n_clusters)
  } else {
    cluster_labels <- NULL
  }

  # Plot dendrogram
  if (plot_dendrogram) {
    # Convert to dendrogram object for coloring
    dend <- as.dendrogram(hc)

    if (!is.null(n_clusters)) {
      # Color branches by cluster
      dend <- color_branches(dend, k = n_clusters)
      dend <- color_labels(dend, k = n_clusters)
    }

    # Save PNG
    png_path <- paste0(output_path, ".png")
    png(png_path, width = 12, height = 8, units = "in", res = 300)
    par(mar = c(5, 4, 4, 2))
    plot(dend, main = "Hierarchical Clustering Dendrogram",
         xlab = "", ylab = "Height", sub = "")
    if (!is.null(n_clusters)) {
      abline(h = hc$height[length(hc$height) - n_clusters + 1],
             col = "red", lty = 2, lwd = 2)
    }
    dev.off()
    message("Dendrogram saved to ", png_path)

    # Save SVG
    svg_path <- paste0(output_path, ".svg")
    svg(svg_path, width = 12, height = 8)
    par(mar = c(5, 4, 4, 2))
    plot(dend, main = "Hierarchical Clustering Dendrogram",
         xlab = "", ylab = "Height", sub = "")
    if (!is.null(n_clusters)) {
      abline(h = hc$height[length(hc$height) - n_clusters + 1],
             col = "red", lty = 2, lwd = 2)
    }
    dev.off()
    message("Dendrogram saved to ", svg_path)
  }

  # Print summary
  if (!is.null(cluster_labels)) {
    cluster_sizes <- table(cluster_labels)
    message("\nCluster sizes:")
    print(cluster_sizes)
  }

  return(list(
    hclust = hc,
    cluster_labels = cluster_labels,
    distance_matrix = dist_matrix
  ))
}

#' Determine optimal number of clusters
#'
#' @param data Numeric matrix (samples x features)
#' @param distance_method Distance metric
#' @param linkage_method Linkage method
#' @param k_range Range of k values to test
#' @param output_path Path for plots
#' @return List with optimal k and metrics
find_optimal_k <- function(data,
                            distance_method = "euclidean",
                            linkage_method = "ward.D2",
                            k_range = 2:10,
                            output_path = "optimal_k") {

  # Compute distance matrix
  if (distance_method == "correlation") {
    dist_matrix <- as.dist(1 - cor(t(data), method = "pearson"))
  } else {
    dist_matrix <- dist(data, method = distance_method)
  }

  # Perform clustering
  hc <- hclust(dist_matrix, method = linkage_method)

  # Method 1: Silhouette
  library(cluster)
  sil_scores <- sapply(k_range, function(k) {
    clusters <- cutree(hc, k = k)
    sil <- silhouette(clusters, dist_matrix)
    mean(sil[, "sil_width"])
  })

  # Method 2: Within-cluster sum of squares (for elbow)
  wss_scores <- sapply(k_range, function(k) {
    clusters <- cutree(hc, k = k)
    sum(sapply(unique(clusters), function(c) {
      cluster_data <- data[clusters == c, , drop = FALSE]
      sum(scale(cluster_data, scale = FALSE)^2)
    }))
  })

  # Find optimal k (max silhouette)
  optimal_k <- k_range[which.max(sil_scores)]

  # Plot results (PNG + SVG)
  for (ext in c(".png", ".svg")) {
    out_file <- paste0(output_path, ext)
    if (ext == ".png") {
      png(out_file, width = 10, height = 6, units = "in", res = 300)
    } else {
      svg(out_file, width = 10, height = 6)
    }

    par(mfrow = c(1, 2))

    # Elbow plot
    plot(k_range, wss_scores, type = "b", pch = 19,
         xlab = "Number of clusters (k)", ylab = "Within-cluster SS",
         main = "Elbow Method", col = "blue", lwd = 2)

    # Silhouette plot
    plot(k_range, sil_scores, type = "b", pch = 19,
         xlab = "Number of clusters (k)", ylab = "Average Silhouette Width",
         main = "Silhouette Method", col = "red", lwd = 2)
    abline(v = optimal_k, lty = 2, col = "darkred")
    text(optimal_k, max(sil_scores), paste("Optimal k =", optimal_k),
         pos = 4, col = "darkred")

    dev.off()
  }

  message("Optimal k analysis saved to ", output_path, ".png and .svg")
  message("Suggested optimal k: ", optimal_k, " (based on silhouette)")

  return(list(
    optimal_k = optimal_k,
    silhouette_scores = sil_scores,
    wss_scores = wss_scores,
    k_range = k_range
  ))
}

#' Example usage
#'
#' @examples
#' # Load data
#' data <- read.csv("expression_matrix.csv", row.names = 1)
#' data_matrix <- as.matrix(data)
#'
#' # Z-score normalization
#' data_scaled <- t(scale(t(data_matrix)))
#'
#' # Find optimal k
#' optimal <- find_optimal_k(
#'   data_scaled,
#'   distance_method = "euclidean",
#'   linkage_method = "ward.D2",
#'   k_range = 2:10,
#'   output_path = "results/optimal_k"
#' )
#'
#' # Perform clustering with optimal k
#' result <- hierarchical_clustering(
#'   data_scaled,
#'   n_clusters = optimal$optimal_k,
#'   distance_method = "euclidean",
#'   linkage_method = "ward.D2",
#'   plot_dendrogram = TRUE,
#'   output_path = "results/dendrogram"
#' )
#'
#' # Save cluster assignments
#' write.csv(
#'   data.frame(Sample = rownames(data), Cluster = result$cluster_labels),
#'   "results/cluster_assignments.csv",
#'   row.names = FALSE
#' )

# If run as script
if (sys.nframe() == 0) {
  message("Hierarchical clustering script for R")
  message("Usage: Rscript hierarchical_clustering.R")
  message("Or source this file and use hierarchical_clustering() function")
}

