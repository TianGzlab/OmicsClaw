###############################################################################
# generate_plots.R — Multi-trait PRS visualizations using ggprism
#
# Per-trait plots:
#   plot_trait_distribution()      — Histogram for one trait
#   plot_trait_population()        — Boxplot by super-population for one trait
#
# Dashboard plots:
#   plot_correlation_heatmap()     — Trait-trait PRS correlation matrix
#   plot_composite_risk()          — Composite risk distribution by population
#   plot_population_heatmap()      — Mean PRS by trait x super-population
#
# Orchestrator:
#   generate_all_plots(all_results, output_dir)
###############################################################################

library(ggplot2)
library(ggprism)
library(dplyr)

# --- SVG support (optional, graceful fallback) --------------------------------

.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) library(svglite)

# --- Save helper (PNG + SVG always) -------------------------------------------

.save_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
    cat("   Saved:", png_path, "\n")

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
            cat("   (SVG export failed - PNG available)\n")
        })
    })
}

# Super-population color palette (consistent across all plots)
.pop_colors <- c(
    "AFR" = "#E74C3C", "AMR" = "#F39C12", "EAS" = "#2ECC71",
    "EUR" = "#3498DB", "SAS" = "#9B59B6"
)

# --- Per-trait: PRS Distribution ----------------------------------------------

plot_trait_distribution <- function(scores, trait_name, output_dir = "results") {
    p <- ggplot(scores, aes(x = prs_zscore)) +
        geom_histogram(aes(y = after_stat(density)),
                       bins = 30, fill = "#4A90D9", color = "white", alpha = 0.8) +
        geom_density(color = "#2C3E50", linewidth = 0.8) +
        geom_vline(xintercept = 0, linetype = "dashed", color = "#E67E22", linewidth = 0.8) +
        labs(
            title = paste(trait_name, "- PRS Distribution"),
            subtitle = paste(nrow(scores), "individuals from 1000 Genomes Phase 3"),
            x = "PRS (Z-score)",
            y = "Density"
        ) +
        theme_prism(base_size = 12) +
        theme(plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
              plot.subtitle = element_text(hjust = 0.5, size = 10, color = "gray40"))

    fname <- paste0("distribution_", gsub(" ", "_", tolower(trait_name)), ".png")
    .save_plot(p, file.path(output_dir, fname), width = 8, height = 6)
    return(invisible(p))
}

# --- Per-trait: Population Comparison -----------------------------------------

plot_trait_population <- function(scores, trait_name, output_dir = "results") {
    if (!"super_population" %in% names(scores) || all(is.na(scores$super_population))) {
        cat("   Skipped population plot (no labels)\n")
        return(invisible(NULL))
    }

    plot_df <- scores[!is.na(scores$super_population), ]
    pop_order <- plot_df %>%
        group_by(super_population) %>%
        summarise(mean_z = mean(prs_zscore), .groups = "drop") %>%
        arrange(mean_z) %>%
        pull(super_population)
    plot_df$super_population <- factor(plot_df$super_population, levels = pop_order)

    p <- ggplot(plot_df, aes(x = super_population, y = prs_zscore,
                              fill = super_population)) +
        geom_boxplot(outlier.shape = NA, alpha = 0.5, width = 0.6) +
        geom_jitter(aes(color = super_population), width = 0.2, size = 0.6, alpha = 0.2) +
        geom_hline(yintercept = 0, linetype = "dashed", color = "gray50") +
        scale_fill_manual(values = .pop_colors) +
        scale_color_manual(values = .pop_colors) +
        labs(
            title = paste(trait_name, "- PRS by Super-Population"),
            subtitle = "1000 Genomes Phase 3 (5 super-populations)",
            x = "Super-Population",
            y = "PRS (Z-score)"
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10, color = "gray40"),
            legend.position = "none"
        )

    fname <- paste0("population_", gsub(" ", "_", tolower(trait_name)), ".png")
    .save_plot(p, file.path(output_dir, fname), width = 8, height = 6)
    return(invisible(p))
}

# --- Dashboard: Correlation Heatmap -------------------------------------------

plot_correlation_heatmap <- function(cor_matrix, output_dir = "results") {
    cat("  [Dashboard] PRS correlation heatmap\n")

    # Melt correlation matrix for ggplot
    traits <- rownames(cor_matrix)
    cor_df <- expand.grid(Trait1 = traits, Trait2 = traits, stringsAsFactors = FALSE)
    cor_df$r <- as.vector(cor_matrix)
    cor_df$label <- sprintf("%.2f", cor_df$r)

    # Order traits
    cor_df$Trait1 <- factor(cor_df$Trait1, levels = traits)
    cor_df$Trait2 <- factor(cor_df$Trait2, levels = rev(traits))

    p <- ggplot(cor_df, aes(x = Trait1, y = Trait2, fill = r)) +
        geom_tile(color = "white", linewidth = 1) +
        geom_text(aes(label = label), size = 5, fontface = "bold") +
        scale_fill_gradient2(low = "#3498DB", mid = "white", high = "#E74C3C",
                             midpoint = 0, limits = c(-1, 1),
                             name = "Pearson r") +
        labs(
            title = "PRS Correlation Across Cardiometabolic Traits",
            subtitle = "Pearson correlation of PRS z-scores",
            x = "", y = ""
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10, color = "gray40"),
            axis.text.x = element_text(angle = 45, hjust = 1, size = 12),
            axis.text.y = element_text(size = 12),
            panel.grid = element_blank()
        )

    .save_plot(p, file.path(output_dir, "dashboard_correlation_matrix.png"), width = 8, height = 7)
    return(invisible(p))
}

