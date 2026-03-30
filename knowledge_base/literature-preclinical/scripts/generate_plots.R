#!/usr/bin/env Rscript
#
# Generate 4-panel preclinical experiment visualization (Step 3).
#
# Creates:
# 1. Experiment type breakdown (in vitro / in vivo / both / unclassified)
# 2. Top assay types (horizontal bar chart)
# 3. Animal model distribution (bar chart)
# 4. Publication timeline by experiment type (stacked bars)
#
# Uses ggplot2 with ggprism publication theme.
# Exports both PNG (300 DPI) and SVG with graceful fallback.
#

# --- Load packages -----------------------------------------------------------

required_pkgs <- c("ggplot2", "ggprism", "dplyr", "tidyr", "patchwork")

for (pkg in required_pkgs) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    stop(paste0("Missing required package: ", pkg,
                "\nInstall with: install.packages('", pkg, "')"))
  }
}

library(ggplot2)
library(ggprism)
library(dplyr)
library(tidyr)
library(patchwork)

# Try to load svglite for high-quality SVG (optional)
.has_svglite <- requireNamespace("svglite", quietly = TRUE)
if (.has_svglite) library(svglite)


# --- Main function -----------------------------------------------------------

generate_all_plots <- function(input_dir = "preclinical_results",
                               output_dir = "preclinical_results") {
  cat("\n", paste(rep("=", 70), collapse = ""), "\n")
  cat("GENERATING VISUALIZATIONS\n")
  cat(paste(rep("=", 70), collapse = ""), "\n\n")

  dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

  # Read extraction CSV
  extract_file <- file.path(input_dir, "experiment_extraction.csv")
  if (!file.exists(extract_file)) {
    stop(paste("File not found:", extract_file,
               "\nRun Steps 1-2 first to generate experiment_extraction.csv"))
  }

  df <- read.csv(extract_file, stringsAsFactors = FALSE)
  cat("  Read", nrow(df), "papers from", extract_file, "\n\n")

  # Build 4 panels
  cat("1. Generating experiment type breakdown...\n")
  p1 <- .plot_experiment_types(df)

  cat("2. Generating top assay types...\n")
  p2 <- .plot_assay_types(df)

  cat("3. Generating animal model distribution...\n")
  p3 <- .plot_animal_models(df)

  cat("4. Generating publication timeline...\n")
  p4 <- .plot_timeline(df)

  # Combine with patchwork
  cat("\n5. Saving combined figure...\n")
  combined <- (p1 | p2) / (p3 | p4) +
    plot_annotation(
      title = "Preclinical Literature Extraction",
      subtitle = paste(nrow(df), "papers analyzed"),
      theme = theme(
        plot.title = element_text(hjust = 0.5, face = "bold", size = 16),
        plot.subtitle = element_text(hjust = 0.5, size = 12)
      )
    )

  .save_plot(combined, file.path(output_dir, "preclinical_plots"),
             width = 16, height = 12)

  cat("\n\u2713 All plots generated successfully!\n")
  cat(paste(rep("=", 70), collapse = ""), "\n\n")
}


# --- Panel 1: Experiment Type Breakdown --------------------------------------

.plot_experiment_types <- function(df) {
  type_counts <- df %>%
    count(experiment_type) %>%
    mutate(
      experiment_type = factor(experiment_type,
                               levels = c("both", "in_vitro", "in_vivo", "unclassified")),
      label = paste0(n, " (", round(n / sum(n) * 100, 1), "%)")
    )

  # Define colors
  type_colors <- c(
    "both" = "#2E86C1",
    "in_vitro" = "#E74C3C",
    "in_vivo" = "#27AE60",
    "unclassified" = "#BDC3C7"
  )

  ggplot(type_counts, aes(x = experiment_type, y = n, fill = experiment_type)) +
    geom_col(color = "black", linewidth = 0.3) +
    geom_text(aes(label = label), vjust = -0.5, size = 3.5) +
    scale_fill_manual(values = type_colors, guide = "none") +
    scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
    labs(
      title = "Experiment Type Breakdown",
      x = "Experiment Type",
      y = "Number of Papers"
    ) +
    theme_prism(base_size = 12) +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
    )
}


# --- Panel 2: Top Assay Types ------------------------------------------------

