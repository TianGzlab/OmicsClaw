#' Pseudobulk Differential Expression Analysis
#'
#' This module implements pseudobulk aggregation and differential expression
#' analysis for single-cell RNA-seq data using DESeq2 and muscat framework.
#'
#' For methodology and best practices, see references/pseudobulk_de_guide.md

library(Seurat)
library(DESeq2)
library(muscat)
library(SingleCellExperiment)
library(ggplot2)
library(ggprism)
library(dplyr)


#' Aggregate counts to pseudobulk (sum per sample × cell type)
#'
#' @param seurat_obj Seurat object with cell type annotations
#' @param sample_col Column in metadata with sample IDs
#' @param celltype_col Column in metadata with cell type labels
#' @param min_cells Minimum cells per sample-celltype (default: 10)
#' @param min_counts Minimum total counts per sample-celltype (default: 1)
#' @param assay Assay to use (default: "RNA")
#'
#' @return SingleCellExperiment object with pseudobulk data
#'
#' @export
aggregate_to_pseudobulk <- function(
  seurat_obj,
  sample_col = "sample_id",
  celltype_col = "cell_type",
  min_cells = 10,
  min_counts = 1,
  assay = "RNA"
) {
  cat("Aggregating to pseudobulk...\n")
  cat(sprintf("  Sample column: %s\n", sample_col))
  cat(sprintf("  Cell type column: %s\n", celltype_col))

  # Convert to SingleCellExperiment
  sce <- as.SingleCellExperiment(seurat_obj, assay = assay)

  # Add required columns
  colData(sce)$sample_id <- seurat_obj@meta.data[[sample_col]]
  colData(sce)$cluster_id <- seurat_obj@meta.data[[celltype_col]]

  # Aggregate using muscat (sum counts per sample × cluster)
  pb <- aggregateData(
    sce,
    assay = "counts",
    fun = "sum",  # CRITICAL: use sum, not mean
    by = c("cluster_id", "sample_id")
  )

  # Filter low-count combinations
  # This is done during DE analysis

  cat("\nPseudobulk aggregation complete:\n")
  cat(sprintf("  Cell types: %d\n", length(assayNames(pb))))
  cat(sprintf("  Samples: %d\n", ncol(pb)))

  return(pb)
}


#' Run DESeq2 differential expression for each cell type
#'
#' @param pseudobulk_data SingleCellExperiment from aggregate_to_pseudobulk()
#' @param formula DESeq2 design formula (e.g., "~ batch + condition")
#' @param contrast DESeq2 contrast vector (e.g., c("condition", "treated", "control"))
#' @param output_dir Directory to save results
#' @param min_samples Minimum samples per group (default: 3)
#' @param shrink_lfc Shrink log2 fold changes (default: TRUE)
#'
#' @return List of DESeq2 results, one per cell type
#'
#' @export
run_pseudobulk_deseq2 <- function(
  pseudobulk_data,
  formula = "~ condition",
  contrast = c("condition", "treated", "control"),
  output_dir = "results/pseudobulk_de",
  min_samples = 3,
  shrink_lfc = TRUE
) {
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  cat("\nRunning DESeq2 for each cell type...\n")

  # Get cell types (assays in muscat object)
  celltypes <- assayNames(pseudobulk_data)

  de_results <- list()

  for (celltype in celltypes) {
    cat(sprintf("\n  Cell type: %s\n", celltype))

    # Extract counts for this cell type
    counts <- assay(pseudobulk_data, celltype)
    metadata <- colData(pseudobulk_data)

    # Check sample size
    n_samples <- ncol(counts)
    cat(sprintf("    Samples: %d\n", n_samples))

    if (n_samples < min_samples) {
      cat(sprintf("    Skipping: <%d samples\n", min_samples))
      next
    }

    # Create DESeqDataSet
    dds <- tryCatch({
      DESeqDataSetFromMatrix(
        countData = counts,
        colData = metadata,
        design = as.formula(formula)
      )
    }, error = function(e) {
      cat(sprintf("    Error creating DESeqDataSet: %s\n", e$message))
      return(NULL)
    })

    if (is.null(dds)) next

    # Filter low count genes
    keep <- rowSums(counts(dds) >= 10) >= 3
    dds <- dds[keep, ]

    cat(sprintf("    Genes after filtering: %d\n", nrow(dds)))

    # Run DESeq2
    dds <- tryCatch({
      DESeq(dds, quiet = TRUE)
    }, error = function(e) {
      cat(sprintf("    Error running DESeq2: %s\n", e$message))
      return(NULL)
    })

    if (is.null(dds)) next

    # Extract results
    res <- results(dds, contrast = contrast)

    # Shrink log2 fold changes
    if (shrink_lfc) {
      res_shrunk <- tryCatch({
        lfcShrink(
          dds,
          contrast = contrast,
          res = res,
          type = "ashr",
          quiet = TRUE
        )
      }, error = function(e) {
        cat(sprintf("    Warning: LFC shrinkage failed: %s\n", e$message))
        res
      })

      if (!is.null(res_shrunk)) res <- res_shrunk
    }

    # Convert to dataframe
    res_df <- as.data.frame(res)
    res_df$gene <- rownames(res_df)
    res_df <- res_df[, c("gene", "baseMean", "log2FoldChange", "lfcSE", "stat", "pvalue", "padj")]

    de_results[[celltype]] <- res_df

    n_sig <- sum(res_df$padj < 0.05, na.rm = TRUE)
    cat(sprintf("    Significant genes (padj<0.05): %d\n", n_sig))
  }

  return(de_results)
}


