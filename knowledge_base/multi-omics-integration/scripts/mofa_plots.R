# =============================================================================
# MOFA+ Visualization: Publication-Quality Plots
# =============================================================================
# Generates 7 plots using ggprism::theme_prism() and ComplexHeatmap.
# All plots saved as PNG + SVG with graceful fallback.
# =============================================================================

options(repos = c(CRAN = "https://cloud.r-project.org"))

.install_if_missing <- function(pkg, bioc = FALSE) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
        cat("Installing", pkg, "...\n")
        if (bioc) {
            if (!requireNamespace("BiocManager", quietly = TRUE))
                install.packages("BiocManager")
            BiocManager::install(pkg, ask = FALSE, update = FALSE)
        } else {
            install.packages(pkg)
        }
    }
}

# --- Load required packages ---
.load_plot_packages <- function() {
    .install_if_missing("ggplot2")
    .install_if_missing("ggprism")
    .install_if_missing("reshape2")
    .install_if_missing("RColorBrewer")
    .install_if_missing("ComplexHeatmap", bioc = TRUE)
    .install_if_missing("circlize")
    .install_if_missing("MOFA2", bioc = TRUE)

    library(ggplot2)
    library(ggprism)
    library(reshape2)
    library(RColorBrewer)
    library(ComplexHeatmap)
    library(circlize)
    library(MOFA2)
    library(grid)
}

# --- PNG + SVG save helper ---
.save_plot <- function(plot_obj, base_name, output_dir, width = 8, height = 6, dpi = 300) {
    png_path <- file.path(output_dir, paste0(base_name, ".png"))
    svg_path <- file.path(output_dir, paste0(base_name, ".svg"))

    # Always save PNG
    ggsave(png_path, plot = plot_obj, width = width, height = height, dpi = dpi, device = "png")
    cat(sprintf("   Saved: %s\n", png_path))

    # Try SVG with fallback
    tryCatch({
        ggsave(svg_path, plot = plot_obj, width = width, height = height, device = "svg")
        cat(sprintf("   Saved: %s\n", svg_path))
    }, error = function(e) {
        tryCatch({
            svg(svg_path, width = width, height = height)
            print(plot_obj)
            dev.off()
            cat(sprintf("   Saved: %s\n", svg_path))
        }, error = function(e2) {
            cat("   (SVG export failed)\n")
        })
    })
}

# --- ComplexHeatmap save helper ---
.save_heatmap <- function(ht, base_name, output_dir, width = 10, height = 8) {
    png_path <- file.path(output_dir, paste0(base_name, ".png"))
    svg_path <- file.path(output_dir, paste0(base_name, ".svg"))

    # PNG
    png(png_path, width = width, height = height, units = "in", res = 300)
    draw(ht)
    dev.off()
    cat(sprintf("   Saved: %s\n", png_path))

    # SVG
    tryCatch({
        svg(svg_path, width = width, height = height)
        draw(ht)
        dev.off()
        cat(sprintf("   Saved: %s\n", svg_path))
    }, error = function(e) {
        cat("   (SVG export failed)\n")
    })
}

# =============================================================================
# Plot 1: Variance Explained Per Factor (THE signature MOFA plot)
# =============================================================================
.plot_variance_per_factor <- function(model, output_dir) {
    cat("\n1. Variance explained per factor per view...\n")

    r2 <- get_variance_explained(model)
    r2_mat <- r2$r2_per_factor[[1]]  # group 1

    # Convert to long format
    df <- melt(r2_mat)
    colnames(df) <- c("Factor", "View", "R2")
    df$Factor <- factor(df$Factor, levels = rev(rownames(r2_mat)))

    p <- ggplot(df, aes(x = View, y = Factor, fill = R2)) +
        geom_tile(color = "white", linewidth = 0.5) +
        geom_text(aes(label = sprintf("%.1f", R2)), size = 3) +
        scale_fill_gradient2(low = "white", mid = "#74ADD1", high = "#313695",
                             midpoint = max(df$R2) / 2,
                             name = "Variance\nexplained (%)") +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            axis.text.x = element_text(angle = 45, hjust = 1),
            axis.title = element_blank(),
            panel.grid = element_blank()
        ) +
        labs(title = "Variance Explained Per Factor Per View")

    .save_plot(p, "mofa_variance_per_factor", output_dir, width = 8, height = 7)
}

