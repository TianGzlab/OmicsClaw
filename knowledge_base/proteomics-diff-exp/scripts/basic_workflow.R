# Proteomics differential expression workflow using limma + DEqMS
# Source this script after loading data with load_example_data.R
#
# Expects in calling environment:
#   psm_data  - PSM-level data.frame from load_example_data() or user data
#   metadata  - Sample metadata data.frame with 'condition' column
#
# Creates in calling environment:
#   protein_matrix  - Log2 normalized protein intensities (proteins x samples)
#   raw_matrix      - Pre-normalization log2 protein intensities
#   fit_deqms       - DEqMS fit object (augmented limma fit)
#   deqms_results   - DEqMS results data.frame
#   psm_counts      - Named vector of PSM counts per protein
#   comparison_name - String describing the contrast

cat("\n=== Proteomics DE Analysis (limma + DEqMS) ===\n\n")

# ---- Load required packages ----
library(limma)
library(DEqMS)
library(matrixStats)

# ---- Configuration ----
# These can be overridden before sourcing this script
if (!exists("comparison_name")) {
    comparison_name <- "miR372-ctrl"
}
if (!exists("padj_threshold")) {
    padj_threshold <- 0.05
}
if (!exists("lfc_threshold")) {
    lfc_threshold <- 0.58  # log2(1.5) — standard proteomics threshold (1.5-fold change)
}
if (!exists("imputation_method")) {
    imputation_method <- "MinProb"  # "MinProb" or "kNN"
}
if (!exists("normalization_method")) {
    normalization_method <- "median"  # "median", "quantile", or "none"
}

# ---- Validate inputs ----
if (!exists("psm_data") && !exists("protein_matrix")) {
    stop("No input data found. Run load_example_data() first or provide psm_data/protein_matrix.")
}
if (!exists("metadata")) {
    stop("No metadata found. Run load_example_data() first or provide metadata.")
}

# ---- Step 1: PSM-to-protein aggregation ----
if (exists("psm_data") && !exists("protein_matrix")) {
    cat("1. Aggregating PSMs to protein level (medianSweeping)...\n")

    # Identify intensity columns (columns 3-12 for example data)
    # For user data, intensity columns are all numeric columns except gene/protein ID
    if ("gene" %in% colnames(psm_data)) {
        gene_col <- which(colnames(psm_data) == "gene")
        # Get sample columns from metadata
        sample_cols <- which(colnames(psm_data) %in% rownames(metadata))
        if (length(sample_cols) == 0) {
            # Fallback: assume intensity columns are numeric columns after first 2
            sample_cols <- 3:ncol(psm_data)
        }
    } else {
        stop("PSM data must have a 'gene' column for protein grouping")
    }

    # Log2 transform PSM intensities
    dat.psm.log <- psm_data
    dat.psm.log[, sample_cols] <- log2(psm_data[, sample_cols])

    # Replace -Inf (from log2(0)) with NA
    for (col in sample_cols) {
        dat.psm.log[is.infinite(dat.psm.log[, col]), col] <- NA
    }

    # Aggregate PSMs to protein level using medianSweeping
    # group_col = column index of gene/protein ID (typically column 2)
    protein_matrix <- as.matrix(medianSweeping(dat.psm.log, group_col = gene_col))

    # Count PSMs per protein
    psm_count_table <- as.data.frame(table(psm_data$gene))
    rownames(psm_count_table) <- psm_count_table$Var1
    psm_counts <- setNames(psm_count_table$Freq, psm_count_table$Var1)

    cat("   Aggregated", nrow(psm_data), "PSMs into", nrow(protein_matrix), "proteins\n")
    cat("   PSM count range:", min(psm_counts), "-", max(psm_counts), "\n\n")

} else if (exists("protein_matrix") && !exists("psm_counts")) {
    cat("1. Using pre-aggregated protein matrix\n")
    cat("   WARNING: No PSM counts provided. DEqMS variance correction will be limited.\n")
    cat("   Provide psm_counts for optimal results.\n\n")
    psm_counts <- rep(1, nrow(protein_matrix))
    names(psm_counts) <- rownames(protein_matrix)
}

# ---- Step 2: Missing value assessment and filtering ----
cat("2. Assessing missing values...\n")

# Save raw matrix for QC plots (before imputation/normalization)
raw_matrix <- protein_matrix

n_total <- nrow(protein_matrix)
missing_pct <- sum(is.na(protein_matrix)) / (nrow(protein_matrix) * ncol(protein_matrix)) * 100
cat("   Total proteins:", n_total, "\n")
cat("   Missing values:", sprintf("%.1f%%", missing_pct), "\n")

# Filter: remove proteins with >50% missing in ALL conditions
# (keep if at least one condition has >=50% non-missing)
keep <- rep(FALSE, nrow(protein_matrix))
for (cond in levels(metadata$condition)) {
    cond_samples <- rownames(metadata)[metadata$condition == cond]
    cond_cols <- which(colnames(protein_matrix) %in% cond_samples)
    if (length(cond_cols) > 0) {
        non_missing_pct <- rowSums(!is.na(protein_matrix[, cond_cols, drop = FALSE])) / length(cond_cols)
        keep <- keep | (non_missing_pct >= 0.5)
    }
}
protein_matrix <- protein_matrix[keep, , drop = FALSE]
raw_matrix <- raw_matrix[keep, , drop = FALSE]
psm_counts <- psm_counts[rownames(protein_matrix)]

cat("   After filtering:", nrow(protein_matrix), "proteins retained\n")
cat("   Removed:", n_total - nrow(protein_matrix), "proteins with >50% missing in all conditions\n\n")

# ---- Step 3: Missing value imputation ----
cat("3. Imputing missing values (", imputation_method, ")...\n", sep = "")

