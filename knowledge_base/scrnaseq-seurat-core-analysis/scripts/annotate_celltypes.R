# ============================================================================
# CELL TYPE ANNOTATION
# ============================================================================
#
# Assign biological identities to clusters based on marker genes.
#
# Functions:
#   - annotate_clusters_manual(): Manual annotation with custom labels
#   - annotate_with_singler(): Automated annotation using SingleR
#   - annotate_with_azimuth(): Automated annotation using Azimuth
#   - plot_annotated_umap(): UMAP with cell type labels
#   - plot_celltype_proportions(): Bar plot of cell type frequencies
#
# Usage:
#   source("scripts/annotate_celltypes.R")
#   seurat_obj <- annotate_clusters_manual(seurat_obj, annotations)

library(ggplot2)
library(ggprism)
library(dplyr)

#' Manually annotate clusters with cell type labels
#'
#' @param seurat_obj Seurat object with clusters
#' @param annotations Named vector: cluster IDs -> cell type names
#' @param resolution Resolution to annotate (NULL for active idents)
#' @param new_col_name Name for new annotation column (default: "celltype")
#' @return Seurat object with cell type annotations
#' @export
annotate_clusters_manual <- function(seurat_obj,
                                    annotations,
                                    resolution = NULL,
                                    new_col_name = "celltype") {

  message("Applying manual cell type annotations")

  # Set identity if resolution specified
  if (!is.null(resolution)) {
    col_name <- paste0("RNA_snn_res.", resolution)
    Idents(seurat_obj) <- col_name
    message("  Using resolution: ", resolution)
  }

  # Get current cluster assignments
  current_clusters <- as.character(Idents(seurat_obj))

  # Map to cell types
  cell_types <- annotations[current_clusters]

  # Check for unmapped clusters
  unmapped <- unique(current_clusters[is.na(cell_types)])
  if (length(unmapped) > 0) {
    warning("Unmapped clusters: ", paste(unmapped, collapse = ", "))
    cell_types[is.na(cell_types)] <- paste0("Cluster_", current_clusters[is.na(cell_types)])
  }

  # Add to metadata
  seurat_obj[[new_col_name]] <- cell_types

  # Set as active identity
  Idents(seurat_obj) <- new_col_name

  # Print summary
  message("Annotation complete:")
  print(table(seurat_obj[[new_col_name]]))

  return(seurat_obj)
}

#' Automated annotation using SingleR
#'
#' @param seurat_obj Seurat object with normalized data
#' @param reference Reference dataset name (e.g., "HPCA", "Blueprint_Encode", "Monaco")
#' @param resolution Resolution to annotate (NULL for active idents)
#' @param assay Assay to use (default: NULL = active assay)
#' @return Seurat object with SingleR annotations
#' @export
annotate_with_singler <- function(seurat_obj,
                                  reference = "HPCA",
                                  resolution = NULL,
                                  assay = NULL) {

  # Check if packages are installed
  if (!requireNamespace("SingleR", quietly = TRUE)) {
    stop("SingleR required. Install with: BiocManager::install('SingleR')")
  }
  if (!requireNamespace("celldex", quietly = TRUE)) {
    stop("celldex required. Install with: BiocManager::install('celldex')")
  }

  library(SingleR)
  library(celldex)

  message("Running SingleR automated annotation")
  message("  Reference: ", reference)

  # Set identity if resolution specified
  if (!is.null(resolution)) {
    col_name <- paste0("RNA_snn_res.", resolution)
    Idents(seurat_obj) <- col_name
  }

  # Get reference dataset
  ref_data <- switch(reference,
                     "HPCA" = HumanPrimaryCellAtlasData(),
                     "Blueprint_Encode" = BlueprintEncodeData(),
                     "Monaco" = MonacoImmuneData(),
                     "Mouse" = MouseRNAseqData(),
                     stop("Unknown reference: ", reference))

  # Get expression data
  if (is.null(assay)) {
    test_data <- GetAssayData(seurat_obj, slot = "data")
  } else {
    test_data <- GetAssayData(seurat_obj, assay = assay, slot = "data")
  }

  # Run SingleR
  predictions <- SingleR(
    test = test_data,
    ref = ref_data,
    labels = ref_data$label.main
  )

  # Add predictions to Seurat object
  seurat_obj$singler_labels <- predictions$labels
  seurat_obj$singler_scores <- predictions$scores

  message("SingleR annotation complete")
  message("Cell types identified:")
  print(table(predictions$labels))

  # Optionally set as active identity
  # Idents(seurat_obj) <- "singler_labels"

  return(seurat_obj)
}

