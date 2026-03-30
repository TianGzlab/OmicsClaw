# Quality control plots for DESeq2 analysis
# Run after DESeq() to assess data quality
#
# Uses ggplot2, ggprism, and ggrepel for publication-quality visualizations

library(DESeq2)
library(ggplot2)
library(ggprism)
library(ggrepel)

# Try to load svglite for high-quality SVG export (falls back to base R svg() if unavailable)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
    library(svglite)
}

#' Save plot to PNG and SVG (always generates both)
#'
#' @param plot ggplot object
#' @param base_path Base file path without extension
#' @param width Width in inches
#' @param height Height in inches
#' @param dpi Resolution for PNG
#'
#' @keywords internal
.save_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
    # Always save PNG
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")

    # Always try to save SVG - try ggsave first, fall back to svg() device
    svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
    tryCatch({
        ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        # If ggsave fails, try base R svg() device directly
        tryCatch({
            svg(svg_path, width = width, height = height)
            print(plot)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e2) {
            cat("   (SVG export failed:", condenseMessage(e2$message), ")\n")
        })
    })
}

# Helper to condense error messages
condenseMessage <- function(msg) {
    msg <- gsub("\n", " ", msg)
    if (nchar(msg) > 100) substring(msg, 1, 100) else msg
}

#' Generate dispersion estimates plot with ggplot2
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param output_file Output file path (SVG or PNG)
#'
#' @export
plot_dispersions <- function(dds, output_file = "dispersion_plot.svg") {
    # Extract dispersion data
    df <- data.frame(
        baseMean = rowMeans(counts(dds, normalized = TRUE)),
        dispGeneEst = mcols(dds)$dispGeneEst,
        dispFit = mcols(dds)$dispFit,
        dispersion = dispersions(dds),
        dispOutlier = mcols(dds)$dispOutlier
    )

    # Remove NA values
    df <- df[!is.na(df$dispGeneEst), ]

    # Create plot with ggplot2 and ggprism theme
    p <- ggplot(df, aes(x = baseMean)) +
        geom_point(aes(y = dispGeneEst), size = 0.5, alpha = 0.3, color = "black") +
        geom_point(data = df[!is.na(df$dispOutlier) & df$dispOutlier, ],
                   aes(y = dispGeneEst), size = 0.8, color = "cyan4") +
        geom_line(aes(y = dispFit), color = "red", linewidth = 1) +
        geom_point(aes(y = dispersion), size = 0.3, alpha = 0.5, color = "dodgerblue") +
        scale_x_log10() +
        scale_y_log10() +
        labs(
            title = "Dispersion Estimates",
            x = "Mean of normalized counts",
            y = "Dispersion"
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(face = "bold", hjust = 0.5),
            axis.title = element_text(face = "bold")
        )

    # Save plot
    .save_plot(p, output_file, width = 8, height = 6, dpi = 300)
    cat("✓ Check: Points should cluster around fitted red trend line\n")
    cat("  Black = gene-wise estimates, Blue = final estimates, Cyan = outliers\n")
}

#' Generate PCA plot with ggplot2, ggprism, and ggrepel
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param intgroup Column name(s) in colData to color by (e.g., 'condition')
#' @param output_file Output file path (SVG or PNG)
#' @param use_vst Use VST transformation (TRUE) or rlog (FALSE)
#' @param label_samples Show sample names (TRUE) or not (FALSE)
#'
#' @export
plot_pca <- function(dds, intgroup = "condition",
                     output_file = "pca_plot.svg",
                     use_vst = TRUE,
                     label_samples = TRUE) {

    # Transform data
    if (use_vst) {
        transformed <- vst(dds, blind = FALSE)
        cat("Using VST transformation\n")
    } else {
        transformed <- rlog(dds, blind = FALSE)
        cat("Using rlog transformation\n")
    }

    # Compute PCA
    pca_data <- plotPCA(transformed, intgroup = intgroup, returnData = TRUE)
    percent_var <- round(100 * attr(pca_data, "percentVar"))

    # Create ggplot with ggprism theme
    p <- ggplot(pca_data, aes(x = PC1, y = PC2, color = group, label = name)) +
        geom_point(size = 4, alpha = 0.8) +
        scale_color_prism(palette = "colors") +
        labs(
            title = "PCA - Sample Clustering",
            x = paste0("PC1: ", percent_var[1], "% variance"),
            y = paste0("PC2: ", percent_var[2], "% variance"),
            color = intgroup
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(face = "bold", hjust = 0.5),
            axis.title = element_text(face = "bold"),
            legend.title = element_text(face = "bold")
        )

    # Add sample labels using ggrepel to avoid overlaps
    if (label_samples) {
        p <- p + geom_text_repel(
            size = 3,
            max.overlaps = 20,
            box.padding = 0.5,
            point.padding = 0.3,
            show.legend = FALSE
        )
    }

    # Save plot
    .save_plot(p, output_file, width = 8, height = 6, dpi = 300)
    cat("✓ Check: Samples should cluster by", intgroup, "\n")
}

