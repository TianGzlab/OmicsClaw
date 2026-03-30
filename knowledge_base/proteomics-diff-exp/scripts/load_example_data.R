# Load example proteomics data for limma + DEqMS analysis
# Uses DEqMS ExperimentHub TMT10plex dataset (EH1663)
# A431 human epidermoid carcinoma cells treated with miRNAs

#' Load TMT10plex A431 miRNA proteomics example data
#'
#' Downloads PSM-level data from ExperimentHub (EH1663).
#' Auto-installs required packages if missing.
#'
#' @return List with:
#'   \itemize{
#'     \item psm_data - PSM-level data.frame (gene column + 10 TMT channels)
#'     \item metadata - Sample metadata data.frame (sample, condition)
#'     \item description - Dataset description string
#'   }
#' @examples
#' data <- load_example_data()
#' @export
load_example_data <- function() {

    # Set CRAN mirror first
    if (length(getOption("repos")) == 0 ||
        getOption("repos")["CRAN"] == "@CRAN@") {
        options(repos = c(CRAN = "https://cloud.r-project.org"))
    }

    # Install BiocManager if needed
    if (!requireNamespace("BiocManager", quietly = TRUE)) {
        cat("Installing BiocManager...\n")
        install.packages("BiocManager")
    }

    # Install ExperimentHub if needed
    if (!requireNamespace("ExperimentHub", quietly = TRUE)) {
        cat("Installing ExperimentHub (~2 min)...\n")
        BiocManager::install("ExperimentHub", update = FALSE, ask = FALSE)
    }

    # Install DEqMS if needed
    if (!requireNamespace("DEqMS", quietly = TRUE)) {
        cat("Installing DEqMS...\n")
        BiocManager::install("DEqMS", update = FALSE, ask = FALSE)
    }

    library(ExperimentHub)
    library(DEqMS)

    # Load PSM-level data from ExperimentHub
    cat("Loading TMT10plex proteomics data from ExperimentHub...\n")
    options(timeout = 300)
    eh <- ExperimentHub()
    dat.psm <- eh[["EH1663"]]

    # Build sample metadata
    # TMT channels: 126-131 correspond to 10 conditions
    sample_names <- colnames(dat.psm)[3:12]
    conditions <- c("ctrl", "miR191", "miR372", "miR519",
                     "ctrl", "miR372", "miR519",
                     "ctrl", "miR191", "miR372")

    metadata <- data.frame(
        sample = sample_names,
        condition = factor(conditions, levels = c("ctrl", "miR191", "miR372", "miR519")),
        row.names = sample_names,
        stringsAsFactors = FALSE
    )

    # Verify data integrity
    stopifnot(ncol(dat.psm) >= 12)
    stopifnot(all(sample_names %in% colnames(dat.psm)))

    n_psms <- nrow(dat.psm)
    n_proteins <- length(unique(dat.psm$gene))
    n_samples <- length(sample_names)

    cat("\n✓ Example data loaded successfully\n")
    cat("  PSMs:", n_psms, "\n")
    cat("  Proteins:", n_proteins, "\n")
    cat("  Samples:", n_samples, "(TMT 10-plex)\n")
    cat("  Conditions:", paste(levels(metadata$condition), collapse = ", "), "\n")
    cat("  Replicates per condition:\n")
    print(table(metadata$condition))
    cat("\n")

    return(list(
        psm_data = dat.psm,
        metadata = metadata,
        description = "A431 human epidermoid carcinoma cells treated with miRNAs (TMT 10-plex, PXD004163)"
    ))
}


#' Validate user-provided proteomics data
#'
#' Checks intensity matrix and metadata for common issues.
#'
#' @param intensity_matrix Protein intensity matrix (proteins x samples), numeric
#' @param metadata Sample metadata data.frame
#' @param psm_counts Optional named vector of PSM/peptide counts per protein
#' @param condition_col Name of the condition column in metadata (default: "condition")
#' @return List with validated intensity_matrix, metadata, psm_counts
#' @export
validate_input_data <- function(intensity_matrix, metadata,
                                 psm_counts = NULL,
                                 condition_col = "condition") {

    cat("Validating input data...\n")

    # Check intensity matrix is numeric
    if (!is.matrix(intensity_matrix) && !is.data.frame(intensity_matrix)) {
        stop("intensity_matrix must be a matrix or data.frame")
    }
    intensity_matrix <- as.matrix(intensity_matrix)
    if (!is.numeric(intensity_matrix)) {
        stop("intensity_matrix must contain numeric values")
    }

    # Check metadata
    if (!is.data.frame(metadata)) {
        stop("metadata must be a data.frame")
    }
    if (!condition_col %in% colnames(metadata)) {
        stop(paste0("metadata must have a '", condition_col, "' column. ",
                     "Available columns: ", paste(colnames(metadata), collapse = ", ")))
    }

    # Check sample alignment
    if (!is.null(rownames(metadata))) {
        if (all(colnames(intensity_matrix) %in% rownames(metadata))) {
            metadata <- metadata[colnames(intensity_matrix), , drop = FALSE]
        } else if (!all(colnames(intensity_matrix) == rownames(metadata))) {
            warning("Column names of intensity_matrix do not match row names of metadata. ",
                    "Assuming same order.")
        }
    }

    if (nrow(metadata) != ncol(intensity_matrix)) {
        stop(paste0("Number of samples in metadata (", nrow(metadata),
                     ") does not match columns in intensity_matrix (",
                     ncol(intensity_matrix), ")"))
    }

    # Check for all-NA rows
    all_na_rows <- rowSums(!is.na(intensity_matrix)) == 0
    if (any(all_na_rows)) {
        cat("  Removing", sum(all_na_rows), "proteins with all missing values\n")
        intensity_matrix <- intensity_matrix[!all_na_rows, , drop = FALSE]
    }

    # Ensure condition is factor
    if (!is.factor(metadata[[condition_col]])) {
        metadata[[condition_col]] <- factor(metadata[[condition_col]])
    }

    # Check minimum replicates
    condition_counts <- table(metadata[[condition_col]])
    if (any(condition_counts < 2)) {
        warning("Some conditions have fewer than 2 replicates: ",
                paste(names(condition_counts[condition_counts < 2]), collapse = ", "))
    }

    # Validate PSM counts if provided
    if (!is.null(psm_counts)) {
        if (!is.numeric(psm_counts)) {
            stop("psm_counts must be a numeric vector")
        }
        if (!is.null(names(psm_counts))) {
            common <- intersect(rownames(intensity_matrix), names(psm_counts))
            if (length(common) < nrow(intensity_matrix) * 0.5) {
                warning("Less than 50% of proteins have matching PSM counts. ",
                        "Check protein ID format.")
            }
        }
    }

    cat("✓ Input data validated\n")
    cat("  Proteins:", nrow(intensity_matrix), "\n")
    cat("  Samples:", ncol(intensity_matrix), "\n")
    cat("  Conditions:", paste(levels(metadata[[condition_col]]), collapse = ", "), "\n")
    if (!is.null(psm_counts)) {
        cat("  PSM counts: provided for", length(psm_counts), "proteins\n")
    }
    cat("\n")

    return(list(
        intensity_matrix = intensity_matrix,
        metadata = metadata,
        psm_counts = psm_counts
    ))
}

