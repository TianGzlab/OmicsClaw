#' Integration Quality Diagnostics for Seurat
#'
#' This module implements metrics to quantify batch integration quality,
#' including LISI (Local Inverse Simpson's Index) and ASW (Average Silhouette Width).
#'
#' For methodology and interpretation, see references/integration_methods.md
#'
#' Functions:
#'   - compute_lisi_scores(): Calculate iLISI and cLISI scores
#'   - compute_asw_scores(): Calculate silhouette width for batch and cell type
#'   - plot_integration_metrics(): Visualize integration quality
#'   - compare_integration_methods(): Compare multiple integration results
#'
#' Metrics:
#'   - iLISI: Integration LISI (higher = better batch mixing, target: n_batches)
#'   - cLISI: Cell type LISI (lower = better separation, target: 1)
#'   - Batch ASW: Silhouette for batch (lower = better mixing, target: ~0)
#'   - Cell type ASW: Silhouette for cell type (higher = better, target: >0.5)

library(Seurat)
library(dplyr)
library(ggplot2)
library(ggprism)


#' Compute LISI (Local Inverse Simpson's Index) scores
#'
#' LISI quantifies local batch mixing and cell type separation.
#'
#' @param seurat_obj Seurat object with integrated representation
#' @param batch_col Column in metadata containing batch labels
#' @param label_col Column in metadata containing cell type labels (optional)
#' @param reduction Reduction to use for distance computation (default: "pca")
#'   Options: "pca", "harmony", "umap"
#' @param perplexity Perplexity for local neighborhood (default: 30)
#' @param verbose Print summary statistics (default: TRUE)
#'
#' @return Data frame with iLISI and cLISI scores
#'
#' @export
compute_lisi_scores <- function(
  seurat_obj,
  batch_col,
  label_col = NULL,
  reduction = "pca",
  perplexity = 30,
  verbose = TRUE
) {
  # Check lisi package
  if (!requireNamespace("lisi", quietly = TRUE)) {
    stop("lisi package required. Install with: devtools::install_github('immunogenomics/lisi')")
  }

  library(lisi)

  if (verbose) {
    cat("Computing LISI scores...\n")
  }

  # Check inputs
  if (!batch_col %in% colnames(seurat_obj@meta.data)) {
    stop(sprintf("Batch column '%s' not found in metadata", batch_col))
  }

  if (!is.null(label_col) && !label_col %in% colnames(seurat_obj@meta.data)) {
    stop(sprintf("Label column '%s' not found in metadata", label_col))
  }

  if (!reduction %in% names(seurat_obj@reductions)) {
    stop(sprintf("Reduction '%s' not found in Seurat object", reduction))
  }

  # Get reduction embeddings
  X <- Embeddings(seurat_obj, reduction = reduction)

  # Prepare metadata
  if (is.null(label_col)) {
    metadata <- seurat_obj@meta.data[, batch_col, drop = FALSE]
  } else {
    metadata <- seurat_obj@meta.data[, c(batch_col, label_col)]
  }

  # Compute iLISI (batch mixing)
  if (verbose) {
    n_batches <- length(unique(seurat_obj@meta.data[[batch_col]]))
    cat(sprintf("  Computing iLISI (batch mixing)...\n"))
    cat(sprintf("    Batches: %d\n", n_batches))
    cat(sprintf("    Target: %.1f (perfect mixing)\n", n_batches))
  }

  ilisi <- compute_lisi(
    X,
    metadata,
    batch_col,
    perplexity = perplexity
  )

  results <- data.frame(ilisi = ilisi[, 1])
  rownames(results) <- colnames(seurat_obj)

  if (verbose) {
    cat(sprintf("    Mean iLISI: %.2f\n", mean(results$ilisi)))
    cat(sprintf("    Median iLISI: %.2f\n", median(results$ilisi)))
  }

  # Compute cLISI (cell type separation)
  if (!is.null(label_col)) {
    if (verbose) {
      n_labels <- length(unique(seurat_obj@meta.data[[label_col]]))
      cat(sprintf("  Computing cLISI (cell type separation)...\n"))
      cat(sprintf("    Cell types: %d\n", n_labels))
      cat(sprintf("    Target: 1.0 (perfect separation)\n"))
    }

    clisi <- compute_lisi(
      X,
      metadata,
      label_col,
      perplexity = perplexity
    )

    results$clisi <- clisi[, 1]

    if (verbose) {
      cat(sprintf("    Mean cLISI: %.2f\n", mean(results$clisi)))
      cat(sprintf("    Median cLISI: %.2f\n", median(results$clisi)))
    }
  }

  if (verbose) {
    cat("  LISI computation complete.\n\n")
  }

  return(results)
}