# =============================================================================
# Plot 2: Total Variance Explained Per View
# =============================================================================
.plot_total_variance <- function(model, output_dir) {
    cat("2. Total variance explained per view...\n")

    r2 <- get_variance_explained(model)
    r2_total <- r2$r2_total[[1]]

    df <- data.frame(
        View = names(r2_total),
        R2 = as.numeric(r2_total),
        stringsAsFactors = FALSE
    )
    df$View <- factor(df$View, levels = df$View[order(df$R2, decreasing = TRUE)])

    p <- ggplot(df, aes(x = View, y = R2, fill = View)) +
        geom_col(width = 0.7) +
        geom_text(aes(label = sprintf("%.1f%%", R2)), vjust = -0.5, size = 4) +
        scale_fill_brewer(palette = "Set2", guide = "none") +
        scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            axis.text.x = element_text(angle = 45, hjust = 1)
        ) +
        labs(title = "Total Variance Explained by MOFA Model",
             x = NULL, y = "Variance Explained (%)")

    .save_plot(p, "mofa_total_variance", output_dir, width = 7, height = 6)
}

# =============================================================================
# Plot 3: Factor Scatter (Factor 1 vs Factor 2)
# =============================================================================
.plot_factor_scatter <- function(model, output_dir) {
    cat("3. Factor scatter plot...\n")

    factors <- get_factors(model, as.data.frame = TRUE)
    # Pivot to wide format
    factors_wide <- reshape2::dcast(factors, sample ~ factor, value.var = "value")

    # Check if metadata has IGHV status
    meta <- tryCatch(samples_metadata(model), error = function(e) NULL)
    has_ighv <- !is.null(meta) && "IGHV" %in% colnames(meta)

    if (has_ighv) {
        factors_wide <- merge(factors_wide, meta[, c("sample", "IGHV"), drop = FALSE],
                              by = "sample", all.x = TRUE)
        factors_wide$IGHV <- factor(factors_wide$IGHV,
                                    levels = c("0", "1"),
                                    labels = c("Unmutated", "Mutated"))

        p <- ggplot(factors_wide, aes(x = Factor1, y = Factor2, color = IGHV)) +
            geom_point(size = 2.5, alpha = 0.8) +
            scale_color_manual(values = c("Unmutated" = "#E74C3C",
                                          "Mutated" = "#3498DB"),
                               na.value = "grey70",
                               name = "IGHV Status") +
            theme_prism(base_size = 12) +
            theme(
                plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
                legend.position = "right"
            ) +
            labs(title = "MOFA Factors Colored by IGHV Status",
                 x = "Factor 1", y = "Factor 2")
    } else {
        p <- ggplot(factors_wide, aes(x = Factor1, y = Factor2)) +
            geom_point(size = 2.5, alpha = 0.8, color = "#3498DB") +
            theme_prism(base_size = 12) +
            theme(
                plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
            ) +
            labs(title = "MOFA Factor 1 vs Factor 2",
                 x = "Factor 1", y = "Factor 2")
    }

    .save_plot(p, "mofa_factor_scatter", output_dir, width = 8, height = 6)
}

# =============================================================================
# Plot 4: Factor Correlation Matrix
# =============================================================================
.plot_factor_correlation <- function(model, output_dir) {
    cat("4. Factor correlation matrix...\n")

    factors <- get_factors(model)[[1]]  # matrix: samples x factors
    cor_mat <- cor(factors, use = "pairwise.complete.obs")

    df <- melt(cor_mat)
    colnames(df) <- c("Factor1", "Factor2", "Correlation")

    p <- ggplot(df, aes(x = Factor1, y = Factor2, fill = Correlation)) +
        geom_tile(color = "white", linewidth = 0.3) +
        geom_text(aes(label = sprintf("%.2f", Correlation)), size = 2.5) +
        scale_fill_gradient2(low = "#D73027", mid = "white", high = "#4575B4",
                             midpoint = 0, limits = c(-1, 1),
                             name = "Pearson r") +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            axis.text.x = element_text(angle = 45, hjust = 1),
            axis.title = element_blank(),
            panel.grid = element_blank()
        ) +
        labs(title = "Factor-Factor Correlation Matrix")

    .save_plot(p, "mofa_factor_correlation", output_dir, width = 8, height = 7)
}

