# =============================================================================
# Survival Analysis Plots
# =============================================================================
# Publication-quality survival visualizations:
#   1. Kaplan-Meier curves (overall + stratified)
#   2. Forest plot of hazard ratios
#   3. Risk group KM curves
#   4. Schoenfeld residual diagnostics
#   5. Cumulative hazard plot
#
# Usage:
#   source("scripts/survival_plots.R")
#   generate_all_plots(result, output_dir = "results")
# =============================================================================

library(survival)
library(ggplot2)
library(ggprism)

# Try survminer (optional but recommended for KM curves with risk tables)
.has_survminer <- requireNamespace("survminer", quietly = TRUE)
if (.has_survminer) library(survminer)

# Try svglite for high-quality SVG
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) library(svglite)


# =============================================================================
# survfit helper: stores formula literally for survminer compatibility
# =============================================================================

.safe_survfit <- function(formula, data) {
    do.call(survfit, list(formula = formula, data = data))
}

# =============================================================================
# Save Helper: PNG + SVG with graceful fallback
# =============================================================================

.save_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300,
                       is_survminer = FALSE) {
    png_path <- paste0(sub("\\.(svg|png)$", "", base_path), ".png")
    svg_path <- paste0(sub("\\.(svg|png)$", "", base_path), ".svg")

    if (is_survminer) {
        # survminer objects need png()/svg() device + print()
        png(png_path, width = width, height = height, units = "in", res = dpi)
        print(plot)
        dev.off()
        cat("   Saved:", png_path, "\n")

        tryCatch({
            svg(svg_path, width = width, height = height)
            print(plot)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e) {
            cat("   (SVG export failed for survminer plot)\n")
        })
    } else {
        # Standard ggplot objects
        ggsave(png_path, plot = plot, width = width, height = height,
               dpi = dpi, device = "png")
        cat("   Saved:", png_path, "\n")

        tryCatch({
            ggsave(svg_path, plot = plot, width = width, height = height,
                   device = "svg")
            cat("   Saved:", svg_path, "\n")
        }, error = function(e) {
            tryCatch({
                svg(svg_path, width = width, height = height)
                print(plot)
                dev.off()
                cat("   Saved:", svg_path, "\n")
            }, error = function(e2) {
                cat("   (SVG export failed)\n")
            })
        })
    }
}


# =============================================================================
# Orchestrator
# =============================================================================

generate_all_plots <- function(result, output_dir = "results") {
    cat("\n=== Generating Survival Plots ===\n\n")

    if (!dir.exists(output_dir)) dir.create(output_dir, recursive = TRUE)

    # 1. KM overall
    cat("1. Kaplan-Meier survival curve (overall)...\n")
    km_overall <- plot_km_overall(result)
    .save_plot(km_overall, file.path(output_dir, "km_overall"),
               width = 8, height = 7, is_survminer = .has_survminer)

    # 2. KM stratified
    if (!is.null(result$km_strata)) {
        cat("\n2. Kaplan-Meier curves (stratified by ",
            result$strata_col, ")...\n", sep = "")
        km_strata <- plot_km_stratified(result)
        .save_plot(km_strata, file.path(output_dir, "km_stratified"),
                   width = 10, height = 8, is_survminer = .has_survminer)
    } else {
        cat("\n2. Skipping stratified KM (no strata)\n")
    }

    # 3. Forest plot
    cat("\n3. Forest plot of hazard ratios...\n")
    forest <- plot_forest(result$cox$coefficients)
    .save_plot(forest, file.path(output_dir, "forest_plot"),
               width = 10, height = max(4, 0.6 * nrow(result$cox$coefficients) + 2))

    # 4. Risk group KM
    if (!is.null(result$km_risk)) {
        cat("\n4. Risk group Kaplan-Meier curves...\n")
        km_risk <- plot_risk_groups(result)
        .save_plot(km_risk, file.path(output_dir, "km_risk_groups"),
                   width = 9, height = 7, is_survminer = .has_survminer)
    }

    # 5. Schoenfeld residuals (PH diagnostics)
    cat("\n5. Schoenfeld residual diagnostics...\n")
    diag <- plot_diagnostics(result$ph_test, output_dir)

    # 6. Cumulative hazard
    cat("\n6. Cumulative hazard plot...\n")
    cumhaz <- plot_cumulative_hazard(result)
    .save_plot(cumhaz, file.path(output_dir, "cumulative_hazard"))

    cat("\n✓ All survival plots generated successfully!\n")
}


# =============================================================================
# Plot 1: Kaplan-Meier Overall
# =============================================================================