.plot_assay_types <- function(df, top_n = 10) {
  # Split semicolon-separated assays and count
  assay_data <- df %>%
    filter(assays != "") %>%
    separate_rows(assays, sep = ";\\s*") %>%
    filter(assays != "") %>%
    count(assays, sort = TRUE) %>%
    head(top_n) %>%
    mutate(assays = factor(assays, levels = rev(assays)))

  if (nrow(assay_data) == 0) {
    return(
      ggplot() +
        annotate("text", x = 0.5, y = 0.5, label = "No assays detected", size = 5) +
        labs(title = "Top Assay Types") +
        theme_prism(base_size = 12) +
        theme(
          plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
          axis.text = element_blank(),
          axis.ticks = element_blank(),
          axis.title = element_blank()
        )
    )
  }

  ggplot(assay_data, aes(x = assays, y = n)) +
    geom_col(fill = "#E74C3C", color = "black", linewidth = 0.3) +
    geom_text(aes(label = n), hjust = -0.3, size = 3.5) +
    coord_flip() +
    scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
    labs(
      title = "Top Assay Types",
      x = "",
      y = "Number of Papers"
    ) +
    theme_prism(base_size = 12) +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
    )
}


# --- Panel 3: Animal Model Distribution --------------------------------------

.plot_animal_models <- function(df, top_n = 8) {
  model_data <- df %>%
    filter(animal_models != "") %>%
    separate_rows(animal_models, sep = ";\\s*") %>%
    filter(animal_models != "") %>%
    count(animal_models, sort = TRUE) %>%
    head(top_n) %>%
    mutate(animal_models = factor(animal_models, levels = rev(animal_models)))

  if (nrow(model_data) == 0) {
    return(
      ggplot() +
        annotate("text", x = 0.5, y = 0.5, label = "No animal models detected",
                 size = 5) +
        labs(title = "Animal Model Distribution") +
        theme_prism(base_size = 12) +
        theme(
          plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
          axis.text = element_blank(),
          axis.ticks = element_blank(),
          axis.title = element_blank()
        )
    )
  }

  ggplot(model_data, aes(x = animal_models, y = n)) +
    geom_col(fill = "#27AE60", color = "black", linewidth = 0.3) +
    geom_text(aes(label = n), hjust = -0.3, size = 3.5) +
    coord_flip() +
    scale_y_continuous(expand = expansion(mult = c(0, 0.15))) +
    labs(
      title = "Animal Model Distribution",
      x = "",
      y = "Number of Papers"
    ) +
    theme_prism(base_size = 12) +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold", size = 14)
    )
}


# --- Panel 4: Publication Timeline -------------------------------------------

.plot_timeline <- function(df) {
  timeline_data <- df %>%
    mutate(year = substr(publication_date, 1, 4)) %>%
    filter(grepl("^\\d{4}$", year)) %>%
    count(year, experiment_type) %>%
    mutate(
      experiment_type = factor(experiment_type,
                               levels = c("both", "in_vitro", "in_vivo", "unclassified"))
    )

  type_colors <- c(
    "both" = "#2E86C1",
    "in_vitro" = "#E74C3C",
    "in_vivo" = "#27AE60",
    "unclassified" = "#BDC3C7"
  )

  if (nrow(timeline_data) == 0) {
    return(
      ggplot() +
        annotate("text", x = 0.5, y = 0.5, label = "No publication dates available",
                 size = 5) +
        labs(title = "Publication Timeline") +
        theme_prism(base_size = 12) +
        theme(
          plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
          axis.text = element_blank(),
          axis.ticks = element_blank(),
          axis.title = element_blank()
        )
    )
  }

  ggplot(timeline_data, aes(x = year, y = n, fill = experiment_type)) +
    geom_col(color = "black", linewidth = 0.3) +
    scale_fill_manual(values = type_colors, name = "Type") +
    scale_y_continuous(expand = expansion(mult = c(0, 0.1))) +
    labs(
      title = "Publication Timeline",
      x = "Year",
      y = "Number of Papers"
    ) +
    theme_prism(base_size = 12) +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold", size = 14),
      axis.text.x = element_text(angle = 45, hjust = 1),
      legend.position = "bottom"
    )
}


# --- Save helper -------------------------------------------------------------

.save_plot <- function(plot, base_path, width = 16, height = 12, dpi = 300) {
  # Always save PNG
  png_path <- paste0(base_path, ".png")
  ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi,
         device = "png")
  cat("   Saved:", png_path, "\n")

  # Always try SVG - try ggsave first, fall back to svg() device
  svg_path <- paste0(base_path, ".svg")
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


# --- Run if sourced or executed directly --------------------------------------

# When sourced, the function is available to call.
# When run from command line, execute with default paths.
if (!interactive() && identical(sys.frame(1)$ofile, NULL)) {
  args <- commandArgs(trailingOnly = TRUE)
  input_dir <- if (length(args) >= 1) args[1] else "preclinical_results"
  output_dir <- if (length(args) >= 2) args[2] else input_dir
  generate_all_plots(input_dir = input_dir, output_dir = output_dir)
}