#' Generate MA plot with ggplot2, ggprism, and ggrepel
#'
#' @param res DESeqResults object
#' @param output_file Output file path (SVG or PNG)
#' @param ylim Y-axis limits (default: c(-5, 5))
#' @param alpha Significance threshold for coloring (default: 0.05)
#' @param label_top Number of top genes to label (default: 10)
#'
#' @export
plot_ma <- function(res, output_file = "ma_plot.svg", ylim = c(-5, 5),
                    alpha = 0.05, label_top = 10) {

    # Prepare data
    df <- as.data.frame(res)
    df$gene <- rownames(df)
    df$significant <- ifelse(is.na(df$padj), FALSE, df$padj < alpha)

    # Clip fold changes to ylim for visualization
    df$log2FoldChange_clipped <- pmax(pmin(df$log2FoldChange, ylim[2]), ylim[1])

    # Identify top genes to label
    df_sig <- df[df$significant & !is.na(df$padj), ]
    if (nrow(df_sig) > 0) {
        df_sig <- df_sig[order(df_sig$padj), ]
        top_genes <- head(df_sig, label_top)$gene
        df$label <- ifelse(df$gene %in% top_genes, df$gene, "")
    } else {
        df$label <- ""
    }

    # Create MA plot
    p <- ggplot(df, aes(x = baseMean, y = log2FoldChange_clipped)) +
        geom_point(
            aes(color = significant),
            size = 0.5,
            alpha = 0.5
        ) +
        geom_hline(yintercept = 0, linetype = "dashed", color = "gray40") +
        scale_x_log10() +
        scale_color_manual(
            values = c("FALSE" = "gray60", "TRUE" = "dodgerblue"),
            labels = c("FALSE" = "Not significant", "TRUE" = paste0("padj < ", alpha)),
            name = "Significance"
        ) +
        labs(
            title = "MA Plot",
            x = "Mean of normalized counts",
            y = "Log2 fold change"
        ) +
        coord_cartesian(ylim = ylim) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(face = "bold", hjust = 0.5),
            axis.title = element_text(face = "bold"),
            legend.title = element_text(face = "bold")
        )

    # Add gene labels using ggrepel
    if (any(df$label != "")) {
        p <- p + geom_text_repel(
            aes(label = label),
            size = 2.5,
            max.overlaps = 20,
            box.padding = 0.5,
            point.padding = 0.3,
            segment.size = 0.2,
            show.legend = FALSE
        )
    }

    # Save plot
    .save_plot(p, output_file, width = 8, height = 6, dpi = 300)
    cat("✓ Check: Plot should be symmetric around zero\n")
    cat("  Blue = significant genes (padj <", alpha, "), Gray = not significant\n")
}