#' Compute Average Silhouette Width (ASW) scores
#'
#' ASW measures clustering quality for batch and cell type.
#'
#' @param seurat_obj Seurat object with integrated representation
#' @param batch_col Column in metadata containing batch labels
#' @param label_col Column in metadata containing cell type labels
#' @param reduction Reduction to use (default: "pca")
#' @param verbose Print summary statistics (default: TRUE)
#'
#' @return List with batch_asw and celltype_asw scores
#'
#' @export
compute_asw_scores <- function(
  seurat_obj,
  batch_col,
  label_col,
  reduction = "pca",
  verbose = TRUE
) {
  # Check cluster package
  if (!requireNamespace("cluster", quietly = TRUE)) {
    stop("cluster package required. Install with: install.packages('cluster')")
  }

  library(cluster)

  if (verbose) {
    cat("Computing ASW scores...\n")
  }

  # Check inputs
  if (!batch_col %in% colnames(seurat_obj@meta.data)) {
    stop(sprintf("Batch column '%s' not found in metadata", batch_col))
  }

  if (!label_col %in% colnames(seurat_obj@meta.data)) {
    stop(sprintf("Label column '%s' not found in metadata", label_col))
  }

  if (!reduction %in% names(seurat_obj@reductions)) {
    stop(sprintf("Reduction '%s' not found in Seurat object", reduction))
  }

  # Get reduction embeddings
  X <- Embeddings(seurat_obj, reduction = reduction)

  # Compute distance matrix (subsample if very large)
  n_cells <- nrow(X)
  if (n_cells > 10000) {
    cat(sprintf("  Warning: %d cells is large. Consider subsampling for faster computation.\n", n_cells))
  }

  dist_matrix <- dist(X, method = "euclidean")

  # Compute batch ASW (lower is better)
  if (verbose) {
    cat("  Computing batch ASW (target: ~0)...\n")
  }

  batch_labels <- as.numeric(factor(seurat_obj@meta.data[[batch_col]]))
  batch_sil <- silhouette(batch_labels, dist_matrix)
  batch_asw <- mean(batch_sil[, "sil_width"])

  if (verbose) {
    cat(sprintf("    Batch ASW: %.3f\n", batch_asw))
  }

  # Per-cell-type batch ASW
  celltype_labels <- seurat_obj@meta.data[[label_col]]
  batch_asw_per_label <- sapply(unique(celltype_labels), function(ct) {
    idx <- which(celltype_labels == ct)
    if (length(idx) > 1) {
      mean(batch_sil[idx, "sil_width"])
    } else {
      NA
    }
  })

  batch_asw_per_label_df <- data.frame(
    cell_type = names(batch_asw_per_label),
    batch_asw = as.numeric(batch_asw_per_label)
  )

  # Compute cell type ASW (higher is better)
  if (verbose) {
    cat("  Computing cell type ASW (target: >0.5)...\n")
  }

  ct_labels <- as.numeric(factor(seurat_obj@meta.data[[label_col]]))
  ct_sil <- silhouette(ct_labels, dist_matrix)
  celltype_asw <- mean(ct_sil[, "sil_width"])

  if (verbose) {
    cat(sprintf("    Cell type ASW: %.3f\n", celltype_asw))
  }

  # Per-batch cell type ASW
  batch_labels_char <- seurat_obj@meta.data[[batch_col]]
  celltype_asw_per_batch <- sapply(unique(batch_labels_char), function(b) {
    idx <- which(batch_labels_char == b)
    if (length(idx) > 1) {
      mean(ct_sil[idx, "sil_width"])
    } else {
      NA
    }
  })

  celltype_asw_per_batch_df <- data.frame(
    batch = names(celltype_asw_per_batch),
    celltype_asw = as.numeric(celltype_asw_per_batch)
  )

  if (verbose) {
    cat("  ASW computation complete.\n\n")
  }

  return(list(
    batch_asw = batch_asw,
    celltype_asw = celltype_asw,
    batch_asw_per_label = batch_asw_per_label_df,
    celltype_asw_per_batch = celltype_asw_per_batch_df
  ))
}


