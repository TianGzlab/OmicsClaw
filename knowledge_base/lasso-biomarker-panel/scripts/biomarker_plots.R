# Biomarker Panel Visualization Suite
# Publication-quality plots for LASSO biomarker panel results
# All ggplot-based plots use ggprism::theme_prism()
# Heatmaps use ComplexHeatmap + circlize

library(ggplot2)
library(ggprism)
library(pROC)

# Load plotting helpers
source("scripts/plotting_helpers.R")

#' Generate all biomarker panel plots
#'
#' Master function that generates all diagnostic and result plots.
#'
#' @param model_result Result from run_lasso_panel()
#' @param validation_result Result from validate_panel() (optional)
#' @param X Original feature matrix (for heatmap, optional)
#' @param y Original outcome vector (for heatmap, optional)
#' @param output_dir Output directory for plots (default: "results")
generate_all_plots <- function(model_result, validation_result = NULL,
                                X = NULL, y = NULL,
                                output_dir = "results") {

    cat("\n=== Generating Biomarker Panel Plots ===\n\n")

    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
    }

    # 1. ROC curve
    cat("1. ROC Curve\n")
    plot_roc_curve(model_result, validation_result, output_dir)

    # 2. Stability barplot
    cat("\n2. Feature Stability Barplot\n")
    plot_stability_barplot(model_result, output_dir)

    # 3. Coefficient forest plot
    cat("\n3. Coefficient Forest Plot\n")
    plot_coefficient_forest(model_result, output_dir)

    # 4. Calibration curve
    cat("\n4. Calibration Curve\n")
    plot_calibration_curve(model_result, output_dir)

    # 5. AUC distribution
    cat("\n5. AUC Distribution\n")
    plot_auc_distribution(model_result, output_dir)

    # 6. Feature heatmap (if expression data provided)
    if (!is.null(X) && !is.null(y) && length(model_result$stable_features) > 0) {
        cat("\n6. Feature Heatmap\n")
        plot_feature_heatmap(X, y, model_result$stable_features, output_dir)
    } else {
        cat("\n6. Feature Heatmap (skipped - provide X and y for heatmap)\n")
    }

    cat("\n✓ All biomarker plots generated successfully!\n")
}

#' Plot ROC curve with discovery and optional validation overlay
plot_roc_curve <- function(model_result, validation_result = NULL, output_dir = "results") {

    # Build ROC data from CV predictions
    cv_preds <- model_result$cv_predictions

    # Aggregate: average prediction per sample across folds
    agg <- aggregate(predicted_prob ~ sample_id + true_label, data = cv_preds, FUN = mean)
    roc_disc <- roc(agg$true_label, agg$predicted_prob, quiet = TRUE)

    # Build plot data
    roc_df <- data.frame(
        specificity = 1 - roc_disc$specificities,
        sensitivity = roc_disc$sensitivities,
        cohort = paste0("Discovery (CV AUC = ", round(model_result$mean_auc, 3), ")"),
        stringsAsFactors = FALSE
    )

    if (!is.null(validation_result) && !is.null(validation_result$roc_object)) {
        roc_val <- validation_result$roc_object
        val_df <- data.frame(
            specificity = 1 - roc_val$specificities,
            sensitivity = roc_val$sensitivities,
            cohort = paste0(validation_result$cohort_name,
                            " (AUC = ", round(auc(roc_val), 3), ")"),
            stringsAsFactors = FALSE
        )
        roc_df <- rbind(roc_df, val_df)
    }

    p <- ggplot(roc_df, aes(x = specificity, y = sensitivity, color = cohort)) +
        geom_line(linewidth = 1.2) +
        geom_abline(slope = 1, intercept = 0, linetype = "dashed", color = "gray50") +
        scale_color_manual(values = c("#1a3c6e", "#c62828", "#2e7d32", "#e65100")) +
        labs(
            title = "ROC Curve - Biomarker Panel",
            x = "1 - Specificity (False Positive Rate)",
            y = "Sensitivity (True Positive Rate)",
            color = "Cohort"
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            legend.position = c(0.65, 0.25),
            legend.background = element_rect(fill = "white", color = "gray80"),
            legend.text = element_text(size = 10)
        ) +
        coord_equal()

    .save_ggplot(p, file.path(output_dir, "roc_curve"), width = 7, height = 7)
}