plot_km_overall <- function(result) {
    clinical <- result$clinical
    time_col <- result$time_col
    event_col <- result$event_col
    f <- as.formula(paste0("Surv(", time_col, ", ", event_col, ") ~ 1"))
    fit <- .safe_survfit(f, clinical)

    if (.has_survminer) {
        p <- ggsurvplot(
            fit, data = clinical,
            risk.table = TRUE,
            risk.table.col = "strata",
            conf.int = TRUE,
            surv.median.line = "hv",
            palette = "#2E86C1",
            title = paste("Overall Survival -", result$dataset_name),
            xlab = "Time (years)",
            ylab = "Survival Probability",
            ggtheme = theme_prism(base_size = 12),
            risk.table.y.text = FALSE,
            fontsize = 3.5
        )
        return(p)
    }

    # Fallback: base ggplot2
    surv_data <- data.frame(
        time = fit$time,
        surv = fit$surv,
        lower = fit$lower,
        upper = fit$upper
    )

    ggplot(surv_data, aes(x = time, y = surv)) +
        geom_step(color = "#2E86C1", linewidth = 1) +
        geom_ribbon(aes(ymin = lower, ymax = upper), alpha = 0.2, fill = "#2E86C1",
                    stat = "identity") +
        geom_hline(yintercept = 0.5, linetype = "dashed", color = "grey50") +
        scale_y_continuous(labels = scales::percent_format(), limits = c(0, 1)) +
        labs(title = paste("Overall Survival -", result$dataset_name),
             x = "Time (years)", y = "Survival Probability") +
        theme_prism(base_size = 12) +
        theme(plot.title = element_text(hjust = 0.5, face = "bold", size = 14))
}


# =============================================================================
# Plot 2: Kaplan-Meier Stratified
# =============================================================================

plot_km_stratified <- function(result) {
    clinical <- result$clinical
    time_col <- result$time_col
    event_col <- result$event_col
    strata_col <- result$strata_col

    strata_data <- clinical[!is.na(clinical[[strata_col]]), ]
    f <- as.formula(paste0("Surv(", time_col, ", ", event_col, ") ~ ", strata_col))
    fit <- .safe_survfit(f, strata_data)

    # Log-rank test
    lr <- survdiff(f, data = strata_data)
    lr_p <- 1 - pchisq(lr$chisq, length(lr$n) - 1)

    # Color palette (up to 8 groups)
    n_groups <- length(lr$n)
    colors <- c("#E74C3C", "#2E86C1", "#27AE60", "#F39C12",
                "#8E44AD", "#1ABC9C", "#D35400", "#34495E")[1:n_groups]

    if (.has_survminer) {
        p <- ggsurvplot(
            fit, data = strata_data,
            risk.table = TRUE,
            pval = TRUE,
            pval.method = TRUE,
            conf.int = TRUE,
            palette = colors,
            title = paste("Survival by", strata_col, "-", result$dataset_name),
            xlab = "Time (years)",
            ylab = "Survival Probability",
            legend.title = strata_col,
            ggtheme = theme_prism(base_size = 12),
            risk.table.y.text = FALSE,
            fontsize = 3.5
        )
        return(p)
    }

    # Fallback
    surv_df <- .extract_surv_data(fit, strata_col)
    ggplot(surv_df, aes(x = time, y = surv, color = strata)) +
        geom_step(linewidth = 1) +
        scale_color_manual(values = colors) +
        scale_y_continuous(labels = scales::percent_format(), limits = c(0, 1)) +
        labs(title = paste("Survival by", strata_col, "-", result$dataset_name),
             subtitle = paste("Log-rank p =", format.pval(lr_p, digits = 3)),
             x = "Time (years)", y = "Survival Probability",
             color = strata_col) +
        theme_prism(base_size = 12) +
        theme(plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
              plot.subtitle = element_text(hjust = 0.5, size = 11))
}


# =============================================================================
# Plot 3: Forest Plot of Hazard Ratios
# =============================================================================

plot_forest <- function(coef_df) {
    df <- coef_df
    # Remove rows with NA/Inf values that can't be plotted
    df <- df[is.finite(df$hazard_ratio) & is.finite(df$hr_lower) &
             is.finite(df$hr_upper) & !is.na(df$pval), ]
    df$variable <- factor(df$variable, levels = rev(df$variable))

    # Significance labels
    df$sig <- ifelse(df$pval < 0.001, "***",
              ifelse(df$pval < 0.01, "**",
              ifelse(df$pval < 0.05, "*", "")))
    df$label <- paste0(
        sprintf("%.2f", df$hazard_ratio),
        " (", sprintf("%.2f", df$hr_lower), "-", sprintf("%.2f", df$hr_upper), ")",
        " ", df$sig
    )

    # Color by significance
    df$significant <- df$pval < 0.05

    # X-axis limits (log scale)
    x_min <- min(df$hr_lower, na.rm = TRUE) * 0.7
    x_max <- max(df$hr_upper, na.rm = TRUE) * 1.3

    ggplot(df, aes(x = hazard_ratio, y = variable)) +
        geom_vline(xintercept = 1, linetype = "dashed", color = "grey50",
                   linewidth = 0.5) +
        geom_errorbar(aes(xmin = hr_lower, xmax = hr_upper),
                      width = 0.25, linewidth = 0.7, color = "grey30") +
        geom_point(aes(color = significant, size = significant)) +
        geom_text(aes(label = label), hjust = -0.1, vjust = -0.8, size = 3.2) +
        scale_color_manual(values = c("FALSE" = "grey50", "TRUE" = "#E74C3C"),
                          guide = "none") +
        scale_size_manual(values = c("FALSE" = 2.5, "TRUE" = 3.5), guide = "none") +
        scale_x_log10(limits = c(x_min, x_max)) +
        labs(title = "Hazard Ratios (Cox PH Model)",
             subtitle = "* p<0.05, ** p<0.01, *** p<0.001",
             x = "Hazard Ratio (log scale)",
             y = NULL) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10, color = "grey40"),
            axis.text.y = element_text(size = 11)
        )
}


