# QC and results visualization for proteomics DE analysis
# All ggplot-based plots use theme_prism(base_size = 12)
# Heatmaps use ComplexHeatmap::Heatmap()

library(ggplot2)
library(ggprism)
library(ggrepel)
library(ComplexHeatmap)
library(circlize)

# ---- Save plot helper ----

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
    library(svglite)
}

.save_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
    # Always save PNG
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")

    # Always try SVG - try ggsave first, fall back to svg() device
    svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
    tryCatch({
        ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
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

# Save ComplexHeatmap with PNG + SVG
.save_heatmap <- function(ht, base_path, width = 10, height = 8, dpi = 300) {
    # Always save PNG
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    png(png_path, width = width, height = height, units = "in", res = dpi)
    draw(ht)
    dev.off()
    cat("   Saved:", png_path, "\n")

    # Always try SVG
    svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
    tryCatch({
        svg(svg_path, width = width, height = height)
        draw(ht)
        dev.off()
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        cat("   (SVG export failed for heatmap)\n")
    })
}


# ---- Individual plot functions ----

#' Intensity distribution boxplot (before and after normalization)
plot_intensity_distribution <- function(raw_matrix, norm_matrix, metadata,
                                         output_dir = "results",
                                         width = 10, height = 6) {
    cat("\n   Plotting intensity distribution...\n")

    # Reshape for ggplot
    df_raw <- data.frame(
        sample = rep(colnames(raw_matrix), each = nrow(raw_matrix)),
        intensity = as.vector(raw_matrix),
        stage = "Before normalization"
    )
    df_norm <- data.frame(
        sample = rep(colnames(norm_matrix), each = nrow(norm_matrix)),
        intensity = as.vector(norm_matrix),
        stage = "After normalization"
    )
    df <- rbind(df_raw, df_norm)
    df$stage <- factor(df$stage, levels = c("Before normalization", "After normalization"))

    # Add condition info
    df$condition <- metadata[df$sample, "condition"]

    p <- ggplot(df, aes(x = sample, y = intensity, fill = condition)) +
        geom_boxplot(outlier.size = 0.5, alpha = 0.7) +
        facet_wrap(~stage, scales = "free_y") +
        theme_prism(base_size = 12) +
        theme(
            axis.text.x = element_text(angle = 45, hjust = 1, size = 8),
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            strip.text = element_text(face = "bold", size = 12)
        ) +
        labs(
            title = "Protein Intensity Distribution",
            x = "Sample",
            y = "Log2 Intensity",
            fill = "Condition"
        )

    .save_plot(p, file.path(output_dir, "intensity_distribution.png"),
               width = width, height = height)
}


#' Missing value heatmap (ComplexHeatmap)
plot_missing_values <- function(intensity_matrix, metadata,
                                 output_dir = "results",
                                 width = 10, height = 8) {
    cat("\n   Plotting missing value heatmap...\n")

    # Create binary missing matrix (1 = present, 0 = missing)
    missing_mat <- ifelse(is.na(intensity_matrix), 0, 1)

    # Filter to proteins with at least some missingness (more informative)
    has_missing <- rowSums(missing_mat == 0) > 0
    if (sum(has_missing) == 0) {
        cat("   No missing values found - skipping missing value heatmap\n")
        return(invisible(NULL))
    }

    # Limit to top 200 proteins with most missingness for readability
    n_missing_per_protein <- rowSums(missing_mat == 0)
    top_missing <- head(order(n_missing_per_protein, decreasing = TRUE),
                        min(200, sum(has_missing)))
    plot_mat <- missing_mat[top_missing, , drop = FALSE]

    # Annotation
    col_anno <- HeatmapAnnotation(
        Condition = metadata[colnames(plot_mat), "condition"],
        col = list(Condition = setNames(
            c("#E41A1C", "#377EB8", "#4DAF4A", "#984EA3")[seq_along(levels(metadata$condition))],
            levels(metadata$condition)
        )),
        annotation_name_side = "left"
    )

    col_fun <- colorRamp2(c(0, 1), c("#2C3E50", "#ECF0F1"))

    ht <- Heatmap(
        plot_mat,
        name = "Present",
        col = col_fun,
        top_annotation = col_anno,
        show_row_names = FALSE,
        column_title = "Missing Value Pattern",
        column_title_gp = gpar(fontsize = 14, fontface = "bold"),
        cluster_rows = TRUE,
        cluster_columns = TRUE,
        heatmap_legend_param = list(
            labels = c("Missing", "Present"),
            at = c(0, 1)
        )
    )

    .save_heatmap(ht, file.path(output_dir, "missing_values_heatmap.png"),
                  width = width, height = height)
}


#' PCA plot colored by condition
plot_pca <- function(protein_matrix, metadata,
                      output_dir = "results",
                      label_samples = TRUE,
                      width = 8, height = 6) {
    cat("\n   Plotting PCA...\n")

    # Use complete cases only
    complete_rows <- complete.cases(protein_matrix)
    mat <- protein_matrix[complete_rows, ]

    # Run PCA on transposed matrix (samples as observations)
    pca <- prcomp(t(mat), center = TRUE, scale. = TRUE)
    pca_df <- data.frame(
        PC1 = pca$x[, 1],
        PC2 = pca$x[, 2],
        sample = rownames(pca$x),
        condition = metadata[rownames(pca$x), "condition"]
    )

    var_explained <- summary(pca)$importance[2, 1:2] * 100

    p <- ggplot(pca_df, aes(x = PC1, y = PC2, color = condition)) +
        geom_point(size = 4, alpha = 0.8) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
        ) +
        labs(
            title = "PCA of Protein Abundances",
            x = sprintf("PC1 (%.1f%% variance)", var_explained[1]),
            y = sprintf("PC2 (%.1f%% variance)", var_explained[2]),
            color = "Condition"
        )

    if (label_samples) {
        p <- p + geom_text_repel(aes(label = sample), size = 3,
                                  max.overlaps = 20)
    }

    .save_plot(p, file.path(output_dir, "pca_plot.png"),
               width = width, height = height)
}


#' Sample correlation heatmap (ComplexHeatmap)
plot_sample_correlation <- function(protein_matrix, metadata,
                                      output_dir = "results",
                                      width = 8, height = 7) {
    cat("\n   Plotting sample correlation heatmap...\n")

    # Compute correlation on complete cases
    complete_rows <- complete.cases(protein_matrix)
    cor_mat <- cor(protein_matrix[complete_rows, ], use = "pairwise.complete.obs")

    # Annotation
    col_anno <- HeatmapAnnotation(
        Condition = metadata[colnames(cor_mat), "condition"],
        col = list(Condition = setNames(
            c("#E41A1C", "#377EB8", "#4DAF4A", "#984EA3")[seq_along(levels(metadata$condition))],
            levels(metadata$condition)
        )),
        annotation_name_side = "left"
    )

    col_fun <- colorRamp2(
        c(min(cor_mat, na.rm = TRUE), mean(c(min(cor_mat, na.rm = TRUE), 1)), 1),
        c("#2166AC", "#F7F7F7", "#B2182B")
    )

    ht <- Heatmap(
        cor_mat,
        name = "Correlation",
        col = col_fun,
        top_annotation = col_anno,
        column_title = "Sample Correlation (Pearson)",
        column_title_gp = gpar(fontsize = 14, fontface = "bold"),
        show_row_names = TRUE,
        show_column_names = TRUE,
        row_names_gp = gpar(fontsize = 8),
        column_names_gp = gpar(fontsize = 8),
        cell_fun = function(j, i, x, y, width, height, fill) {
            grid.text(sprintf("%.2f", cor_mat[i, j]), x, y,
                      gp = gpar(fontsize = 7))
        }
    )

    .save_heatmap(ht, file.path(output_dir, "sample_correlation_heatmap.png"),
                  width = width, height = height)
}


#' Volcano plot with labeled top hits
plot_volcano <- function(deqms_results, output_dir = "results",
                          alpha = 0.05, lfc_threshold = 0.58,
                          label_top = 10,
                          width = 8, height = 6) {
    cat("\n   Plotting volcano plot...\n")

    df <- deqms_results
    df$neg_log10_pval <- -log10(df$sca.adj.pval)

    # Classify significance
    df$significance <- "Not significant"
    df$significance[df$sca.adj.pval < alpha & df$logFC > lfc_threshold] <- "Up"
    df$significance[df$sca.adj.pval < alpha & df$logFC < -lfc_threshold] <- "Down"
    df$significance <- factor(df$significance,
                               levels = c("Up", "Down", "Not significant"))

    # Top hits to label
    sig_df <- df[df$significance != "Not significant", ]
    top_hits <- head(sig_df[order(sig_df$sca.adj.pval), ], label_top)

    p <- ggplot(df, aes(x = logFC, y = neg_log10_pval, color = significance)) +
        geom_point(alpha = 0.5, size = 1.5) +
        scale_color_manual(
            values = c("Up" = "#E41A1C", "Down" = "#377EB8",
                        "Not significant" = "#999999")
        ) +
        geom_hline(yintercept = -log10(alpha), linetype = "dashed", color = "grey40") +
        geom_vline(xintercept = c(-lfc_threshold, lfc_threshold),
                    linetype = "dashed", color = "grey40") +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
        ) +
        labs(
            title = "Volcano Plot (DEqMS)",
            x = "Log2 Fold Change",
            y = "-Log10 Adjusted P-value (DEqMS)",
            color = "Significance"
        )

    if (nrow(top_hits) > 0) {
        p <- p + geom_text_repel(
            data = top_hits,
            aes(label = protein),
            size = 3,
            max.overlaps = 20,
            color = "black",
            fontface = "italic"
        )
    }

    .save_plot(p, file.path(output_dir, "volcano_plot.png"),
               width = width, height = height)
}


