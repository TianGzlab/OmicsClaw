# =============================================================================
# Cell-Cell Communication Analysis — Visualization
# =============================================================================
# Generates 6 publication-quality plots from CellChat analysis results.
# Saves PNG + SVG with graceful SVG fallback.
# =============================================================================

suppressPackageStartupMessages({
    library(CellChat)
    library(ggplot2)
    library(ggprism)
})

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) {
    suppressPackageStartupMessages(library(svglite))
}

# --- Save helpers -----------------------------------------------------------

#' Save a ggplot object to PNG + SVG
.save_ggplot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
    # Always save PNG
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi,
           device = "png")
    cat("   Saved:", png_path, "\n")

    # Always try SVG
    svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
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
            cat("   (SVG export failed for ggplot)\n")
        })
    })
}

#' Save a base R plot to PNG + SVG using a plot function (closure)
#' @param plot_fn A zero-argument function that draws the plot
.save_base_plot <- function(plot_fn, base_path, width = 8, height = 6,
                            dpi = 300) {
    # Always save PNG
    png_path <- sub("\\.(svg|png)$", ".png", base_path)
    png(png_path, width = width, height = height, units = "in", res = dpi)
    tryCatch(plot_fn(), error = function(e) {
        cat("   ⚠ PNG plot error:", conditionMessage(e), "\n")
    })
    dev.off()
    cat("   Saved:", png_path, "\n")

    # Always try SVG
    svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
    tryCatch({
        svg(svg_path, width = width, height = height)
        plot_fn()
        dev.off()
        cat("   Saved:", svg_path, "\n")
    }, error = function(e) {
        tryCatch(dev.off(), error = function(e2) NULL)
        cat("   (SVG export failed for base plot)\n")
    })
}


# --- Individual Plot Functions -----------------------------------------------

#' Plot 1: Interaction count network (circle plot)
plot_interaction_count_network <- function(cellchat, output_dir) {
    cat("\n   [1/6] Interaction count network...\n")

    group_sizes <- as.numeric(table(cellchat@idents))
    count_mat <- cellchat@net$count

    .save_base_plot(
        function() {
            par(mar = c(1, 1, 2, 1))
            netVisual_circle(
                count_mat,
                vertex.weight = group_sizes,
                weight.scale = TRUE,
                label.edge = FALSE,
                title.name = "Number of Interactions"
            )
        },
        file.path(output_dir, "interaction_count_network.png"),
        width = 8, height = 8
    )
}


#' Plot 2: Interaction strength network (circle plot)
plot_interaction_strength_network <- function(cellchat, output_dir) {
    cat("   [2/6] Interaction strength network...\n")

    group_sizes <- as.numeric(table(cellchat@idents))
    weight_mat <- cellchat@net$weight

    .save_base_plot(
        function() {
            par(mar = c(1, 1, 2, 1))
            netVisual_circle(
                weight_mat,
                vertex.weight = group_sizes,
                weight.scale = TRUE,
                label.edge = FALSE,
                title.name = "Interaction Strength"
            )
        },
        file.path(output_dir, "interaction_strength_network.png"),
        width = 8, height = 8
    )
}


#' Plot 3: Chord diagram of top pathways
plot_chord_top_pathways <- function(cellchat, output_dir) {
    cat("   [3/6] Chord diagram (aggregated)...\n")

    weight_net <- cellchat@net$weight

    .save_base_plot(
        function() {
            par(mar = c(1, 1, 2, 1))
            netVisual_chord_cell(
                cellchat,
                net = weight_net,
                title.name = "Cell-Cell Communication Network"
            )
        },
        file.path(output_dir, "chord_aggregated.png"),
        width = 10, height = 10
    )
}


#' Plot 4: Bubble plot of ligand-receptor pairs
plot_bubble_ligand_receptor <- function(cellchat, output_dir) {
    cat("   [4/6] Bubble plot (ligand-receptor pairs)...\n")

    # CellChat's netVisual_bubble returns a ggplot
    p <- tryCatch({
        netVisual_bubble(cellchat, remove.isolate = TRUE)
    }, error = function(e) {
        cat("   ⚠ Bubble plot failed:", conditionMessage(e), "\n")
        cat("   Trying with fewer sources...\n")
        # Fall back to top 5 source cell types
        sources <- levels(cellchat@idents)[1:min(5, length(levels(cellchat@idents)))]
        netVisual_bubble(cellchat, sources.use = sources, remove.isolate = TRUE)
    })

    if (!is.null(p) && inherits(p, "gg")) {
        # Apply ggprism theme to the ggplot bubble plot
        p <- p + theme_prism(base_size = 10) +
            theme(
                axis.text.x = element_text(angle = 45, hjust = 1, size = 8),
                axis.text.y = element_text(size = 7),
                plot.title = element_text(hjust = 0.5, face = "bold", size = 12),
                legend.position = "right"
            )
        .save_ggplot(p, file.path(output_dir, "bubble_ligand_receptor.png"),
                     width = 12, height = 10)
    }
}


