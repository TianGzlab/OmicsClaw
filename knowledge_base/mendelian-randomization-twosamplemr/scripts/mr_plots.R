# =============================================================================
# Mendelian Randomization - Visualization
# =============================================================================
# Functions:
#   generate_all_plots()  - Generate all 4 standard MR plots (PNG + SVG)
# =============================================================================

suppressPackageStartupMessages({
    library(TwoSampleMR)
    library(ggplot2)
    library(ggprism)
})

# --- SVG support detection ---------------------------------------------------

.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
    library(svglite)
}

# --- Plot save helper (PNG + SVG with graceful fallback) ---------------------

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

# --- Main plot generation function -------------------------------------------

#' Generate all standard MR diagnostic plots
#'
#' Creates 4 plots:
#'   1. Scatter plot - SNP-exposure vs SNP-outcome with method lines
#'   2. Forest plot - Individual SNP estimates + combined estimates
#'   3. Funnel plot - Precision vs effect size (assesses asymmetry)
#'   4. Leave-one-out plot - Robustness to individual SNP removal
#'
#' @param mr_results MR results from run_mr()
#' @param dat Harmonized data from load_data.R
#' @param single_snp_results Single-SNP results from run_sensitivity()$singlesnp
#' @param leaveoneout_results Leave-one-out results from run_sensitivity()$leaveoneout
#' @param output_dir Directory for saving plots (default: "mr_results")
generate_all_plots <- function(mr_results, dat, single_snp_results,
                                leaveoneout_results, output_dir = "mr_results") {
    cat("\n=== Generating MR Plots ===\n\n")

    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
    }

    plots_saved <- 0

    # 1. Scatter plot
    cat("1/4 Scatter plot (SNP-exposure vs SNP-outcome associations)...\n")
    tryCatch({
        plot_warnings <- list()
        p_scatter <- withCallingHandlers(
            mr_scatter_plot(mr_results, dat),
            warning = function(w) {
                plot_warnings[[length(plot_warnings) + 1]] <<- conditionMessage(w)
                invokeRestart("muffleWarning")
            })
        # TwoSampleMR returns a list of ggplot objects (one per exposure-outcome pair)
        for (i in seq_along(p_scatter)) {
            p_scatter[[i]] <- p_scatter[[i]] + theme_prism(base_size = 12)
            base_name <- file.path(output_dir, paste0("mr_scatter_plot",
                                   if (length(p_scatter) > 1) paste0("_", i) else ""))
            # Capture ggsave warnings too (e.g., removed rows)
            save_warnings <- list()
            withCallingHandlers(
                .save_plot(p_scatter[[i]], paste0(base_name, ".png"), width = 9, height = 7),
                warning = function(w) {
                    save_warnings[[length(save_warnings) + 1]] <<- conditionMessage(w)
                    invokeRestart("muffleWarning")
                })
            plots_saved <- plots_saved + 1
            plot_warnings <- c(plot_warnings, save_warnings)
        }
        if (length(plot_warnings) > 0) {
            unique_warnings <- unique(unlist(plot_warnings))
            for (w in unique_warnings) {
                cat("   \u26a0 Plot warning:", w, "\n")
            }
            cat("   Investigate which SNP(s) were affected.\n")
        }
    }, error = function(e) {
        cat("   Warning: Scatter plot failed (", conditionMessage(e), ")\n")
    })
    cat("\n")

    # 2. Forest plot
    cat("2/4 Forest plot (individual SNP estimates)...\n")
    tryCatch({
        p_forest <- mr_forest_plot(single_snp_results)
        for (i in seq_along(p_forest)) {
            p_forest[[i]] <- p_forest[[i]] + theme_prism(base_size = 12)
            n_snps <- nrow(dat)
            plot_height <- max(6, 3 + n_snps * 0.3)
            base_name <- file.path(output_dir, paste0("mr_forest_plot",
                                   if (length(p_forest) > 1) paste0("_", i) else ""))
            .save_plot(p_forest[[i]], paste0(base_name, ".png"),
                      width = 9, height = plot_height)
            plots_saved <- plots_saved + 1
        }
    }, error = function(e) {
        cat("   Warning: Forest plot failed (", conditionMessage(e), ")\n")
    })
    cat("\n")

    # 3. Funnel plot
    cat("3/4 Funnel plot (instrument strength assessment)...\n")
    tryCatch({
        p_funnel <- mr_funnel_plot(single_snp_results)
        for (i in seq_along(p_funnel)) {
            p_funnel[[i]] <- p_funnel[[i]] + theme_prism(base_size = 12)
            base_name <- file.path(output_dir, paste0("mr_funnel_plot",
                                   if (length(p_funnel) > 1) paste0("_", i) else ""))
            .save_plot(p_funnel[[i]], paste0(base_name, ".png"), width = 8, height = 6)
            plots_saved <- plots_saved + 1
        }
    }, error = function(e) {
        cat("   Warning: Funnel plot failed (", conditionMessage(e), ")\n")
    })
    cat("\n")

    # 4. Leave-one-out plot
    cat("4/4 Leave-one-out plot (robustness assessment)...\n")
    tryCatch({
        p_loo <- mr_leaveoneout_plot(leaveoneout_results)
        for (i in seq_along(p_loo)) {
            p_loo[[i]] <- p_loo[[i]] + theme_prism(base_size = 12)
            n_snps <- nrow(dat)
            plot_height <- max(6, 3 + n_snps * 0.3)
            base_name <- file.path(output_dir, paste0("mr_leaveoneout_plot",
                                   if (length(p_loo) > 1) paste0("_", i) else ""))
            .save_plot(p_loo[[i]], paste0(base_name, ".png"),
                      width = 9, height = plot_height)
            plots_saved <- plots_saved + 1
        }
    }, error = function(e) {
        cat("   Warning: Leave-one-out plot failed (", conditionMessage(e), ")\n")
    })

    cat("\n✓ All MR plots generated successfully! (", plots_saved, " plots saved)\n", sep = "")
}

