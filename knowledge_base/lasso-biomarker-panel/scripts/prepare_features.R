# Prepare Feature Matrix for LASSO Biomarker Panel Selection
# Transforms expression data into a LASSO-ready scaled feature matrix

#' Prepare feature matrix for LASSO modeling
#'
#' Log2-transforms TPM values, filters to top N most variable features,
#' scales to zero mean/unit variance, and aligns samples between expression
#' and metadata.
#'
#' @param expression Expression matrix (genes x samples). TPM or normalized values.
#' @param metadata Data frame with sample metadata (rownames = sample IDs)
#' @param outcome_col Name of binary outcome column in metadata
#' @param top_n_variable Number of most variable features to retain (default: 5000)
#' @param log_transform Apply log2(x+1) transformation (default: TRUE for TPM data)
#' @param scale_features Scale features to zero mean/unit variance (default: TRUE)
#'
#' @return list(X, y, feature_names, sample_ids, transform_params)
prepare_feature_matrix <- function(expression, metadata, outcome_col,
                                    top_n_variable = 5000,
                                    log_transform = TRUE,
                                    scale_features = TRUE) {
    cat("Preparing feature matrix for LASSO...\n")

    # Align samples
    shared_samples <- intersect(colnames(expression), rownames(metadata))
    if (length(shared_samples) == 0) {
        stop("No shared sample IDs between expression columns and metadata rownames.")
    }
    cat("  Shared samples:", length(shared_samples), "\n")

    expr <- expression[, shared_samples, drop = FALSE]
    meta <- metadata[shared_samples, , drop = FALSE]

    # Remove samples with NA outcome
    outcome <- meta[[outcome_col]]
    valid <- !is.na(outcome)
    if (sum(!valid) > 0) {
        cat("  Removing", sum(!valid), "samples with NA outcome\n")
    }
    expr <- expr[, valid, drop = FALSE]
    meta <- meta[valid, , drop = FALSE]
    outcome <- meta[[outcome_col]]

    # Ensure numeric binary outcome
    y <- as.numeric(as.factor(outcome)) - 1
    names(y) <- rownames(meta)
    cat("  Outcome: ", sum(y == 1), "positives,", sum(y == 0), "negatives\n")

    # Convert to numeric matrix
    expr <- as.matrix(expr)
    storage.mode(expr) <- "numeric"

    # Remove features with zero variance or all NA
    feature_vars <- apply(expr, 1, var, na.rm = TRUE)
    valid_features <- !is.na(feature_vars) & feature_vars > 0
    expr <- expr[valid_features, , drop = FALSE]
    cat("  Features after removing zero-variance:", nrow(expr), "\n")

    # Log2 transform (for TPM/FPKM data)
    if (log_transform) {
        # Check if data looks like it needs log transform (max > 100 suggests raw TPM)
        if (max(expr, na.rm = TRUE) > 100) {
            cat("  Applying log2(x + 1) transformation\n")
            expr <- log2(expr + 1)
        } else {
            cat("  Data appears already log-transformed (max =",
                round(max(expr, na.rm = TRUE), 2), "), skipping log2\n")
        }
    }

    # Replace any remaining NAs with 0
    expr[is.na(expr)] <- 0

    # Filter to top N most variable features
    if (top_n_variable < nrow(expr)) {
        feature_vars <- apply(expr, 1, var)
        top_idx <- order(feature_vars, decreasing = TRUE)[1:top_n_variable]
        expr <- expr[top_idx, , drop = FALSE]
        cat("  Filtered to top", top_n_variable, "most variable features\n")
    }

    # Scale features (zero mean, unit variance)
    transform_params <- NULL
    if (scale_features) {
        cat("  Scaling features to zero mean / unit variance\n")
        expr_scaled <- t(scale(t(expr)))
        # Save scaling parameters for applying to validation data
        transform_params <- list(
            center = attr(scale(t(expr)), "scaled:center"),
            scale = attr(scale(t(expr)), "scaled:scale")
        )
        # Transpose: LASSO expects samples x features
        X <- t(expr_scaled)
    } else {
        X <- t(expr)
    }

    # Ensure no NaN/Inf from scaling
    X[is.nan(X)] <- 0
    X[is.infinite(X)] <- 0

    cat("\n✓ Feature matrix prepared successfully\n")
    cat("  X dimensions:", nrow(X), "samples x", ncol(X), "features\n")
    cat("  y distribution:", table(y), "\n")

    return(list(
        X = X,
        y = y,
        feature_names = colnames(X),
        sample_ids = rownames(X),
        transform_params = transform_params
    ))
}

