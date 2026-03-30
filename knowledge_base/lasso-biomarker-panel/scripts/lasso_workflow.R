# LASSO Biomarker Panel Discovery Workflow
# Core pipeline: nested CV LASSO with stability selection
# Reference: Ali et al., Nature Medicine 2025 (github.com/NeuroGenomicsAndInformatics/NatMed_2025_GNPC)
#
# Pipeline:
#   1. Repeated nested CV (50 iterations, 70/30 class-balanced splits)
#   2. Inner CV (cv.glmnet, 10-fold) for lambda selection per iteration
#   3. Feature tracking across iterations
#   4. Stability selection (features in >80% of iterations)
#   5. Final model on full discovery data with stable features
#   6. Per-fold AUC estimation via pROC

# Required packages
library(glmnet)
library(pROC)

#' Run LASSO biomarker panel selection with stability analysis
#'
#' Implements the Ali et al. (Nat Med 2025) pipeline:
#' - Repeated 70/30 train/test splits with class balancing
#' - cv.glmnet for optimal lambda per split
#' - Feature selection frequency tracking
#' - Stability selection (features in > threshold fraction of splits)
#' - Final locked model for clinical use
#'
#' @param X Feature matrix (samples x features), scaled
#' @param y Binary outcome vector (0/1)
#' @param n_repeats Number of repeated CV iterations (default: 50)
#' @param train_fraction Fraction of data for training (default: 0.7)
#' @param alpha Elastic net mixing parameter: 1=LASSO, 0=Ridge (default: 1.0)
#' @param n_inner_folds Folds for inner CV lambda selection (default: 10)
#' @param stability_threshold Min selection frequency for stable features (default: 0.8)
#' @param top_n_features Max features to select per iteration (default: NULL = all non-zero)
#' @param seed Random seed for reproducibility (default: 42)
#'
#' @return list with final_model, stable_features, feature_importance, fold_aucs, etc.
run_lasso_panel <- function(X, y,
                             n_repeats = 50,
                             train_fraction = 0.7,
                             alpha = 1.0,
                             n_inner_folds = 10,
                             stability_threshold = 0.8,
                             top_n_features = NULL,
                             seed = 42) {

    cat("\n=== LASSO Biomarker Panel Selection ===\n\n")
    cat("Parameters:\n")
    cat("  Samples:", nrow(X), "| Features:", ncol(X), "\n")
    cat("  Outcome: ", sum(y == 1), "positives,", sum(y == 0), "negatives\n")
    cat("  Repeats:", n_repeats, "| Train fraction:", train_fraction, "\n")
    cat("  Alpha:", alpha, ifelse(alpha == 1, "(pure LASSO)", "(elastic net)"), "\n")
    cat("  Inner CV folds:", n_inner_folds, "\n")
    cat("  Stability threshold:", stability_threshold, "\n\n")

    set.seed(seed)
    feature_names <- colnames(X)
    n_samples <- nrow(X)
    n_train <- round(n_samples * train_fraction)

    # Track feature selection across iterations
    selection_count <- rep(0, ncol(X))
    names(selection_count) <- feature_names

    # Track coefficients across iterations
    coef_matrix <- matrix(0, nrow = n_repeats, ncol = ncol(X))
    colnames(coef_matrix) <- feature_names

    # Track per-fold performance
    fold_aucs <- numeric(n_repeats)
    fold_sensitivities <- numeric(n_repeats)
    fold_specificities <- numeric(n_repeats)
    all_predictions <- data.frame()

    cat("Running", n_repeats, "iterations...\n")
    pb_interval <- max(1, n_repeats %/% 10)

    for (i in seq_len(n_repeats)) {
        if (i %% pb_interval == 0 || i == 1) {
            cat("  Iteration", i, "/", n_repeats, "...")
        }

        # Class-balanced train/test split
        idx_pos <- which(y == 1)
        idx_neg <- which(y == 0)
        n_train_pos <- round(length(idx_pos) * train_fraction)
        n_train_neg <- round(length(idx_neg) * train_fraction)

        train_pos <- sample(idx_pos, n_train_pos)
        train_neg <- sample(idx_neg, n_train_neg)
        train_idx <- c(train_pos, train_neg)
        test_idx <- setdiff(seq_len(n_samples), train_idx)

        X_train <- X[train_idx, , drop = FALSE]
        y_train <- y[train_idx]
        X_test <- X[test_idx, , drop = FALSE]
        y_test <- y[test_idx]

        # Inner CV for lambda selection
        cv_fit <- tryCatch({
            cv.glmnet(
                x = X_train,
                y = y_train,
                family = "binomial",
                alpha = alpha,
                nfolds = min(n_inner_folds, length(y_train)),
                type.measure = "auc",
                standardize = FALSE  # Already scaled
            )
        }, error = function(e) {
            cat(" (cv.glmnet error in fold", i, ":", conditionMessage(e), ")\n")
            return(NULL)
        })

        if (is.null(cv_fit)) {
            fold_aucs[i] <- NA
            next
        }

        # Extract selected features at lambda.min
        coefs <- as.vector(coef(cv_fit, s = "lambda.min"))[-1]  # Remove intercept
        names(coefs) <- feature_names
        selected <- which(coefs != 0)

        if (length(selected) > 0) {
            # Track selection
            selection_count[selected] <- selection_count[selected] + 1

            # Track coefficients
            coef_matrix[i, selected] <- coefs[selected]

            # Limit to top N if requested
            if (!is.null(top_n_features) && length(selected) > top_n_features) {
                top_idx <- order(abs(coefs[selected]), decreasing = TRUE)[1:top_n_features]
                selected <- selected[top_idx]
            }
        }

        # Predict on test set
        pred_probs <- as.vector(predict(cv_fit, newx = X_test,
                                         s = "lambda.min", type = "response"))

        # Calculate AUC
        if (length(unique(y_test)) == 2) {
            roc_obj <- tryCatch(
                roc(y_test, pred_probs, quiet = TRUE),
                error = function(e) NULL
            )
            if (!is.null(roc_obj)) {
                fold_aucs[i] <- auc(roc_obj)
                # Sensitivity/specificity at optimal threshold (Youden)
                coords <- coords(roc_obj, "best", ret = c("sensitivity", "specificity"))
                fold_sensitivities[i] <- coords$sensitivity[1]
                fold_specificities[i] <- coords$specificity[1]
            }
        }

        # Store predictions
        fold_preds <- data.frame(
            sample_id = rownames(X_test),
            true_label = y_test,
            predicted_prob = pred_probs,
            fold = i,
            stringsAsFactors = FALSE
        )
        all_predictions <- rbind(all_predictions, fold_preds)

        if (i %% pb_interval == 0 || i == 1) {
            cat(" AUC =", round(fold_aucs[i], 3),
                "| Selected:", length(selected), "features\n")
        }
    }

    # ---- Stability Selection ----
    cat("\n--- Stability Selection ---\n")
    valid_folds <- sum(!is.na(fold_aucs))
    selection_freq <- selection_count / valid_folds
    stable_features <- names(selection_freq[selection_freq >= stability_threshold])

    cat("  Valid iterations:", valid_folds, "/", n_repeats, "\n")
    cat("  Features selected at least once:", sum(selection_count > 0), "\n")
    cat("  Stable features (>", stability_threshold * 100, "%):",
        length(stable_features), "\n")

    if (length(stable_features) < 2) {
        if (length(stable_features) == 0) {
            cat("  WARNING: No features passed stability threshold.\n")
        } else {
            cat("  WARNING: Only", length(stable_features), "feature passed threshold.\n")
        }
        cat("  Relaxing to top 10 most frequently selected features.\n")
        top_10 <- names(sort(selection_freq, decreasing = TRUE))[1:min(10, length(selection_freq))]
        stable_features <- top_10[selection_freq[top_10] > 0]
        # Ensure at least 2 features for glmnet
        if (length(stable_features) < 2) {
            stable_features <- names(sort(selection_freq, decreasing = TRUE))[1:2]
        }
        cat("  Using", length(stable_features), "features (frequency:",
            round(min(selection_freq[stable_features]), 3), "-",
            round(max(selection_freq[stable_features]), 3), ")\n")
    }

    cat("  Stable feature panel:\n")
    for (feat in stable_features) {
        cat("    -", feat, "(selected in",
            round(selection_freq[feat] * 100, 1), "% of folds)\n")
    }

    # ---- Feature Importance Table ----
    feature_importance <- data.frame(
        feature = feature_names,
        selection_frequency = selection_freq,
        mean_coefficient = colMeans(coef_matrix, na.rm = TRUE),
        sd_coefficient = apply(coef_matrix, 2, sd, na.rm = TRUE),
        is_stable = feature_names %in% stable_features,
        stringsAsFactors = FALSE
    )
    feature_importance <- feature_importance[order(-feature_importance$selection_frequency), ]

    # ---- Final Model ----
    cat("\n--- Final Model (locked panel) ---\n")

    if (length(stable_features) > 0) {
        # Fit final model using only stable features on full discovery data
        X_stable <- X[, stable_features, drop = FALSE]

        final_cv <- cv.glmnet(
            x = X_stable,
            y = y,
            family = "binomial",
            alpha = alpha,
            nfolds = min(n_inner_folds, length(y)),
            type.measure = "auc",
            standardize = FALSE
        )

        final_model <- final_cv

        # Final model AUC on full data (training AUC — for reference only)
        final_preds <- as.vector(predict(final_cv, newx = X_stable,
                                          s = "lambda.min", type = "response"))
        final_roc <- roc(y, final_preds, quiet = TRUE)
        cat("  Final model AUC (training, for reference):", round(auc(final_roc), 3), "\n")
        cat("  Note: Use CV AUC below for unbiased performance estimate\n")
    } else {
        final_model <- NULL
        cat("  WARNING: No stable features found. Final model not created.\n")
    }

    # ---- Summary Statistics ----
    valid_aucs <- fold_aucs[!is.na(fold_aucs)]
    mean_auc <- mean(valid_aucs)
    auc_ci <- quantile(valid_aucs, c(0.025, 0.975))

    cat("\n--- Cross-Validation Performance ---\n")
    cat("  Mean AUC:", round(mean_auc, 3),
        "(95% CI:", round(auc_ci[1], 3), "-", round(auc_ci[2], 3), ")\n")
    cat("  Mean Sensitivity:", round(mean(fold_sensitivities, na.rm = TRUE), 3), "\n")
    cat("  Mean Specificity:", round(mean(fold_specificities, na.rm = TRUE), 3), "\n")

    # ---- Compile Results ----
    result <- list(
        final_model = final_model,
        stable_features = stable_features,
        feature_importance = feature_importance,
        fold_aucs = fold_aucs,
        mean_auc = mean_auc,
        auc_ci = auc_ci,
        fold_sensitivities = fold_sensitivities,
        fold_specificities = fold_specificities,
        cv_predictions = all_predictions,
        selection_frequencies = selection_freq,
        coef_matrix = coef_matrix,
        parameters = list(
            n_repeats = n_repeats,
            train_fraction = train_fraction,
            alpha = alpha,
            n_inner_folds = n_inner_folds,
            stability_threshold = stability_threshold,
            seed = seed,
            n_samples = nrow(X),
            n_features = ncol(X),
            n_stable = length(stable_features)
        )
    )

    cat("\n✓ LASSO panel selection completed successfully!\n")
    cat("  Panel size:", length(stable_features), "features\n")
    cat("  CV AUC:", round(mean_auc, 3), "\n")

    return(result)
}

#' Apply locked biomarker panel to new data
#'
#' @param model_result Result from run_lasso_panel()
#' @param new_X New feature matrix (samples x features)
#'
#' @return Predicted probabilities
predict_biomarker_panel <- function(model_result, new_X) {
    if (is.null(model_result$final_model)) {
        stop("No final model available. Panel selection may have failed.")
    }

    # Subset to stable features
    stable <- model_result$stable_features
    available <- intersect(stable, colnames(new_X))

    if (length(available) == 0) {
        stop("None of the panel features found in new data.")
    }

    if (length(available) < length(stable)) {
        cat("WARNING:", length(stable) - length(available),
            "panel features missing from new data.\n")
        cat("  Available:", length(available), "/", length(stable), "\n")
    }

    # Predict
    preds <- as.vector(predict(
        model_result$final_model,
        newx = new_X[, available, drop = FALSE],
        s = "lambda.min",
        type = "response"
    ))

    names(preds) <- rownames(new_X)
    return(preds)
}