# =============================================================================
# Plot 4: Risk Group KM Curves
# =============================================================================

plot_risk_groups <- function(result) {
    clinical <- result$clinical
    time_col <- result$time_col
    event_col <- result$event_col
    risk_col <- result$risk_col

    risk_data <- clinical[!is.na(clinical[[risk_col]]), ]
    f <- as.formula(paste0("Surv(", time_col, ", ", event_col, ") ~ ", risk_col))
    fit <- .safe_survfit(f, risk_data)

    lr <- survdiff(f, data = risk_data)
    lr_p <- 1 - pchisq(lr$chisq, length(lr$n) - 1)

    n_groups <- length(unique(risk_data[[risk_col]]))
    colors <- c("#E74C3C", "#2E86C1", "#27AE60", "#F39C12")[1:n_groups]

    if (.has_survminer) {
        p <- ggsurvplot(
            fit, data = risk_data,
            risk.table = TRUE,
            pval = TRUE,
            pval.method = TRUE,
            conf.int = TRUE,
            palette = colors,
            title = paste("Survival by Risk Group -", result$dataset_name),
            subtitle = paste("Risk stratification method:",
                           result$risk_strata_method),
            xlab = "Time (years)",
            ylab = "Survival Probability",
            legend.title = "Risk Group",
            ggtheme = theme_prism(base_size = 12),
            risk.table.y.text = FALSE,
            fontsize = 3.5
        )
        return(p)
    }

    # Fallback
    surv_df <- .extract_surv_data(fit, risk_col)
    ggplot(surv_df, aes(x = time, y = surv, color = strata)) +
        geom_step(linewidth = 1) +
        scale_color_manual(values = colors) +
        scale_y_continuous(labels = scales::percent_format(), limits = c(0, 1)) +
        labs(title = paste("Survival by Risk Group -", result$dataset_name),
             subtitle = paste("Log-rank p =", format.pval(lr_p, digits = 3)),
             x = "Time (years)", y = "Survival Probability",
             color = "Risk Group") +
        theme_prism(base_size = 12) +
        theme(plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
              plot.subtitle = element_text(hjust = 0.5, size = 11))
}


# =============================================================================
# Plot 5: Schoenfeld Residual Diagnostics
# =============================================================================

plot_diagnostics <- function(ph_test, output_dir = "results") {
    n_vars <- nrow(ph_test$table) - 1  # Exclude GLOBAL row

    # Save as multi-panel PNG
    png_path <- file.path(output_dir, "schoenfeld_diagnostics.png")
    png(png_path, width = 10, height = max(4, 3 * ceiling(n_vars / 2)),
        units = "in", res = 300)
    par(mfrow = c(ceiling(n_vars / 2), min(2, n_vars)))
    plot(ph_test)
    dev.off()
    cat("   Saved:", png_path, "\n")

    # SVG
    svg_path <- file.path(output_dir, "schoenfeld_diagnostics.svg")
    tryCatch({
        svg(svg_path, width = 10, height = max(4, 3 * ceiling(n_vars / 2)))
        par(mfrow = c(ceiling(n_vars / 2), min(2, n_vars)))
        plot(ph_test)
        dev.off()
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        cat("   (SVG export failed for diagnostics)\n")
    })

    invisible(ph_test)
}


# =============================================================================
# Plot 6: Cumulative Hazard
# =============================================================================

plot_cumulative_hazard <- function(result) {
    clinical <- result$clinical
    time_col <- result$time_col
    event_col <- result$event_col

    f <- as.formula(paste0("Surv(", time_col, ", ", event_col, ") ~ 1"))
    fit <- .safe_survfit(f, clinical)

    cumhaz_df <- data.frame(
        time = fit$time,
        cumhaz = fit$cumhaz
    )

    ggplot(cumhaz_df, aes(x = time, y = cumhaz)) +
        geom_step(color = "#2E86C1", linewidth = 1) +
        labs(title = paste("Cumulative Hazard -", result$dataset_name),
             x = "Time (years)", y = "Cumulative Hazard") +
        theme_prism(base_size = 12) +
        theme(plot.title = element_text(hjust = 0.5, face = "bold", size = 14))
}


# =============================================================================
# Helper: Extract survfit data for fallback ggplot
# =============================================================================

.extract_surv_data <- function(fit, strata_name) {
    strata_labels <- names(fit$strata)
    strata_labels <- sub(paste0("^", strata_name, "="), "", strata_labels)

    strata_vec <- rep(strata_labels, fit$strata)
    data.frame(
        time = fit$time,
        surv = fit$surv,
        strata = strata_vec,
        stringsAsFactors = FALSE
    )
}