#' Create comprehensive integration quality plots
#'
#' @param seurat_obj Seurat object with integrated representation
#' @param batch_col Column in metadata containing batch labels
#' @param label_col Column in metadata containing cell type labels
#' @param reduction Reduction to use (default: "pca")
#' @param output_dir Output directory for plots (default: "results/integration_qc")
#' @param method_name Integration method name for titles (default: "Integration")
#'
#' @export
plot_integration_metrics <- function(
  seurat_obj,
  batch_col,
  label_col,
  reduction = "pca",
  output_dir = "results/integration_qc",
  method_name = "Integration"
) {
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  cat(sprintf("Generating integration quality plots for %s...\n", method_name))

  # 1. UMAP plots
  cat("  Creating UMAP plots...\n")

  # Compute UMAP if not present
  if (!"umap" %in% names(seurat_obj@reductions)) {
    cat("    Computing UMAP...\n")
    seurat_obj <- RunUMAP(seurat_obj, reduction = reduction, dims = 1:30, verbose = FALSE)
  }

  # UMAP by batch
  p1 <- DimPlot(seurat_obj, reduction = "umap", group.by = batch_col) +
    ggtitle(sprintf("%s: Batch", method_name)) +
    theme_prism()

  ggsave(
    file.path(output_dir, sprintf("%s_umap_batch.svg", method_name)),
    plot = p1,
    width = 8,
    height = 6,
    dpi = 300
  )

  # UMAP by cell type
  p2 <- DimPlot(seurat_obj, reduction = "umap", group.by = label_col) +
    ggtitle(sprintf("%s: Cell Type", method_name)) +
    theme_prism()

  ggsave(
    file.path(output_dir, sprintf("%s_umap_celltype.svg", method_name)),
    plot = p2,
    width = 8,
    height = 6,
    dpi = 300
  )

  # 2. Compute metrics
  cat("  Computing LISI and ASW scores...\n")
  lisi <- compute_lisi_scores(seurat_obj, batch_col, label_col, reduction, verbose = FALSE)
  asw <- compute_asw_scores(seurat_obj, batch_col, label_col, reduction, verbose = FALSE)

  # Add to metadata
  seurat_obj@meta.data$ilisi <- lisi$ilisi
  if ("clisi" %in% colnames(lisi)) {
    seurat_obj@meta.data$clisi <- lisi$clisi
  }

  # 3. LISI distribution plots
  cat("  Creating LISI distribution plots...\n")

  # iLISI violin plot
  plot_df <- data.frame(
    iLISI = seurat_obj@meta.data$ilisi,
    CellType = seurat_obj@meta.data[[label_col]]
  )

  p3 <- ggplot(plot_df, aes(x = CellType, y = iLISI, fill = CellType)) +
    geom_violin(show.legend = FALSE) +
    labs(
      title = sprintf("%s: Batch Mixing (iLISI)", method_name),
      x = "",
      y = "iLISI (higher = better mixing)"
    ) +
    theme_prism() +
    theme(axis.text.x = element_text(angle = 45, hjust = 1))

  ggsave(
    file.path(output_dir, sprintf("%s_ilisi_violin.svg", method_name)),
    plot = p3,
    width = 10,
    height = 6,
    dpi = 300
  )

  # cLISI violin plot (if available)
  if ("clisi" %in% colnames(seurat_obj@meta.data)) {
    plot_df <- data.frame(
      cLISI = seurat_obj@meta.data$clisi,
      Batch = seurat_obj@meta.data[[batch_col]]
    )

    p4 <- ggplot(plot_df, aes(x = Batch, y = cLISI, fill = Batch)) +
      geom_violin(show.legend = FALSE) +
      labs(
        title = sprintf("%s: Cell Type Separation (cLISI)", method_name),
        x = "",
        y = "cLISI (lower = better separation)"
      ) +
      theme_prism()

    ggsave(
      file.path(output_dir, sprintf("%s_clisi_violin.svg", method_name)),
      plot = p4,
      width = 8,
      height = 6,
      dpi = 300
    )
  }

  # 4. ASW summary plot
  cat("  Creating ASW summary plot...\n")

  asw_summary <- data.frame(
    Metric = c("Batch ASW\n(lower better)", "Cell Type ASW\n(higher better)"),
    Score = c(asw$batch_asw, asw$celltype_asw),
    Category = c("Batch Mixing", "Cell Type Separation")
  )

  p5 <- ggplot(asw_summary, aes(x = Metric, y = Score, fill = Category)) +
    geom_bar(stat = "identity", show.legend = FALSE) +
    labs(
      title = sprintf("%s: Average Silhouette Width", method_name),
      x = "",
      y = "ASW Score"
    ) +
    theme_prism()

  ggsave(
    file.path(output_dir, sprintf("%s_asw_summary.svg", method_name)),
    plot = p5,
    width = 6,
    height = 6,
    dpi = 300
  )

  # 5. Batch mixing heatmap
  cat("  Creating batch mixing heatmap...\n")

  batch_ct_counts <- table(
    seurat_obj@meta.data[[label_col]],
    seurat_obj@meta.data[[batch_col]]
  )
  batch_ct_proportions <- sweep(batch_ct_counts, 1, rowSums(batch_ct_counts), "/")

  # Save as heatmap using ComplexHeatmap
  if (requireNamespace("ComplexHeatmap", quietly = TRUE)) {
    library(ComplexHeatmap)

    svg(
      file.path(output_dir, sprintf("%s_batch_mixing_heatmap.svg", method_name)),
      width = 10,
      height = 8
    )

    Heatmap(
      batch_ct_proportions,
      name = "Proportion",
      column_title = sprintf("%s: Batch Distribution per Cell Type", method_name),
      row_title = "Cell Type",
      column_title_side = "top",
      cluster_rows = FALSE,
      cluster_columns = FALSE,
      cell_fun = function(j, i, x, y, width, height, fill) {
        grid.text(sprintf("%.2f", batch_ct_proportions[i, j]), x, y, gp = gpar(fontsize = 10))
      }
    )

    dev.off()
  }

  # Save metrics summary
  metrics_summary <- data.frame(
    method = method_name,
    representation = reduction,
    mean_ilisi = mean(lisi$ilisi),
    median_ilisi = median(lisi$ilisi),
    batch_asw = asw$batch_asw,
    celltype_asw = asw$celltype_asw,
    n_batches = length(unique(seurat_obj@meta.data[[batch_col]])),
    n_celltypes = length(unique(seurat_obj@meta.data[[label_col]]))
  )

  if ("clisi" %in% colnames(lisi)) {
    metrics_summary$mean_clisi <- mean(lisi$clisi)
    metrics_summary$median_clisi <- median(lisi$clisi)
  }

  metrics_file <- file.path(output_dir, sprintf("%s_metrics_summary.csv", method_name))
  write.csv(metrics_summary, metrics_file, row.names = FALSE)

  cat(sprintf("\n  Plots saved to: %s\n", output_dir))
  cat(sprintf("  Metrics summary saved to: %s\n\n", metrics_file))
}