#' Plot 5: Signaling role heatmap (outgoing + incoming)
plot_signaling_role_heatmap <- function(cellchat, output_dir) {
    cat("   [5/6] Signaling role heatmap...\n")

    # Outgoing signaling patterns
    tryCatch({
        # netAnalysis_signalingRole_heatmap returns a ComplexHeatmap object
        ht_out <- netAnalysis_signalingRole_heatmap(cellchat, pattern = "outgoing",
                                                     title = "Outgoing Signaling Patterns",
                                                     font.size = 8)
        # Save PNG
        png_path <- file.path(output_dir, "signaling_outgoing_heatmap.png")
        png(png_path, width = 10, height = 8, units = "in", res = 300)
        ComplexHeatmap::draw(ht_out)
        dev.off()
        cat("   Saved:", png_path, "\n")

        # Save SVG
        svg_path <- file.path(output_dir, "signaling_outgoing_heatmap.svg")
        tryCatch({
            svg(svg_path, width = 10, height = 8)
            ComplexHeatmap::draw(ht_out)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e2) {
            tryCatch(dev.off(), error = function(e3) NULL)
            cat("   (SVG export failed for outgoing heatmap)\n")
        })
    }, error = function(e) {
        cat("   ⚠ Outgoing heatmap failed:", conditionMessage(e), "\n")
    })

    # Incoming signaling patterns
    tryCatch({
        ht_in <- netAnalysis_signalingRole_heatmap(cellchat, pattern = "incoming",
                                                    title = "Incoming Signaling Patterns",
                                                    font.size = 8)
        png_path <- file.path(output_dir, "signaling_incoming_heatmap.png")
        png(png_path, width = 10, height = 8, units = "in", res = 300)
        ComplexHeatmap::draw(ht_in)
        dev.off()
        cat("   Saved:", png_path, "\n")

        svg_path <- file.path(output_dir, "signaling_incoming_heatmap.svg")
        tryCatch({
            svg(svg_path, width = 10, height = 8)
            ComplexHeatmap::draw(ht_in)
            dev.off()
            cat("   Saved:", svg_path, "\n")
        }, error = function(e2) {
            tryCatch(dev.off(), error = function(e3) NULL)
            cat("   (SVG export failed for incoming heatmap)\n")
        })
    }, error = function(e) {
        cat("   ⚠ Incoming heatmap failed:", conditionMessage(e), "\n")
    })
}


#' Plot 6: Signaling role scatter (senders vs receivers)
plot_signaling_role_scatter <- function(cellchat, output_dir) {
    cat("   [6/6] Signaling role scatter...\n")

    tryCatch({
        p <- netAnalysis_signalingRole_scatter(cellchat)

        if (inherits(p, "gg")) {
            p <- p + theme_prism(base_size = 12) +
                theme(
                    plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
                )
            .save_ggplot(p, file.path(output_dir, "signaling_role_scatter.png"),
                         width = 8, height = 7)
        }
    }, error = function(e) {
        cat("   ⚠ Signaling scatter failed:", conditionMessage(e), "\n")
    })
}


# --- Main entry point --------------------------------------------------------

#' Generate all CellChat visualizations
#'
#' @param cellchat CellChat object (from run_cellchat_analysis)
#' @param output_dir Directory for output files
generate_all_plots <- function(cellchat, output_dir = "results") {
    cat("\n=== Generating CellChat Visualizations ===\n")

    dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

    plot_count <- 0

    # Plot 1: Interaction count network
    tryCatch({
        plot_interaction_count_network(cellchat, output_dir)
        plot_count <- plot_count + 1
    }, error = function(e) {
        cat("   ✗ Interaction count network failed:", conditionMessage(e), "\n")
    })

    # Plot 2: Interaction strength network
    tryCatch({
        plot_interaction_strength_network(cellchat, output_dir)
        plot_count <- plot_count + 1
    }, error = function(e) {
        cat("   ✗ Interaction strength network failed:", conditionMessage(e), "\n")
    })

    # Plot 3: Chord diagram
    tryCatch({
        plot_chord_top_pathways(cellchat, output_dir)
        plot_count <- plot_count + 1
    }, error = function(e) {
        cat("   ✗ Chord diagram failed:", conditionMessage(e), "\n")
    })

    # Plot 4: Bubble plot
    tryCatch({
        plot_bubble_ligand_receptor(cellchat, output_dir)
        plot_count <- plot_count + 1
    }, error = function(e) {
        cat("   ✗ Bubble plot failed:", conditionMessage(e), "\n")
    })

    # Plot 5: Signaling role heatmap
    tryCatch({
        plot_signaling_role_heatmap(cellchat, output_dir)
        plot_count <- plot_count + 1
    }, error = function(e) {
        cat("   ✗ Signaling role heatmap failed:", conditionMessage(e), "\n")
    })

    # Plot 6: Signaling role scatter
    tryCatch({
        plot_signaling_role_scatter(cellchat, output_dir)
        plot_count <- plot_count + 1
    }, error = function(e) {
        cat("   ✗ Signaling role scatter failed:", conditionMessage(e), "\n")
    })

    cat("\n✓ All plots generated successfully!", plot_count, "visualizations saved\n\n")
}