#' Automated annotation using Azimuth
#'
#' @param seurat_obj Seurat object
#' @param reference Azimuth reference name (e.g., "pbmc", "lung", "kidney")
#' @return Seurat object with Azimuth annotations
#' @export
annotate_with_azimuth <- function(seurat_obj, reference = "pbmc") {

  # Check if Azimuth is installed
  if (!requireNamespace("Azimuth", quietly = TRUE)) {
    stop("Azimuth required. Install with: remotes::install_github('satijalab/azimuth')")
  }

  library(Azimuth)

  message("Running Azimuth automated annotation")
  message("  Reference: ", reference)
  message("  Note: This requires internet connection to download reference")

  # Run Azimuth
  seurat_obj <- RunAzimuth(
    seurat_obj,
    reference = reference
  )

  message("Azimuth annotation complete")
  message("Predicted cell types:")
  print(table(seurat_obj$predicted.celltype.l1))

  return(seurat_obj)
}

#' Plot UMAP with cell type annotations
#'
#' @param seurat_obj Seurat object with cell type annotations
#' @param group_by Metadata column with cell types (default: "celltype")
#' @param label Label cell types on plot (default: TRUE)
#' @param output_dir Output directory for plots
#' @param width Plot width (default: 10)
#' @param height Plot height (default: 8)
#' @return ggplot object
#' @export
plot_annotated_umap <- function(seurat_obj,
                                group_by = "celltype",
                                label = TRUE,
                                output_dir = NULL,
                                width = 10,
                                height = 8) {

  message("Creating annotated UMAP")

  # Check if column exists
  if (!group_by %in% colnames(seurat_obj@meta.data)) {
    stop("Column not found: ", group_by)
  }

  # Create UMAP plot
  p <- DimPlot(
    seurat_obj,
    reduction = "umap",
    group.by = group_by,
    label = label,
    label.size = 5,
    pt.size = 0.5,
    repel = TRUE
  ) +
    theme_prism() +
    theme(legend.position = "right") +
    labs(title = "Cell Type Annotation")

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    svg_file <- file.path(output_dir, "umap_celltypes.svg")
    ggsave(svg_file, plot = p, width = width, height = height, dpi = 300)
    message("  Saved: ", svg_file)

    png_file <- file.path(output_dir, "umap_celltypes.png")
    ggsave(png_file, plot = p, width = width, height = height, dpi = 300)
    message("  Saved: ", png_file)
  }

  return(p)
}

#' Plot cell type proportions
#'
#' @param seurat_obj Seurat object with cell type annotations
#' @param group_by Metadata column with cell types (default: "celltype")
#' @param split_by Optional column to split by (e.g., condition)
#' @param output_dir Output directory for plots
#' @param width Plot width (default: 10)
#' @param height Plot height (default: 6)
#' @return ggplot object
#' @export
plot_celltype_proportions <- function(seurat_obj,
                                     group_by = "celltype",
                                     split_by = NULL,
                                     output_dir = NULL,
                                     width = 10,
                                     height = 6) {

  message("Creating cell type proportion plot")

  # Get metadata
  metadata <- seurat_obj@meta.data

  # Calculate proportions
  if (is.null(split_by)) {
    # Overall proportions
    counts <- table(metadata[[group_by]])
    prop_data <- data.frame(
      celltype = names(counts),
      count = as.numeric(counts),
      proportion = as.numeric(counts) / sum(counts)
    )

    p <- ggplot(prop_data, aes(x = reorder(celltype, -count), y = count, fill = celltype)) +
      geom_bar(stat = "identity", color = "black") +
      geom_text(aes(label = paste0(round(proportion * 100, 1), "%")),
                vjust = -0.5, size = 3.5) +
      theme_prism() +
      theme(
        axis.text.x = element_text(angle = 45, hjust = 1),
        legend.position = "none"
      ) +
      labs(
        x = "Cell Type",
        y = "Number of Cells",
        title = "Cell Type Distribution"
      )

  } else {
    # Proportions split by condition
    prop_data <- metadata %>%
      group_by(!!sym(group_by), !!sym(split_by)) %>%
      summarise(count = n(), .groups = "drop") %>%
      group_by(!!sym(split_by)) %>%
      mutate(proportion = count / sum(count))

    p <- ggplot(prop_data, aes(x = !!sym(group_by), y = proportion, fill = !!sym(split_by))) +
      geom_bar(stat = "identity", position = "dodge", color = "black") +
      theme_prism() +
      theme(axis.text.x = element_text(angle = 45, hjust = 1)) +
      labs(
        x = "Cell Type",
        y = "Proportion",
        title = paste0("Cell Type Distribution by ", split_by)
      ) +
      scale_y_continuous(labels = scales::percent)
  }

  # Save plot if output directory specified
  if (!is.null(output_dir)) {
    dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

    svg_file <- file.path(output_dir, "celltype_proportions.svg")
    ggsave(svg_file, plot = p, width = width, height = height, dpi = 300)
    message("  Saved: ", svg_file)

    png_file <- file.path(output_dir, "celltype_proportions.png")
    ggsave(png_file, plot = p, width = width, height = height, dpi = 300)
    message("  Saved: ", png_file)
  }

  return(p)
}