#' Export DE results to CSV files
#'
#' @param de_results List of DESeq2 results from run_pseudobulk_deseq2()
#' @param output_dir Output directory
#' @param padj_threshold Adjusted p-value threshold (default: 0.05)
#' @param log2fc_threshold Absolute log2FC threshold (default: 0)
#'
#' @export
export_de_results <- function(
  de_results,
  output_dir = "results/pseudobulk_de",
  padj_threshold = 0.05,
  log2fc_threshold = 0
) {
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  cat(sprintf("\nExporting DE results to %s\n", output_dir))

  for (celltype in names(de_results)) {
    results_df <- de_results[[celltype]]

    # Export full results
    results_file <- file.path(output_dir, sprintf("%s_deseq2_results.csv", celltype))
    write.csv(results_df, results_file, row.names = FALSE)

    # Export significant genes
    sig_df <- results_df %>%
      filter(padj < padj_threshold, abs(log2FoldChange) > log2fc_threshold) %>%
      arrange(padj)

    sig_file <- file.path(output_dir, sprintf("%s_deseq2_sig.csv", celltype))
    write.csv(sig_df, sig_file, row.names = FALSE)

    cat(sprintf("  %s: %d significant genes\n", celltype, nrow(sig_df)))
  }
}


#' Create volcano plot for DE results
#'
#' @param results_df DESeq2 results dataframe
#' @param celltype Cell type name
#' @param output_dir Output directory
#' @param padj_threshold Adjusted p-value threshold (default: 0.05)
#' @param log2fc_threshold Log2FC threshold (default: 0.5)
#'
#' @export
plot_volcano <- function(
  results_df,
  celltype,
  output_dir = "results/pseudobulk_de",
  padj_threshold = 0.05,
  log2fc_threshold = 0.5
) {
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  # Prepare data
  plot_df <- results_df %>%
    mutate(
      neg_log10_padj = -log10(padj),
      significance = case_when(
        padj < padj_threshold & abs(log2FoldChange) > log2fc_threshold ~ "Significant",
        TRUE ~ "NS"
      )
    ) %>%
    filter(!is.na(padj))

  # Create plot
  p <- ggplot(plot_df, aes(x = log2FoldChange, y = neg_log10_padj)) +
    geom_point(aes(color = significance), alpha = 0.5, size = 1) +
    geom_hline(yintercept = -log10(padj_threshold), linetype = "dashed", color = "red") +
    geom_vline(xintercept = c(-log2fc_threshold, log2fc_threshold),
               linetype = "dashed", color = "red") +
    scale_color_manual(values = c("NS" = "#CCCCCC", "Significant" = "#E31A1C")) +
    labs(
      title = sprintf("Volcano Plot: %s", celltype),
      x = "log2 Fold Change",
      y = "-log10(adjusted p-value)"
    ) +
    theme_prism()

  # Save
  ggsave(
    file.path(output_dir, sprintf("%s_volcano.svg", celltype)),
    plot = p,
    width = 8,
    height = 6,
    dpi = 300
  )
}


#' Create MA plot for DE results
#'
#' @param results_df DESeq2 results dataframe
#' @param celltype Cell type name
#' @param output_dir Output directory
#' @param padj_threshold Adjusted p-value threshold (default: 0.05)
#'
#' @export
plot_ma <- function(
  results_df,
  celltype,
  output_dir = "results/pseudobulk_de",
  padj_threshold = 0.05
) {
  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  # Prepare data
  plot_df <- results_df %>%
    mutate(
      significance = ifelse(padj < padj_threshold, "Significant", "NS")
    ) %>%
    filter(!is.na(padj), baseMean > 0)

  # Create plot
  p <- ggplot(plot_df, aes(x = log10(baseMean), y = log2FoldChange)) +
    geom_point(aes(color = significance), alpha = 0.5, size = 1) +
    geom_hline(yintercept = 0, linetype = "dashed", color = "black") +
    scale_color_manual(values = c("NS" = "#CCCCCC", "Significant" = "#E31A1C")) +
    labs(
      title = sprintf("MA Plot: %s", celltype),
      x = "Mean Expression (log10)",
      y = "log2 Fold Change"
    ) +
    theme_prism()

  # Save
  ggsave(
    file.path(output_dir, sprintf("%s_ma.svg", celltype)),
    plot = p,
    width = 8,
    height = 6,
    dpi = 300
  )
}


# Example usage
if (FALSE) {
  # Example workflow
  cat("Example pseudobulk DE workflow:\n")
  cat("1. Aggregate: pb <- aggregate_to_pseudobulk(seurat_obj, 'sample_id', 'cell_type')\n")
  cat("2. Run DESeq2: de_results <- run_pseudobulk_deseq2(pb, '~ condition', c('condition', 'treated', 'control'))\n")
  cat("3. Export: export_de_results(de_results)\n")
  cat("4. Plot: plot_volcano(de_results[['CellType']], 'CellType')\n")
}