#' Compare multiple integration methods
#'
#' @param seurat_obj Seurat object with multiple reductions
#' @param batch_col Column in metadata with batch labels
#' @param label_col Column in metadata with cell type labels
#' @param methods List of reduction names to compare
#' @param output_dir Output directory (default: "results/integration_comparison")
#'
#' @return Data frame with comparison results
#'
#' @export
compare_integration_methods <- function(
  seurat_obj,
  batch_col,
  label_col,
  methods,
  output_dir = "results/integration_comparison"
) {
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  cat("Comparing integration methods...\n")

  # Compute metrics for each method
  comparison_results <- list()

  for (method in methods) {
    if (!method %in% names(seurat_obj@reductions)) {
      cat(sprintf("  Warning: %s not found in reductions, skipping...\n", method))
      next
    }

    cat(sprintf("  Computing metrics for %s...\n", method))

    # LISI
    lisi <- compute_lisi_scores(seurat_obj, batch_col, label_col, method, verbose = FALSE)

    # ASW
    asw <- compute_asw_scores(seurat_obj, batch_col, label_col, method, verbose = FALSE)

    comparison_results[[method]] <- data.frame(
      Method = toupper(gsub("^X_", "", method)),
      Mean_iLISI = mean(lisi$ilisi),
      Mean_cLISI = if ("clisi" %in% colnames(lisi)) mean(lisi$clisi) else NA,
      Batch_ASW = asw$batch_asw,
      CellType_ASW = asw$celltype_asw
    )
  }

  results_df <- do.call(rbind, comparison_results)
  rownames(results_df) <- NULL

  # Save comparison table
  results_file <- file.path(output_dir, "integration_comparison.csv")
  write.csv(results_df, results_file, row.names = FALSE)
  cat(sprintf("\n  Comparison table saved to: %s\n", results_file))

  # Create comparison plots
  cat("  Creating comparison plots...\n")

  # iLISI comparison
  p1 <- ggplot(results_df, aes(x = Method, y = Mean_iLISI, fill = Method)) +
    geom_bar(stat = "identity", show.legend = FALSE) +
    labs(
      title = "Integration Quality: Batch Mixing (iLISI)",
      x = "",
      y = "Mean iLISI (higher = better)"
    ) +
    theme_prism()

  ggsave(
    file.path(output_dir, "comparison_ilisi.svg"),
    plot = p1,
    width = 8,
    height = 6,
    dpi = 300
  )

  # ASW comparison
  asw_long <- reshape2::melt(
    results_df[, c("Method", "Batch_ASW", "CellType_ASW")],
    id.vars = "Method",
    variable.name = "Metric",
    value.name = "Score"
  )

  p2 <- ggplot(asw_long, aes(x = Method, y = Score, fill = Metric)) +
    geom_bar(stat = "identity", position = "dodge") +
    labs(
      title = "Integration Quality: Average Silhouette Width",
      x = "",
      y = "ASW Score",
      fill = "Metric"
    ) +
    theme_prism()

  ggsave(
    file.path(output_dir, "comparison_asw.svg"),
    plot = p2,
    width = 10,
    height = 6,
    dpi = 300
  )

  cat(sprintf("\n  Comparison complete! Results in: %s\n\n", output_dir))

  return(results_df)
}


# Example usage
if (FALSE) {
  # Compute LISI scores
  lisi <- compute_lisi_scores(seurat_obj, "batch", "cell_type", reduction = "harmony")
  cat(sprintf("Mean iLISI: %.2f\n", mean(lisi$ilisi)))
  cat(sprintf("Mean cLISI: %.2f\n", mean(lisi$clisi)))

  # Compute ASW scores
  asw <- compute_asw_scores(seurat_obj, "batch", "cell_type", reduction = "harmony")
  cat(sprintf("Batch ASW: %.3f\n", asw$batch_asw))
  cat(sprintf("Cell type ASW: %.3f\n", asw$celltype_asw))

  # Generate quality plots
  plot_integration_metrics(seurat_obj, "batch", "cell_type", reduction = "harmony", method_name = "Harmony")

  # Compare multiple methods
  compare_integration_methods(seurat_obj, "batch", "cell_type", methods = c("pca", "harmony", "integrated"))
}