# --- Dashboard: Composite Risk ------------------------------------------------

plot_composite_risk <- function(combined_scores, output_dir = "results") {
    cat("  [Dashboard] Composite risk distribution\n")

    if ("super_population" %in% names(combined_scores)) {
        plot_df <- combined_scores[!is.na(combined_scores$super_population), ]

        p <- ggplot(plot_df, aes(x = composite_risk, fill = super_population)) +
            geom_density(alpha = 0.4, linewidth = 0.6) +
            geom_vline(xintercept = 0, linetype = "dashed", color = "gray50") +
            scale_fill_manual(values = .pop_colors) +
            labs(
                title = "Composite Cardiometabolic Risk Score",
                subtitle = "Mean PRS z-score across all traits, by super-population",
                x = "Composite Risk (Mean Z-score)",
                y = "Density",
                fill = "Population"
            ) +
            theme_prism(base_size = 12) +
            theme(
                plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
                plot.subtitle = element_text(hjust = 0.5, size = 10, color = "gray40"),
                legend.position = "right"
            )
    } else {
        p <- ggplot(combined_scores, aes(x = composite_risk)) +
            geom_histogram(aes(y = after_stat(density)),
                           bins = 30, fill = "#4A90D9", color = "white", alpha = 0.8) +
            geom_density(color = "#2C3E50", linewidth = 0.8) +
            geom_vline(xintercept = 0, linetype = "dashed", color = "gray50") +
            labs(
                title = "Composite Cardiometabolic Risk Score",
                subtitle = "Mean PRS z-score across all traits",
                x = "Composite Risk (Mean Z-score)",
                y = "Density"
            ) +
            theme_prism(base_size = 12) +
            theme(
                plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
                plot.subtitle = element_text(hjust = 0.5, size = 10, color = "gray40")
            )
    }

    .save_plot(p, file.path(output_dir, "dashboard_composite_risk.png"), width = 10, height = 6)
    return(invisible(p))
}

# --- Dashboard: Population x Trait Heatmap ------------------------------------

plot_population_heatmap <- function(combined_scores, output_dir = "results") {
    cat("  [Dashboard] Population-trait heatmap\n")

    if (!"super_population" %in% names(combined_scores)) {
        cat("   Skipped (no population labels)\n")
        return(invisible(NULL))
    }

    prs_cols <- grep("^prs_", names(combined_scores), value = TRUE)
    trait_labels <- sub("^prs_", "", prs_cols)

    plot_df <- combined_scores[!is.na(combined_scores$super_population), ]

    # Calculate mean z-score per population per trait
    heatmap_data <- do.call(rbind, lapply(seq_along(prs_cols), function(i) {
        plot_df %>%
            group_by(super_population) %>%
            summarise(mean_z = mean(.data[[prs_cols[i]]], na.rm = TRUE), .groups = "drop") %>%
            mutate(trait = trait_labels[i])
    }))

    heatmap_data$label <- sprintf("%+.2f", heatmap_data$mean_z)

    p <- ggplot(heatmap_data, aes(x = trait, y = super_population, fill = mean_z)) +
        geom_tile(color = "white", linewidth = 1) +
        geom_text(aes(label = label), size = 4.5, fontface = "bold") +
        scale_fill_gradient2(low = "#3498DB", mid = "white", high = "#E74C3C",
                             midpoint = 0, name = "Mean PRS\n(Z-score)") +
        labs(
            title = "Mean PRS by Super-Population and Trait",
            subtitle = "Population-stratified cardiometabolic risk profile",
            x = "Trait", y = "Super-Population"
        ) +
        theme_prism(base_size = 12) +
        theme(
            plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
            plot.subtitle = element_text(hjust = 0.5, size = 10, color = "gray40"),
            axis.text.x = element_text(angle = 45, hjust = 1, size = 12),
            axis.text.y = element_text(size = 12),
            panel.grid = element_blank()
        )

    .save_plot(p, file.path(output_dir, "dashboard_population_heatmap.png"), width = 10, height = 7)
    return(invisible(p))
}

# --- Orchestrator -------------------------------------------------------------

#' Generate all plots: per-trait + dashboard
#' @param all_results list from score_traits.R
#' @param output_dir Directory to save plots (default: "results")
generate_all_plots <- function(all_results, output_dir = "results") {
    cat("\n=== Generating Multi-Trait PRS Visualizations ===\n\n")

    dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

    # Per-trait plots
    for (trait_name in all_results$trait_names) {
        cat("  [", trait_name, "] Per-trait plots\n")
        scores <- all_results$per_trait[[trait_name]]
        plot_trait_distribution(scores, trait_name, output_dir)
        plot_trait_population(scores, trait_name, output_dir)
        cat("\n")
    }

    # Dashboard plots
    cat("  === Dashboard Plots ===\n\n")
    plot_correlation_heatmap(all_results$cor_matrix, output_dir)
    plot_composite_risk(all_results$combined_scores, output_dir)
    plot_population_heatmap(all_results$combined_scores, output_dir)

    n_trait_plots <- all_results$n_traits * 2
    n_dashboard <- 3
    cat("\n\u2713 All plots generated successfully! (",
        n_trait_plots, " per-trait + ", n_dashboard, " dashboard, PNG + SVG)\n", sep = "")
}