#' Plot feature selection stability barplot
plot_stability_barplot <- function(model_result, output_dir = "results") {

    # Get top features by selection frequency
    fi <- model_result$feature_importance
    fi <- fi[fi$selection_frequency > 0, ]
    fi <- fi[order(-fi$selection_frequency), ]

    # Show top 30 features
    n_show <- min(30, nrow(fi))
    fi_top <- fi[1:n_show, ]
    fi_top$feature <- factor(fi_top$feature, levels = rev(fi_top$feature))

    threshold <- model_result$parameters$stability_threshold

    p <- ggplot(fi_top, aes(x = feature, y = selection_frequency,
                             fill = is_stable)) +
        geom_col(width = 0.7) +
        geom_hline(yintercept = threshold, linetype = "dashed",
                   color = "#c62828", linewidth = 0.8) +
        annotate("text", x = 1, y = threshold + 0.02,
                 label = paste0("Stability threshold (", threshold * 100, "%)"),
                 hjust = 0, color = "#c62828", size = 3.5) +
        scale_fill_manual(values = c("TRUE" = "#1a3c6e", "FALSE" = "#cccccc"),
                          labels = c("TRUE" = "Stable", "FALSE" = "Not stable"),
                          name = "Status") +
        labs(
            title = "Feature Selection Stability",
            subtitle = paste("Top", n_show, "features across",
                             model_result$parameters$n_repeats, "CV iterations"),
            x = NULL,
            y = "Selection Frequency"
        ) +
        theme_prism(base_size = 11) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10),
            axis.text.y = element_text(size = 9)
        ) +
        coord_flip() +
        scale_y_continuous(limits = c(0, 1), breaks = seq(0, 1, 0.2))

    .save_ggplot(p, file.path(output_dir, "stability_barplot"),
                 width = 10, height = max(6, n_show * 0.3))
}

#' Plot coefficient forest plot for stable features
plot_coefficient_forest <- function(model_result, output_dir = "results") {

    stable <- model_result$stable_features
    if (length(stable) == 0) {
        cat("   No stable features to plot.\n")
        return(invisible(NULL))
    }

    # Get coefficient stats from coef_matrix
    coef_mat <- model_result$coef_matrix[, stable, drop = FALSE]

    forest_data <- data.frame(
        feature = stable,
        mean_coef = colMeans(coef_mat, na.rm = TRUE),
        sd_coef = apply(coef_mat, 2, sd, na.rm = TRUE),
        stringsAsFactors = FALSE
    )
    forest_data$lower <- forest_data$mean_coef - 1.96 * forest_data$sd_coef
    forest_data$upper <- forest_data$mean_coef + 1.96 * forest_data$sd_coef
    forest_data$direction <- ifelse(forest_data$mean_coef > 0, "Positive", "Negative")
    forest_data <- forest_data[order(forest_data$mean_coef), ]
    forest_data$feature <- factor(forest_data$feature, levels = forest_data$feature)

    p <- ggplot(forest_data, aes(x = feature, y = mean_coef, color = direction)) +
        geom_point(size = 3) +
        geom_errorbar(aes(ymin = lower, ymax = upper), width = 0.3, linewidth = 0.8) +
        geom_hline(yintercept = 0, linetype = "dashed", color = "gray50") +
        scale_color_manual(values = c("Positive" = "#c62828", "Negative" = "#1a3c6e")) +
        labs(
            title = "LASSO Coefficient Forest Plot",
            subtitle = paste(length(stable), "stable features with 95% CI across CV folds"),
            x = NULL,
            y = "Mean LASSO Coefficient",
            color = "Direction"
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10)
        ) +
        coord_flip()

    .save_ggplot(p, file.path(output_dir, "coefficient_forest"),
                 width = 9, height = max(5, length(stable) * 0.5))
}

#' Plot calibration curve
plot_calibration_curve <- function(model_result, output_dir = "results") {

    cv_preds <- model_result$cv_predictions
    # Aggregate predictions per sample
    agg <- aggregate(predicted_prob ~ sample_id + true_label, data = cv_preds, FUN = mean)

    # Create calibration bins
    n_bins <- 10
    agg$bin <- cut(agg$predicted_prob, breaks = seq(0, 1, length.out = n_bins + 1),
                   include.lowest = TRUE)

    cal_data <- aggregate(
        cbind(observed = true_label, predicted = predicted_prob) ~ bin,
        data = agg, FUN = mean
    )
    # Count samples per bin — match only bins present in cal_data (aggregate drops empty bins)
    bin_counts <- table(agg$bin)
    cal_data$n <- as.numeric(bin_counts[as.character(cal_data$bin)])

    p <- ggplot(cal_data, aes(x = predicted, y = observed)) +
        geom_abline(slope = 1, intercept = 0, linetype = "dashed", color = "gray50") +
        geom_point(aes(size = n), color = "#1a3c6e") +
        geom_line(color = "#1a3c6e", linewidth = 1) +
        scale_size_continuous(range = c(2, 8), name = "N samples") +
        labs(
            title = "Calibration Curve",
            subtitle = "Predicted vs observed probability (CV aggregated)",
            x = "Mean Predicted Probability",
            y = "Observed Proportion"
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10)
        ) +
        coord_equal(xlim = c(0, 1), ylim = c(0, 1))

    .save_ggplot(p, file.path(output_dir, "calibration_curve"), width = 7, height = 7)
}