#' Optional: Pre-filter features by differential expression (limma-voom)
#'
#' Lightweight DE analysis using limma (works with TPM, no raw counts needed).
#' Returns a subset of the expression matrix with only DE-significant features.
#'
#' @param expression Expression matrix (genes x samples)
#' @param metadata Data frame with sample metadata
#' @param outcome_col Name of binary outcome column
#' @param padj_threshold Adjusted p-value threshold (default: 0.05)
#'
#' @return Filtered expression matrix (significant genes only)
filter_by_de <- function(expression, metadata, outcome_col, padj_threshold = 0.05) {
    cat("Pre-filtering features by differential expression (limma)...\n")

    if (!requireNamespace("limma", quietly = TRUE)) {
        cat("  limma not available. Skipping DE pre-filter.\n")
        return(expression)
    }

    library(limma)

    # Align samples
    shared <- intersect(colnames(expression), rownames(metadata))
    expr <- as.matrix(expression[, shared])
    outcome <- metadata[shared, outcome_col]

    # Design matrix
    design <- model.matrix(~ factor(outcome))

    # Fit linear model
    fit <- lmFit(expr, design)
    fit <- eBayes(fit)

    # Extract results
    results <- topTable(fit, coef = 2, number = Inf, sort.by = "none")
    sig_genes <- rownames(results)[results$adj.P.Val < padj_threshold]

    cat("  Significant features (padj <", padj_threshold, "):", length(sig_genes), "\n")

    if (length(sig_genes) < 50) {
        cat("  WARNING: Very few significant features. Using top 500 by p-value instead.\n")
        sig_genes <- rownames(results)[order(results$P.Value)][1:min(500, nrow(results))]
    }

    cat("✓ DE pre-filtering complete:", length(sig_genes), "features retained\n")
    return(expression[sig_genes, , drop = FALSE])
}

#' Prepare validation features to match discovery feature space
#'
#' Maps validation data features to the discovery feature space.
#' Handles cross-platform gene symbol mapping.
#'
#' @param validation_expression Validation expression matrix (genes x samples)
#' @param discovery_features Character vector of feature names from discovery
#' @param log_transform Apply log2(x+1) transformation (default: TRUE)
#'
#' @return list(X_validation, matched_features, n_matched, n_total)
prepare_validation_features <- function(validation_expression, discovery_features,
                                         log_transform = TRUE) {
    cat("Preparing validation features to match discovery space...\n")

    # Find shared features (gene symbol intersection)
    val_features <- rownames(validation_expression)
    matched <- intersect(discovery_features, val_features)

    cat("  Discovery features:", length(discovery_features), "\n")
    cat("  Validation features:", length(val_features), "\n")
    cat("  Matched features:", length(matched),
        "(", round(100 * length(matched) / length(discovery_features), 1), "%)\n")

    if (length(matched) == 0) {
        stop("No features matched between discovery and validation datasets.")
    }

    if (length(matched) < length(discovery_features) * 0.5) {
        cat("  WARNING: Less than 50% of discovery features matched.\n")
        cat("  Cross-platform validation may have reduced power.\n")
    }

    # Subset and align
    expr <- as.matrix(validation_expression[matched, , drop = FALSE])
    storage.mode(expr) <- "numeric"

    # Log transform if needed
    if (log_transform && max(expr, na.rm = TRUE) > 100) {
        cat("  Applying log2(x + 1) transformation\n")
        expr <- log2(expr + 1)
    }

    # Replace NAs
    expr[is.na(expr)] <- 0

    # Scale (using validation data's own mean/sd — acceptable for external validation)
    expr_scaled <- t(scale(t(expr)))
    expr_scaled[is.nan(expr_scaled)] <- 0
    expr_scaled[is.infinite(expr_scaled)] <- 0

    # Transpose to samples x features
    X_val <- t(expr_scaled)

    cat("✓ Validation features prepared\n")
    cat("  X dimensions:", nrow(X_val), "samples x", ncol(X_val), "features\n")

    return(list(
        X = X_val,
        matched_features = matched,
        n_matched = length(matched),
        n_total_discovery = length(discovery_features)
    ))
}

