#!/usr/bin/env Rscript

##
## glmGamPoi Batch-Corrected Differential Expression for CRISPR Screens
##
## This script runs glmGamPoi to perform rigorous differential expression
## analysis with donor/batch correction for perturbation screens.
##
## Usage:
##   Rscript run_glmgampoi.R <h5ad_file> <perturbations> <control> <gene_col> <donor_col> <min_expr> <output_dir>
##
## Arguments:
##   h5ad_file: Path to AnnData h5ad file (RAW counts)
##   perturbations: Comma-separated list of perturbations to test
##   control: Name of control group (e.g., "non-targeting")
##   gene_col: Column name for perturbation identities
##   donor_col: Column name for donor/batch information
##   min_expr: Minimum total expression across cells for gene inclusion
##   output_dir: Directory to save results
##

# Parse command line arguments
args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 7) {
    cat("Error: Insufficient arguments\n")
    cat("Usage: Rscript run_glmgampoi.R <h5ad_file> <perturbations> <control> <gene_col> <donor_col> <min_expr> <output_dir>\n")
    quit(status = 1)
}

h5ad_file <- args[1]
perturbations_str <- args[2]
control_group <- args[3]
gene_col <- args[4]
donor_col <- args[5]
min_expression <- as.numeric(args[6])
output_dir <- args[7]

# Load required libraries
suppressPackageStartupMessages({
    library(glmGamPoi)
    library(SingleCellExperiment)
    library(zellkonverter)  # For reading h5ad files
})

cat(sprintf("\nglmGamPoi Differential Expression Analysis\n"))
cat(sprintf("==========================================\n"))
cat(sprintf("Input file: %s\n", h5ad_file))
cat(sprintf("Control group: %s\n", control_group))
cat(sprintf("Gene column: %s\n", gene_col))
cat(sprintf("Donor column: %s\n", donor_col))
cat(sprintf("Min expression: %d\n", min_expression))
cat(sprintf("Output directory: %s\n\n", output_dir))

# Create output directory
if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
}

# Load data
cat("Loading data from h5ad file...\n")
sce <- tryCatch({
    readH5AD(h5ad_file)
}, error = function(e) {
    cat(sprintf("Error loading h5ad file: %s\n", e$message))
    quit(status = 1)
})

cat(sprintf("Loaded data: %d cells, %d genes\n", ncol(sce), nrow(sce)))

# Check that required columns exist
if (!gene_col %in% colnames(colData(sce))) {
    cat(sprintf("Error: Gene column '%s' not found in cell metadata\n", gene_col))
    quit(status = 1)
}

if (!donor_col %in% colnames(colData(sce))) {
    cat(sprintf("Error: Donor column '%s' not found in cell metadata\n", donor_col))
    quit(status = 1)
}

# Parse perturbations list
perturbations <- strsplit(perturbations_str, ",")[[1]]
cat(sprintf("Testing %d perturbations\n\n", length(perturbations)))

# Run glmGamPoi for each perturbation
for (i in seq_along(perturbations)) {
    gene <- perturbations[i]
    cat(sprintf("[%d/%d] Processing %s...\n", i, length(perturbations), gene))

    tryCatch({
        # Subset to perturbation + control
        cells_of_interest <- colData(sce)[[gene_col]] %in% c(gene, control_group)
        sce_subset <- sce[, cells_of_interest]

        # Count cells
        n_perturbed <- sum(colData(sce_subset)[[gene_col]] == gene)
        n_control <- sum(colData(sce_subset)[[gene_col]] == control_group)

        cat(sprintf("  Cells: %d perturbed, %d control\n", n_perturbed, n_control))

        # Check minimum cells
        if (n_perturbed < 20 || n_control < 20) {
            cat(sprintf("  Skipping: insufficient cells\n"))
            next
        }

        # Filter lowly expressed genes
        gene_totals <- rowSums(counts(sce_subset))
        sce_subset <- sce_subset[gene_totals > min_expression, ]

        cat(sprintf("  Genes after filtering: %d\n", nrow(sce_subset)))

        if (nrow(sce_subset) < 100) {
            cat(sprintf("  Skipping: too few genes after filtering\n"))
            next
        }

        # Set up design formula with donor correction
        # Ensure factor levels are properly set (control as reference)
        colData(sce_subset)[[gene_col]] <- factor(
            colData(sce_subset)[[gene_col]],
            levels = c(control_group, gene)
        )

        # Create design formula
        design_formula <- as.formula(sprintf("~ %s + %s - 1", gene_col, donor_col))

        cat(sprintf("  Fitting glmGamPoi model...\n"))

        # Fit glmGamPoi model
        fit <- glm_gp(
            sce_subset,
            design = design_formula,
            on_disk = FALSE,
            verbose = FALSE
        )

        # Test perturbation vs control
        gene_level <- sprintf("%s%s", gene_col, gene)
        control_level <- sprintf("%s%s", gene_col, control_group)

        contrast_formula <- as.formula(sprintf("~ `%s` - `%s`", gene_level, control_level))

        cat(sprintf("  Testing differential expression...\n"))

        # Perform DE test
        res <- test_de(
            fit,
            contrast = contrast_formula,
            sort_by = "pval",
            verbose = FALSE
        )

        # Extract results
        de_results <- data.frame(
            gene = res$name,
            log2fc = res$lfc,
            pval = res$pval,
            adj_pval = res$adj_pval,
            mean_expression = res$mean,
            stringsAsFactors = FALSE
        )

        # Count significant genes
        n_sig <- sum(de_results$adj_pval < 0.05, na.rm = TRUE)
        cat(sprintf("  Significant genes (FDR < 0.05): %d\n", n_sig))

        # Save results
        output_file <- file.path(output_dir, sprintf("%s_glmgampoi.csv", gene))
        write.csv(de_results, output_file, row.names = FALSE, quote = FALSE)
        cat(sprintf("  Results saved to: %s\n", output_file))

    }, error = function(e) {
        cat(sprintf("  Error processing %s: %s\n", gene, e$message))
    })

    cat("\n")
}

cat("glmGamPoi analysis complete\n")