#' Generate volcano plot with ggplot2, ggprism, and ggrepel
#'
#' Shows -log10(padj) vs log2FoldChange for differential expression visualization.
#'
#' @param res DESeqResults object
#' @param output_file Output file path (SVG or PNG)
#' @param xlim X-axis limits (default: c(-6, 6))
#' @param alpha Significance threshold (default: 0.05)
#' @param lfc_threshold Log2 fold change threshold (default: 1)
#' @param label_top Number of top genes to label (default: 10)
#'
#' @export
plot_volcano <- function(res, output_file = "volcano_plot.svg",
                        xlim = c(-6, 6),
                        alpha = 0.05,
                        lfc_threshold = 1,
                        label_top = 10) {

    # Prepare data
    df <- as.data.frame(res)
    df$gene <- rownames(df)

    # Calculate -log10(padj)
    df$neg_log10_padj <- -log10(df$padj)

    # Define significance categories
    df$category <- "Not significant"
    df$category[!is.na(df$padj) & df$padj < alpha & df$log2FoldChange > lfc_threshold] <- "Up"
    df$category[!is.na(df$padj) & df$padj < alpha & df$log2FoldChange < -lfc_threshold] <- "Down"
    df$category <- factor(df$category, levels = c("Up", "Down", "Not significant"))

    # Clip fold changes to xlim for visualization
    df$log2FoldChange_clipped <- pmax(pmin(df$log2FoldChange, xlim[2]), xlim[1])

    # Identify top genes to label (most significant in each direction)
    df_sig <- df[df$category != "Not significant" & !is.na(df$padj), ]
    if (nrow(df_sig) > 0) {
        df_sig <- df_sig[order(df_sig$padj), ]
        top_genes <- head(df_sig, label_top)$gene
        df$label <- ifelse(df$gene %in% top_genes, df$gene, "")
    } else {
        df$label <- ""
    }

    # Remove rows with NA padj for plotting
    df_plot <- df[!is.na(df$neg_log10_padj), ]

    # Create volcano plot
    p <- ggplot(df_plot, aes(x = log2FoldChange_clipped, y = neg_log10_padj)) +
        geom_point(
            aes(color = category),
            size = 0.5,
            alpha = 0.5
        ) +
        geom_vline(xintercept = c(-lfc_threshold, lfc_threshold),
                   linetype = "dashed", color = "gray40", linewidth = 0.5) +
        geom_hline(yintercept = -log10(alpha),
                   linetype = "dashed", color = "gray40", linewidth = 0.5) +
        scale_color_manual(
            values = c(
                "Up" = "red3",
                "Down" = "dodgerblue",
                "Not significant" = "gray60"
            ),
            name = "Differential Expression"
        ) +
        labs(
            title = "Volcano Plot",
            x = "Log2 fold change",
            y = expression(-log[10](adjusted~p-value))
        ) +
        coord_cartesian(xlim = xlim) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(face = "bold", hjust = 0.5),
            axis.title = element_text(face = "bold"),
            legend.title = element_text(face = "bold")
        )

    # Add gene labels using ggrepel
    if (any(df_plot$label != "")) {
        p <- p + geom_text_repel(
            data = df_plot[df_plot$label != "", ],
            aes(label = label),
            size = 2.5,
            max.overlaps = 20,
            box.padding = 0.5,
            point.padding = 0.3,
            segment.size = 0.2,
            show.legend = FALSE
        )
    }

    # Save plot
    .save_plot(p, output_file, width = 8, height = 6, dpi = 300)

    # Summary statistics
    n_up <- sum(df$category == "Up", na.rm = TRUE)
    n_down <- sum(df$category == "Down", na.rm = TRUE)
    cat("✓ Check: Plot should be symmetric around x = 0\n")
    cat("  Upregulated:", n_up, "genes (red)\n")
    cat("  Downregulated:", n_down, "genes (blue)\n")
    cat("  Thresholds: padj <", alpha, ", |log2FC| >", lfc_threshold, "\n")
}

#' Run all QC checks
#'
#' @param dds DESeqDataSet object (after DESeq())
#' @param res DESeqResults object (optional)
#' @param output_dir Directory for output plots
#'
#' @export
run_all_qc <- function(dds, res = NULL, output_dir = ".") {
    cat("\n=== Running DESeq2 Quality Control ===\n\n")

    # Create output directory if needed
    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
    }

    # Check data structure
    cat("1. Checking data structure...\n")
    cat("   Genes:", nrow(dds), "\n")
    cat("   Samples:", ncol(dds), "\n")
    cat("   Design:", as.character(design(dds)), "\n")
    cat("   Reference level:", levels(dds$condition)[1], "\n\n")

    # Generate plots
    cat("2. Generating dispersion plot...\n")
    plot_dispersions(dds, file.path(output_dir, "dispersion_plot.svg"))
    cat("\n")

    cat("3. Generating PCA plot...\n")
    # Use vst for large datasets, rlog for small
    use_vst <- ncol(dds) > 30
    plot_pca(dds, output_file = file.path(output_dir, "pca_plot.svg"),
             use_vst = use_vst)
    cat("\n")

    if (!is.null(res)) {
        cat("4. Generating MA plot...\n")
        plot_ma(res, output_file = file.path(output_dir, "ma_plot.svg"))
        cat("\n")

        cat("5. Generating volcano plot...\n")
        plot_volcano(res, output_file = file.path(output_dir, "volcano_plot.svg"))
        cat("\n")

        cat("6. Results summary:\n")
        print(summary(res))
    }

    cat("\n✓ All QC plots generated successfully!\n")
}

# Example usage:
# library(DESeq2)
# library(ggplot2)
# library(ggprism)
# library(ggrepel)
# source("scripts/qc_plots.R")
#
# # After running DESeq2
# dds <- DESeq(dds)
# res <- results(dds)
#
# # Generate all QC plots (uses ggplot2, ggprism, ggrepel)
# run_all_qc(dds, res, output_dir = "qc_plots")
#
# # Or generate individual plots with customization
# plot_dispersions(dds, "dispersion.svg")
# plot_pca(dds, intgroup = "condition", output_file = "pca.svg", label_samples = TRUE)
# plot_ma(res, "ma_plot.svg", ylim = c(-5, 5), alpha = 0.05, label_top = 10)
# plot_volcano(res, "volcano_plot.svg", xlim = c(-6, 6), alpha = 0.05, lfc_threshold = 1, label_top = 10)

