# External Cohort Validation for LASSO Biomarker Panel
# Validates a locked biomarker panel on independent data
# Computes ROC/AUC with CIs, sensitivity, specificity, PPV, NPV

library(pROC)

#' Validate biomarker panel on an external cohort
#'
#' Applies the locked LASSO model to external validation data and computes
#' comprehensive performance metrics including ROC/AUC with DeLong 95% CI.
#'
#' @param model_result Result from run_lasso_panel()
#' @param validation_X Validation feature matrix (samples x features)
#' @param validation_y Validation binary outcome vector (0/1)
#' @param cohort_name Label for the validation cohort (default: "validation")
#'
#' @return list(auc, auc_ci, roc_object, predictions, performance_table, cohort_name)
validate_panel <- function(model_result, validation_X, validation_y,
                            cohort_name = "validation") {

    cat("\n=== External Validation:", cohort_name, "===\n\n")

    if (is.null(model_result$final_model)) {
        stop("No final model available. Cannot validate.")
    }

    # Check feature overlap
    stable <- model_result$stable_features
    available <- intersect(stable, colnames(validation_X))

    cat("  Panel features:", length(stable), "\n")
    cat("  Available in validation:", length(available),
        "(", round(100 * length(available) / length(stable), 1), "%)\n")

    if (length(available) == 0) {
        stop("No panel features found in validation data. Check gene symbol mapping.")
    }

    missing <- setdiff(stable, available)
    if (length(missing) > 0) {
        cat("  Missing features:", paste(missing, collapse = ", "), "\n")
    }

    # Get predictions
    X_val <- validation_X[, available, drop = FALSE]
    pred_probs <- as.vector(predict(
        model_result$final_model,
        newx = X_val,
        s = "lambda.min",
        type = "response"
    ))
    names(pred_probs) <- rownames(validation_X)

    # Compute ROC/AUC
    cat("\n  Computing ROC/AUC...\n")
    roc_obj <- roc(validation_y, pred_probs, quiet = TRUE)
    auc_val <- auc(roc_obj)
    auc_ci <- ci.auc(roc_obj, method = "delong")

    cat("  AUC:", round(auc_val, 3),
        "(95% CI:", round(auc_ci[1], 3), "-", round(auc_ci[3], 3), ")\n")

    # Optimal threshold (Youden's J)
    optimal <- coords(roc_obj, "best", ret = c("threshold", "sensitivity",
                                                  "specificity", "ppv", "npv"),
                       best.method = "youden")

    # Handle case where coords returns multiple rows
    if (nrow(optimal) > 1) optimal <- optimal[1, , drop = FALSE]

    cat("  Optimal threshold:", round(optimal$threshold, 3), "\n")
    cat("  Sensitivity:", round(optimal$sensitivity, 3), "\n")
    cat("  Specificity:", round(optimal$specificity, 3), "\n")
    cat("  PPV:", round(optimal$ppv, 3), "\n")
    cat("  NPV:", round(optimal$npv, 3), "\n")

    # Build predictions data frame
    predictions <- data.frame(
        sample_id = rownames(validation_X),
        true_label = validation_y,
        predicted_prob = pred_probs,
        predicted_class = ifelse(pred_probs >= optimal$threshold, 1, 0),
        cohort = cohort_name,
        stringsAsFactors = FALSE
    )

    # Performance summary table
    performance_table <- data.frame(
        metric = c("AUC", "AUC_lower_CI", "AUC_upper_CI",
                    "Sensitivity", "Specificity", "PPV", "NPV",
                    "Threshold", "N_samples", "N_positive", "N_negative",
                    "N_panel_features", "N_features_available"),
        value = c(round(auc_val, 4), round(auc_ci[1], 4), round(auc_ci[3], 4),
                  round(optimal$sensitivity, 4), round(optimal$specificity, 4),
                  round(optimal$ppv, 4), round(optimal$npv, 4),
                  round(optimal$threshold, 4),
                  length(validation_y), sum(validation_y == 1), sum(validation_y == 0),
                  length(stable), length(available)),
        stringsAsFactors = FALSE
    )

    cat("\n✓ External validation complete\n")
    cat("  Cohort:", cohort_name, "\n")
    cat("  AUC:", round(auc_val, 3), "(95% CI:",
        round(auc_ci[1], 3), "-", round(auc_ci[3], 3), ")\n")

    return(list(
        auc = as.numeric(auc_val),
        auc_ci = as.numeric(auc_ci),
        roc_object = roc_obj,
        predictions = predictions,
        performance_table = performance_table,
        optimal_threshold = optimal$threshold,
        cohort_name = cohort_name,
        n_features_used = length(available),
        n_features_total = length(stable)
    ))
}

#' Compare biomarker panel AUC vs baseline model
#'
#' Uses DeLong test (pROC::roc.test) to compare two models.
#'
#' @param baseline_preds Predicted probabilities from baseline model
#' @param panel_preds Predicted probabilities from biomarker panel
#' @param true_y True binary outcome
#' @param baseline_name Label for baseline model (default: "baseline")
#' @param panel_name Label for panel model (default: "biomarker_panel")
#'
#' @return list(p_value, baseline_auc, panel_auc, comparison_text)
compare_models <- function(baseline_preds, panel_preds, true_y,
                            baseline_name = "baseline",
                            panel_name = "biomarker_panel") {

    cat("\n=== Model Comparison:", baseline_name, "vs", panel_name, "===\n")

    roc_baseline <- roc(true_y, baseline_preds, quiet = TRUE)
    roc_panel <- roc(true_y, panel_preds, quiet = TRUE)

    # DeLong test
    test_result <- roc.test(roc_baseline, roc_panel, method = "delong")

    baseline_auc <- auc(roc_baseline)
    panel_auc <- auc(roc_panel)

    cat("  ", baseline_name, "AUC:", round(baseline_auc, 3), "\n")
    cat("  ", panel_name, "AUC:", round(panel_auc, 3), "\n")
    cat("  DeLong p-value:", format.pval(test_result$p.value, digits = 3), "\n")

    if (test_result$p.value < 0.05) {
        if (panel_auc > baseline_auc) {
            comparison_text <- paste(panel_name, "significantly outperforms",
                                     baseline_name, "(p =",
                                     format.pval(test_result$p.value, digits = 3), ")")
        } else {
            comparison_text <- paste(baseline_name, "significantly outperforms",
                                     panel_name, "(p =",
                                     format.pval(test_result$p.value, digits = 3), ")")
        }
    } else {
        comparison_text <- paste("No significant difference between models (p =",
                                  format.pval(test_result$p.value, digits = 3), ")")
    }

    cat("  Conclusion:", comparison_text, "\n")

    return(list(
        p_value = test_result$p.value,
        baseline_auc = as.numeric(baseline_auc),
        panel_auc = as.numeric(panel_auc),
        test_result = test_result,
        comparison_text = comparison_text
    ))
}