#' MA plot (log2FC vs mean intensity)
plot_ma <- function(deqms_results, output_dir = "results",
                     alpha = 0.05, label_top = 10,
                     width = 8, height = 6) {
    cat("\n   Plotting MA plot...\n")

    df <- deqms_results
    df$significant <- df$sca.adj.pval < alpha

    top_hits <- head(df[df$significant & !is.na(df$significant), ], label_top)

    p <- ggplot(df, aes(x = AveExpr, y = logFC, color = significant)) +
        geom_point(alpha = 0.5, size = 1.5) +
        scale_color_manual(
            values = c("TRUE" = "#E41A1C", "FALSE" = "#999999"),
            labels = c("TRUE" = "Significant", "FALSE" = "Not significant")
        ) +
        geom_hline(yintercept = 0, linetype = "solid", color = "grey40") +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
        ) +
        labs(
            title = "MA Plot (DEqMS)",
            x = "Average Log2 Expression",
            y = "Log2 Fold Change",
            color = ""
        )

    if (nrow(top_hits) > 0) {
        p <- p + geom_text_repel(
            data = top_hits,
            aes(label = protein),
            size = 3,
            max.overlaps = 20,
            color = "black",
            fontface = "italic"
        )
    }

    .save_plot(p, file.path(output_dir, "ma_plot.png"),
               width = width, height = height)
}