# =============================================================================
# Plot 5: Top Feature Weights Per Factor
# =============================================================================
.plot_top_weights <- function(model, output_dir, n_top = 10) {
    cat("5. Top feature weights per factor...\n")

    weights <- get_weights(model, as.data.frame = TRUE)

    # Get active factors (top 4 by total variance)
    r2 <- get_variance_explained(model)
    r2_mat <- r2$r2_per_factor[[1]]
    factor_importance <- apply(r2_mat, 1, sum)
    top_factors <- names(sort(factor_importance, decreasing = TRUE))[1:min(4, length(factor_importance))]

    # Filter to top factors
    weights_sub <- weights[weights$factor %in% top_factors, ]

    # For each factor x view, get top N by absolute weight
    top_list <- list()
    for (f in top_factors) {
        for (v in unique(weights_sub$view)) {
            sub <- weights_sub[weights_sub$factor == f & weights_sub$view == v, ]
            sub <- sub[order(abs(sub$value), decreasing = TRUE), ]
            if (nrow(sub) > 0) {
                top_list[[paste(f, v)]] <- head(sub, n_top)
            }
        }
    }
    top_df <- do.call(rbind, top_list)

    if (nrow(top_df) == 0) {
        cat("   (No weights to plot)\n")
        return(invisible(NULL))
    }

    # Create short feature labels
    top_df$feature_short <- substr(top_df$feature, 1, 20)
    top_df$direction <- ifelse(top_df$value > 0, "Positive", "Negative")

    p <- ggplot(top_df, aes(x = reorder(feature_short, abs(value)),
                            y = value, fill = direction)) +
        geom_col() +
        coord_flip() +
        facet_wrap(~ factor + view, scales = "free", ncol = 2) +
        scale_fill_manual(values = c("Positive" = "#E74C3C", "Negative" = "#3498DB"),
                          name = "Direction") +
        theme_prism(base_size = 10) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            strip.text = element_text(size = 9),
            axis.text.y = element_text(size = 7)
        ) +
        labs(title = "Top Feature Weights Per Factor",
             x = NULL, y = "Weight")

    n_panels <- length(unique(paste(top_df$factor, top_df$view)))
    plot_height <- max(8, ceiling(n_panels / 2) * 4)
    .save_plot(p, "mofa_top_weights", output_dir, width = 12, height = plot_height)
}

# =============================================================================
# Plot 6: Factor Heatmap (ComplexHeatmap)
# =============================================================================
.plot_factor_heatmap <- function(model, output_dir) {
    cat("6. Factor heatmap (samples x factors)...\n")

    factors <- get_factors(model)[[1]]  # samples x factors

    # Scale factors for visualization
    factors_scaled <- scale(factors)

    # Color function
    col_fun <- colorRamp2(c(-3, 0, 3), c("#4575B4", "white", "#D73027"))

    # Build annotation if metadata available
    meta <- tryCatch(samples_metadata(model), error = function(e) NULL)
    ha <- NULL
    if (!is.null(meta) && nrow(meta) > 0) {
        ann_cols <- list()
        if ("IGHV" %in% colnames(meta)) {
            ann_cols[["IGHV"]] <- c("0" = "#E74C3C", "1" = "#3498DB")
        }
        if ("Gender" %in% colnames(meta)) {
            ann_cols[["Gender"]] <- c("m" = "#66C2A5", "f" = "#FC8D62")
        }

        # Align metadata rows to factor matrix rows
        common <- intersect(rownames(factors_scaled), meta$sample)
        if (length(common) > 0) {
            meta_aligned <- meta[match(common, meta$sample), , drop = FALSE]
            factors_scaled <- factors_scaled[common, , drop = FALSE]

            ann_df <- data.frame(row.names = common)
            if ("IGHV" %in% colnames(meta_aligned)) {
                ann_df$IGHV <- as.character(meta_aligned$IGHV)
            }
            if ("Gender" %in% colnames(meta_aligned)) {
                ann_df$Gender <- as.character(meta_aligned$Gender)
            }

            if (ncol(ann_df) > 0) {
                ha <- HeatmapAnnotation(df = ann_df, col = ann_cols,
                                        show_annotation_name = TRUE)
            }
        }
    }

    ht <- Heatmap(
        t(factors_scaled),
        name = "Z-score",
        col = col_fun,
        top_annotation = ha,
        cluster_rows = FALSE,
        cluster_columns = TRUE,
        show_column_names = FALSE,
        row_names_gp = gpar(fontsize = 10),
        column_title = "MOFA Factor Values Across Samples",
        column_title_gp = gpar(fontsize = 14, fontface = "bold"),
        heatmap_legend_param = list(title = "Factor\nZ-score")
    )

    .save_heatmap(ht, "mofa_factor_heatmap", output_dir, width = 12, height = 6)
}