n_missing <- sum(is.na(protein_matrix))
if (n_missing > 0) {
    if (imputation_method == "MinProb") {
        # MinProb imputation: draw from low-intensity normal distribution
        # Appropriate for MNAR (Missing Not At Random) in MS data
        for (j in seq_len(ncol(protein_matrix))) {
            na_idx <- is.na(protein_matrix[, j])
            if (any(na_idx)) {
                col_vals <- protein_matrix[!na_idx, j]
                protein_matrix[na_idx, j] <- rnorm(
                    n = sum(na_idx),
                    mean = quantile(col_vals, probs = 0.01, na.rm = TRUE),
                    sd = 0.3 * sd(col_vals, na.rm = TRUE)
                )
            }
        }
        cat("   Imputed", n_missing, "values using MinProb method\n\n")

    } else if (imputation_method == "kNN") {
        # kNN imputation: use k nearest neighbors
        if (requireNamespace("impute", quietly = TRUE)) {
            library(impute)
            imputed <- impute.knn(protein_matrix, k = 10)
            protein_matrix <- imputed$data
            cat("   Imputed", n_missing, "values using kNN (k=10)\n\n")
        } else {
            cat("   impute package not available, falling back to MinProb\n")
            for (j in seq_len(ncol(protein_matrix))) {
                na_idx <- is.na(protein_matrix[, j])
                if (any(na_idx)) {
                    col_vals <- protein_matrix[!na_idx, j]
                    protein_matrix[na_idx, j] <- rnorm(
                        n = sum(na_idx),
                        mean = quantile(col_vals, probs = 0.01, na.rm = TRUE),
                        sd = 0.3 * sd(col_vals, na.rm = TRUE)
                    )
                }
            }
            cat("   Imputed", n_missing, "values using MinProb fallback\n\n")
        }
    }
} else {
    cat("   No missing values to impute\n\n")
}

# ---- Step 4: Normalization ----
cat("4. Normalizing (", normalization_method, ")...\n", sep = "")

if (normalization_method == "median") {
    # Median centering: subtract column median so all samples have median = 0
    col_medians <- colMedians(protein_matrix, na.rm = TRUE)
    protein_matrix <- sweep(protein_matrix, 2, col_medians, "-")
    cat("   Applied median centering normalization\n\n")

} else if (normalization_method == "quantile") {
    # Quantile normalization via limma
    protein_matrix <- normalizeBetweenArrays(protein_matrix, method = "quantile")
    cat("   Applied quantile normalization\n\n")

} else {
    cat("   No normalization applied\n\n")
}

# ---- Step 5: limma model fitting ----
cat("5. Fitting limma linear model...\n")

gene_matrix <- as.matrix(protein_matrix)

# Build design matrix
design <- model.matrix(~0 + condition, data = metadata)
colnames(design) <- gsub("^condition", "", colnames(design))

# Fit linear model
fit1 <- lmFit(gene_matrix, design)

# Make contrasts
contrast_matrix <- makeContrasts(contrasts = comparison_name, levels = design)
fit2 <- contrasts.fit(fit1, contrasts = contrast_matrix)
fit2 <- eBayes(fit2)

cat("   Design:", paste(colnames(design), collapse = ", "), "\n")
cat("   Contrast:", comparison_name, "\n\n")

# ---- Step 6: DEqMS variance correction ----
cat("6. Applying DEqMS PSM-count-aware variance correction...\n")

# Assign PSM counts to fit object
fit2$count <- psm_counts[rownames(fit2$coefficients)]

# Replace any NA counts with 1
fit2$count[is.na(fit2$count)] <- 1

# Run DEqMS
fit_deqms <- spectraCounteBayes(fit2)

cat("   DEqMS correction applied using PSM counts\n")
cat("   PSM count range:", min(fit_deqms$count, na.rm = TRUE), "-",
    max(fit_deqms$count, na.rm = TRUE), "\n\n")

# ---- Step 7: Extract results ----
cat("7. Extracting results...\n")

deqms_results <- outputResult(fit_deqms, coef_col = 1)

# Add protein names as column
deqms_results$protein <- rownames(deqms_results)

# Sort by DEqMS adjusted p-value
deqms_results <- deqms_results[order(deqms_results$sca.adj.pval), ]

# ---- Summary ----
n_sig_deqms <- sum(deqms_results$sca.adj.pval < padj_threshold &
                    abs(deqms_results$logFC) > lfc_threshold, na.rm = TRUE)
n_sig_limma <- sum(deqms_results$adj.P.Val < padj_threshold &
                    abs(deqms_results$logFC) > lfc_threshold, na.rm = TRUE)
n_up <- sum(deqms_results$sca.adj.pval < padj_threshold &
             deqms_results$logFC > lfc_threshold, na.rm = TRUE)
n_down <- sum(deqms_results$sca.adj.pval < padj_threshold &
               deqms_results$logFC < -lfc_threshold, na.rm = TRUE)

cat("\n✓ Proteomics DE analysis completed successfully!\n")
cat("  Total proteins tested:", nrow(deqms_results), "\n")
cat("  Comparison:", comparison_name, "\n")
cat("  Thresholds: sca.adj.pval <", padj_threshold, ", |logFC| >", lfc_threshold, "\n")
cat("  Significant (DEqMS):", n_sig_deqms,
    "(", n_up, "up,", n_down, "down )\n")
cat("  Significant (limma):", n_sig_limma, "\n")
cat("  Top hit:", deqms_results$protein[1],
    "(logFC =", sprintf("%.2f", deqms_results$logFC[1]),
    ", sca.adj.pval =", sprintf("%.2e", deqms_results$sca.adj.pval[1]), ")\n\n")

