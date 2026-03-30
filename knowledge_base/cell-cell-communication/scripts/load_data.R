# =============================================================================
# Cell-Cell Communication Analysis — Data Loading
# =============================================================================
# Loads annotated Seurat object for CellChat analysis.
# Accepts: (1) path to Seurat RDS, or (2) example PBMC data via SeuratData.
# =============================================================================

suppressPackageStartupMessages({
    library(Seurat)
})

# --- Example Data Loader ---------------------------------------------------

#' Load example PBMC 3k dataset (pre-annotated, human immune cells)
#'
#' Auto-installs SeuratData if needed. Returns a Seurat object with
#' cell type annotations in the "celltype" metadata column.
#'
#' @return Seurat object (2,638 cells, 8 cell types)
load_example_pbmc <- function() {
    cat("\n=== Loading Example PBMC Data ===\n\n")

    # Set CRAN mirror
    options(repos = c(CRAN = "https://cloud.r-project.org"))

    # Install SeuratData if needed
    if (!requireNamespace("SeuratData", quietly = TRUE)) {
        cat("Installing SeuratData...\n")
        if (!requireNamespace("devtools", quietly = TRUE)) {
            install.packages("devtools")
        }
        devtools::install_github("satijalab/seurat-data", upgrade = "never")
    }

    library(SeuratData)

    # Install pbmc3k dataset if needed
    available <- AvailableData()
    # SeuratData rownames use "pbmc3k.SeuratData" format
    pbmc_row <- grep("^pbmc3k", rownames(available), value = TRUE)[1]
    if (!is.na(pbmc_row)) {
        if (!available[pbmc_row, "Installed"]) {
            cat("Installing pbmc3k dataset (~6MB)...\n")
            InstallData("pbmc3k")
        }
    } else {
        stop("pbmc3k dataset not available in SeuratData. ",
             "Try: remotes::install_github('satijalab/seurat-data')")
    }

    # Load the pre-processed version (pbmc3k.final has cell type annotations)
    # Suppress warnings about newer Seurat version
    env <- new.env()
    data("pbmc3k.final", package = "pbmc3k.SeuratData", envir = env)
    seurat_obj <- env$pbmc3k.final

    # Update to current Seurat v5 format (handles old "images" slot etc.)
    cat("   Updating Seurat object to v5 format...\n")
    seurat_obj <- UpdateSeuratObject(seurat_obj)

    # Ensure cell type column exists as "celltype"
    if (!"celltype" %in% colnames(seurat_obj@meta.data)) {
        # pbmc3k.final stores annotations in active ident
        seurat_obj$celltype <- Idents(seurat_obj)
    }

    # Verify normalization — check a small block for all zeros
    norm_check <- tryCatch({
        d <- GetAssayData(seurat_obj, layer = "data")
        all(d[1:min(5, nrow(d)), 1:min(5, ncol(d))] == 0)
    }, error = function(e) TRUE)
    if (norm_check) {
        cat("   Running normalization...\n")
        seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)
    }

    cat("   Dataset: PBMC 3k (Satija Lab, 10X Genomics)\n")
    cat("   Species: Human\n")
    cat("   Cells:", ncol(seurat_obj), "\n")
    cat("   Genes:", nrow(seurat_obj), "\n")
    cat("\n   Cell type composition:\n")
    ct_table <- sort(table(seurat_obj$celltype), decreasing = TRUE)
    for (ct in names(ct_table)) {
        cat(sprintf("     %-25s %d cells\n", ct, ct_table[ct]))
    }

    cat("\n✓ Data loaded successfully!", ncol(seurat_obj), "cells,",
        length(unique(seurat_obj$celltype)), "cell types\n\n")

    return(seurat_obj)
}


# --- General Data Loader ----------------------------------------------------

#' Load Seurat object for CellChat analysis
#'
#' @param seurat_path Path to Seurat RDS file (NULL for example data)
#' @param group.by Metadata column with cell type annotations
#' @return Seurat object validated for CellChat
load_cellchat_data <- function(seurat_path = NULL, group.by = "celltype") {

    if (is.null(seurat_path)) {
        return(load_example_pbmc())
    }

    cat("\n=== Loading Seurat Object ===\n\n")

    # Load RDS
    if (!file.exists(seurat_path)) {
        stop("File not found: ", seurat_path)
    }
    cat("   Loading:", seurat_path, "\n")
    seurat_obj <- readRDS(seurat_path)

    # Validate
    seurat_obj <- validate_seurat_for_cellchat(seurat_obj, group.by = group.by)

    cat("\n✓ Data loaded successfully!", ncol(seurat_obj), "cells,",
        length(unique(seurat_obj[[group.by, drop = TRUE]])), "cell types\n\n")

    return(seurat_obj)
}


# --- Validation --------------------------------------------------------------

#' Validate Seurat object has required components for CellChat
#'
#' @param seurat_obj Seurat object
#' @param group.by Metadata column with cell type annotations
#' @return Validated Seurat object
validate_seurat_for_cellchat <- function(seurat_obj, group.by = "celltype") {

    # Check it's a Seurat object
    if (!inherits(seurat_obj, "Seurat")) {
        stop("Input must be a Seurat object. Got: ", class(seurat_obj)[1])
    }

    # Check cell type column exists
    if (!group.by %in% colnames(seurat_obj@meta.data)) {
        available_cols <- colnames(seurat_obj@meta.data)
        # Try to find a likely cell type column
        candidates <- grep("cell.?type|ident|label|annotation|cluster",
                          available_cols, ignore.case = TRUE, value = TRUE)
        msg <- paste0("Column '", group.by, "' not found in metadata.\n",
                      "  Available columns: ", paste(available_cols, collapse = ", "))
        if (length(candidates) > 0) {
            msg <- paste0(msg, "\n  Likely cell type columns: ",
                         paste(candidates, collapse = ", "))
        }
        stop(msg)
    }

    # Check for normalized data
    norm_data <- tryCatch(
        GetAssayData(seurat_obj, layer = "data"),
        error = function(e) NULL
    )
    if (is.null(norm_data)) {
        cat("   ⚠ No normalized data found. Running NormalizeData()...\n")
        seurat_obj <- NormalizeData(seurat_obj, verbose = FALSE)
    }

    # Check minimum cells per type
    ct_counts <- table(seurat_obj[[group.by, drop = TRUE]])
    small_types <- ct_counts[ct_counts < 10]
    if (length(small_types) > 0) {
        cat("   ⚠ Warning: Cell types with <10 cells (may be filtered by CellChat):\n")
        for (ct in names(small_types)) {
            cat("     ", ct, ":", small_types[ct], "cells\n")
        }
    }

    # Print summary
    cat("   Cells:", ncol(seurat_obj), "\n")
    cat("   Genes:", nrow(seurat_obj), "\n")
    cat("   Cell types (", group.by, "):\n")
    ct_table <- sort(table(seurat_obj[[group.by, drop = TRUE]]), decreasing = TRUE)
    for (ct in names(ct_table)) {
        cat(sprintf("     %-25s %d cells\n", ct, ct_table[ct]))
    }

    return(seurat_obj)
}