#' DEqMS variance vs PSM count plot
plot_variance_psm <- function(fit_deqms, output_dir = "results",
                                width = 8, height = 6) {
    cat("\n   Plotting variance vs PSM count...\n")

    df <- data.frame(
        psm_count = fit_deqms$count,
        log_variance = log2(fit_deqms$sigma^2)
    )
    df <- df[!is.na(df$psm_count) & !is.na(df$log_variance), ]

    # Bin PSM counts (cap at 20 for readability)
    df$psm_bin <- factor(pmin(df$psm_count, 20),
                          levels = sort(unique(pmin(df$psm_count, 20))))

    # Relabel last bin
    levels(df$psm_bin)[levels(df$psm_bin) == "20"] <- "20+"

    p <- ggplot(df, aes(x = psm_bin, y = log_variance)) +
        geom_boxplot(fill = "#377EB8", alpha = 0.6, outlier.size = 0.5) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            axis.text.x = element_text(size = 8)
        ) +
        labs(
            title = "Protein Variance vs PSM Count (DEqMS)",
            x = "PSM Count",
            y = "Log2 Variance"
        )

    .save_plot(p, file.path(output_dir, "variance_psm_plot.png"),
               width = width, height = height)
}


# ---- Main function ----

#' Generate all QC and results plots
#'
#' @param fit_deqms DEqMS fit object from basic_workflow.R
#' @param deqms_results DEqMS results data.frame from basic_workflow.R
#' @param protein_matrix Normalized protein matrix from basic_workflow.R
#' @param metadata Sample metadata data.frame
#' @param output_dir Output directory (default: "results")
#' @param raw_matrix Optional pre-normalization matrix for intensity distribution
#' @export
generate_all_plots <- function(fit_deqms, deqms_results, protein_matrix,
                                metadata, output_dir = "results",
                                raw_matrix = NULL) {

    cat("\n=== Generating Proteomics QC and Results Plots ===\n")

    # Create output directory
    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
    }

    # 1. Intensity distribution (requires raw_matrix)
    if (!is.null(raw_matrix)) {
        plot_intensity_distribution(raw_matrix, protein_matrix, metadata,
                                    output_dir = output_dir)
    } else {
        cat("\n   Skipping intensity distribution (no raw_matrix provided)\n")
    }

    # 2. Missing value heatmap (use raw_matrix if available)
    plot_mat <- if (!is.null(raw_matrix)) raw_matrix else protein_matrix
    plot_missing_values(plot_mat, metadata, output_dir = output_dir)

    # 3. PCA
    plot_pca(protein_matrix, metadata, output_dir = output_dir)

    # 4. Sample correlation
    plot_sample_correlation(protein_matrix, metadata, output_dir = output_dir)

    # 5. Volcano
    plot_volcano(deqms_results, output_dir = output_dir)

    # 6. MA plot
    plot_ma(deqms_results, output_dir = output_dir)

    # 7. Variance vs PSM count
    plot_variance_psm(fit_deqms, output_dir = output_dir)

    cat("\n✓ All plots generated successfully!\n\n")
}