#' Plot AUC distribution across CV folds
plot_auc_distribution <- function(model_result, output_dir = "results") {

    valid_aucs <- model_result$fold_aucs[!is.na(model_result$fold_aucs)]
    auc_df <- data.frame(auc = valid_aucs)

    p <- ggplot(auc_df, aes(x = auc)) +
        geom_histogram(bins = 20, fill = "#1a3c6e", color = "white", alpha = 0.8) +
        geom_vline(xintercept = model_result$mean_auc,
                   linetype = "solid", color = "#c62828", linewidth = 1) +
        geom_vline(xintercept = model_result$auc_ci,
                   linetype = "dashed", color = "#c62828", linewidth = 0.6) +
        annotate("text",
                 x = model_result$mean_auc, y = Inf,
                 label = paste0("Mean = ", round(model_result$mean_auc, 3)),
                 vjust = 2, hjust = -0.1, color = "#c62828", fontface = "bold") +
        labs(
            title = "AUC Distribution Across CV Folds",
            subtitle = paste(length(valid_aucs), "iterations, 95% CI shown"),
            x = "AUC",
            y = "Count"
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10)
        )

    .save_ggplot(p, file.path(output_dir, "auc_distribution"), width = 8, height = 6)
}

#' Plot heatmap of panel features across samples
#'
#' Uses ComplexHeatmap for publication-quality clustered heatmap.
#'
#' @param X Feature matrix (samples x features)
#' @param y Binary outcome vector
#' @param stable_features Character vector of panel feature names
#' @param output_dir Output directory
plot_feature_heatmap <- function(X, y, stable_features, output_dir = "results") {

    if (!requireNamespace("ComplexHeatmap", quietly = TRUE)) {
        cat("   ComplexHeatmap not available. Skipping heatmap.\n")
        return(invisible(NULL))
    }
    if (!requireNamespace("circlize", quietly = TRUE)) {
        cat("   circlize not available. Skipping heatmap.\n")
        return(invisible(NULL))
    }

    library(ComplexHeatmap)
    library(circlize)

    # Get panel features
    available <- intersect(stable_features, colnames(X))
    if (length(available) == 0) {
        cat("   No panel features found in X matrix.\n")
        return(invisible(NULL))
    }

    # Extract and scale
    mat <- t(X[, available, drop = FALSE])  # features x samples

    # Z-score by feature
    mat_scaled <- t(scale(t(mat)))
    mat_scaled[is.nan(mat_scaled)] <- 0

    # Color function
    col_fun <- colorRamp2(c(-2, 0, 2), c("#1a3c6e", "white", "#c62828"))

    # Outcome annotation
    outcome_colors <- c("0" = "#0072B2", "1" = "#E69F00")  # colorblind-safe blue/orange
    names(outcome_colors) <- c("0", "1")
    ha <- HeatmapAnnotation(
        Outcome = as.character(y),
        col = list(Outcome = outcome_colors),
        annotation_name_side = "left"
    )

    # Create heatmap
    ht <- Heatmap(
        mat_scaled,
        name = "Z-score",
        col = col_fun,
        top_annotation = ha,
        show_column_names = FALSE,
        row_names_gp = gpar(fontsize = 10),
        column_title = paste("Biomarker Panel:", length(available), "Features"),
        column_title_gp = gpar(fontsize = 14, fontface = "bold"),
        clustering_distance_columns = "euclidean",
        clustering_method_columns = "ward.D2",
        clustering_distance_rows = "euclidean",
        clustering_method_rows = "ward.D2"
    )

    .save_base_plot(
        quote(draw(ht)),
        file.path(output_dir, "feature_heatmap"),
        width = max(8, ncol(mat) * 0.05 + 3),
        height = max(5, nrow(mat) * 0.4 + 2)
    )
}