# =============================================================================
# Plot 7: Factor-Clinical Variable Association
# =============================================================================
.plot_factor_clinical <- function(model, output_dir) {
    cat("7. Factor-clinical variable associations...\n")

    meta <- tryCatch(samples_metadata(model), error = function(e) NULL)
    if (is.null(meta) || nrow(meta) == 0) {
        cat("   (Skipped: no sample metadata available)\n")
        return(invisible(NULL))
    }

    factors <- get_factors(model, as.data.frame = TRUE)
    factors_wide <- reshape2::dcast(factors, sample ~ factor, value.var = "value")

    # Merge with metadata
    merged <- merge(factors_wide, meta, by = "sample", all.x = TRUE)

    # Find clinical variables to plot (categorical with 2-5 levels)
    clinical_vars <- c()
    for (col in colnames(meta)) {
        if (col %in% c("sample", "group")) next
        vals <- meta[[col]][!is.na(meta[[col]])]
        n_unique <- length(unique(vals))
        if (n_unique >= 2 && n_unique <= 5) {
            clinical_vars <- c(clinical_vars, col)
        }
    }

    if (length(clinical_vars) == 0) {
        cat("   (Skipped: no suitable categorical clinical variables)\n")
        return(invisible(NULL))
    }

    # Prefer IGHV if available (most biologically relevant for CLL)
    preferred <- c("IGHV", "trisomy12")
    pref_match <- intersect(preferred, clinical_vars)
    if (length(pref_match) > 0) {
        clinical_vars <- c(pref_match, setdiff(clinical_vars, pref_match))
    }

    # Plot top 3 factors against first clinical variable
    clin_var <- clinical_vars[1]
    # Get top 3 factors by variance
    r2 <- get_variance_explained(model)
    r2_mat <- r2$r2_per_factor[[1]]
    factor_importance <- apply(r2_mat, 1, sum)
    top_factors <- names(sort(factor_importance, decreasing = TRUE))[1:min(3, length(factor_importance))]

    # Build long-format data for top factors
    plot_data <- list()
    for (f in top_factors) {
        if (f %in% colnames(merged)) {
            tmp <- data.frame(
                sample = merged$sample,
                Factor = f,
                Value = merged[[f]],
                Clinical = as.factor(merged[[clin_var]]),
                stringsAsFactors = FALSE
            )
            plot_data[[f]] <- tmp
        }
    }
    plot_df <- do.call(rbind, plot_data)
    plot_df <- plot_df[!is.na(plot_df$Clinical), ]

    if (nrow(plot_df) == 0) {
        cat("   (Skipped: no data after filtering)\n")
        return(invisible(NULL))
    }

    p <- ggplot(plot_df, aes(x = Clinical, y = Value, fill = Clinical)) +
        geom_boxplot(alpha = 0.7, outlier.shape = NA) +
        geom_jitter(width = 0.2, size = 1, alpha = 0.5) +
        facet_wrap(~ Factor, scales = "free_y", ncol = 3) +
        scale_fill_brewer(palette = "Set2", guide = "none") +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            strip.text = element_text(size = 11)
        ) +
        labs(title = sprintf("Factor Values by %s", clin_var),
             x = clin_var, y = "Factor Value")

    .save_plot(p, "mofa_factor_clinical", output_dir, width = 12, height = 5)
}

# =============================================================================
# Main entry point
# =============================================================================

#' Generate all MOFA visualizations
#'
#' @param model Trained MOFA model object
#' @param output_dir Directory for plot files
generate_all_plots <- function(model, output_dir = "mofa_results") {
    cat("\n=== Generating MOFA Visualizations ===\n")

    .load_plot_packages()

    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
    }

    .plot_variance_per_factor(model, output_dir)
    .plot_total_variance(model, output_dir)
    .plot_factor_scatter(model, output_dir)
    .plot_factor_correlation(model, output_dir)
    .plot_top_weights(model, output_dir)
    .plot_factor_heatmap(model, output_dir)
    .plot_factor_clinical(model, output_dir)

    # Count generated files
    pngs <- list.files(output_dir, pattern = "mofa_.*\\.png$")
    svgs <- list.files(output_dir, pattern = "mofa_.*\\.svg$")
    cat(sprintf("\n  Generated: %d PNG files, %d SVG files\n", length(pngs), length(svgs)))

    cat("\n✓ All plots generated successfully!\n\n")
}

