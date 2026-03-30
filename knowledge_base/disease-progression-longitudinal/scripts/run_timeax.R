#!/usr/bin/env Rscript

# TimeAx R wrapper script
# This script runs TimeAx trajectory alignment and saves results to CSV files
# Called from Python via subprocess

suppressPackageStartupMessages({
  library(TimeAx)
  library(ggplot2)
  library(ggprism)
})

# Parse command line arguments
args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 4) {
  cat("Usage: Rscript run_timeax.R <data_file> <metadata_file> <output_dir> <n_iterations> [n_seeds]\n")
  quit(status = 1)
}

data_file <- args[1]
metadata_file <- args[2]
output_dir <- args[3]
n_iterations <- as.integer(args[4])
n_seeds <- if (length(args) >= 5) as.integer(args[5]) else 50

cat("\n=== TimeAx R Wrapper ===\n")
cat("Data file:", data_file, "\n")
cat("Metadata file:", metadata_file, "\n")
cat("Output directory:", output_dir, "\n")
cat("Iterations:", n_iterations, "\n")
cat("Seed features:", n_seeds, "\n\n")

# Create output directory
dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

# Load data
cat("Loading data...\n")
data_matrix <- read.csv(data_file, row.names = 1, check.names = FALSE)
metadata <- read.csv(metadata_file)

# Ensure data is a matrix
data_matrix <- as.matrix(data_matrix)

cat("  Features:", nrow(data_matrix), "\n")
cat("  Samples:", ncol(data_matrix), "\n")
cat("  Patients:", length(unique(metadata$patient_id)), "\n")

# Prepare data for TimeAx
# TimeAx expects columns to be samples ordered by patient and time
# Sort samples by patient_id and timepoint
metadata <- metadata[order(metadata$patient_id, metadata$timepoint), ]
sample_order <- metadata$sample_id
data_matrix <- data_matrix[, sample_order]

# Get sample names vector (patient IDs)
sample_names <- metadata$patient_id

cat("\nCreating TimeAx model...\n")
cat("  (This may take several minutes)\n")

# Create model
tryCatch({
  model <- modelCreation(
    trainData = data_matrix,
    sampleNames = sample_names,
    ratio = TRUE,  # Compute feature ratios (default; handles batch effects)
    numOfIter = n_iterations,
    numOfTopFeatures = n_seeds,
    seed = NULL,
    no_cores = NULL
  )

  cat("✓ Model created successfully\n")

}, error = function(e) {
  cat("Error creating model:", conditionMessage(e), "\n")
  quit(status = 1)
})

# Get pseudotime predictions
cat("\nPredicting pseudotime...\n")
tryCatch({
  pseudo_stats <- predictByConsensus(
    model = model,
    testData = data_matrix,
    no_cores = NULL,
    seed = NULL,
    sampleNames = NULL
  )

  pseudotime <- pseudo_stats$predictions
  uncertainty <- pseudo_stats$uncertainty

  cat("✓ Pseudotime computed\n")
  cat("  Range: [", min(pseudotime), ", ", max(pseudotime), "]\n", sep="")
  cat("  Mean uncertainty:", mean(uncertainty), "\n")

}, error = function(e) {
  cat("Error predicting pseudotime:", conditionMessage(e), "\n")
  quit(status = 1)
})

# Compute trajectory quality metrics
cat("\nComputing trajectory quality...\n")

# Primary metric: within-patient monotonicity
# Measures whether pseudotime increases with actual timepoint for each patient
monotonicity_score <- tryCatch({
  patient_cors <- sapply(split(seq_along(sample_names), sample_names), function(idx) {
    if (length(idx) < 3) return(NA)
    cor(metadata$timepoint[match(sample_order[idx], metadata$sample_id)],
        pseudotime[idx], method = "spearman")
  })
  patient_cors <- patient_cors[!is.na(patient_cors)]
  n_positive <- sum(patient_cors > 0)
  n_total <- length(patient_cors)
  mean_cor <- mean(patient_cors)

  cat("✓ Within-patient monotonicity:", round(mean_cor, 3), "\n")
  cat("  Patients with positive trend:", n_positive, "/", n_total, "\n")

  if (mean_cor > 0.5) {
    cat("  ✓ Good trajectory quality (>0.5)\n")
  } else if (mean_cor > 0.3) {
    cat("  ⚠ Moderate trajectory quality (0.3-0.5)\n")
  } else {
    cat("  ⚠ Weak trajectory quality (<0.3)\n")
  }
  mean_cor
}, error = function(e) {
  cat("Warning: Could not compute monotonicity:", conditionMessage(e), "\n")
  NA
})

# Secondary metric: TimeAx robustness (LOO consistency)
# Note: this metric can give misleading negative values with small cohorts
robustness_score <- tryCatch({
  robustness_stats <- robustness(
    model = model,
    trainData = data_matrix,
    sampleNames = sample_names,
    pseudo = pseudo_stats,
    no_cores = NULL
  )
  rob <- robustness_stats$score
  cat("  LOO robustness:", round(rob, 3), "\n")
  rob
}, error = function(e) {
  cat("  LOO robustness: N/A\n")
  NA
})

# Save results
cat("\nSaving results...\n")

# Pseudotime results
results_df <- data.frame(
  sample_id = sample_order,
  pseudotime = pseudotime,
  uncertainty = uncertainty
)
write.csv(results_df, file.path(output_dir, "timeax_pseudotime.csv"), row.names = FALSE)
cat("  ✓", file.path(output_dir, "timeax_pseudotime.csv"), "\n")

# Seed features (model$seed returns feature names, not indices)
seed_features <- model$seed
write.csv(
  data.frame(feature = seed_features),
  file.path(output_dir, "timeax_seed_features.csv"),
  row.names = FALSE
)
cat("  ✓", file.path(output_dir, "timeax_seed_features.csv"), "\n")

# Model info
model_info <- data.frame(
  parameter = c("n_iterations", "n_seeds", "robustness_score", "monotonicity_score", "n_features", "n_samples"),
  value = c(n_iterations, n_seeds, robustness_score, monotonicity_score, nrow(data_matrix), ncol(data_matrix))
)
write.csv(model_info, file.path(output_dir, "timeax_model_info.csv"), row.names = FALSE)
cat("  ✓", file.path(output_dir, "timeax_model_info.csv"), "\n")

# Save model object as RDS
saveRDS(model, file.path(output_dir, "timeax_model.rds"))
cat("  ✓", file.path(output_dir, "timeax_model.rds"), "\n")

# ==============================================================================
# Generate TimeAx-specific plots (PNG + SVG with fallback)
# ==============================================================================

.save_plot <- function(p, base_name, width = 8, height = 6) {
  png_path <- file.path(output_dir, paste0(base_name, ".png"))
  ggsave(png_path, plot = p, width = width, height = height, dpi = 300)
  cat("  ✓", png_path, "\n")

  svg_path <- file.path(output_dir, paste0(base_name, ".svg"))
  tryCatch({
    ggsave(svg_path, plot = p, width = width, height = height, device = "svg")
    cat("  ✓", svg_path, "\n")
  }, error = function(e) {
    tryCatch({
      svg(svg_path, width = width, height = height)
      print(p)
      dev.off()
      cat("  ✓", svg_path, "\n")
    }, error = function(e2) {
      cat("  (SVG export failed for", base_name, ")\n")
    })
  })
}

cat("\nGenerating TimeAx plots...\n")

# Build plotting data frame
plot_df <- data.frame(
  sample_id = sample_order,
  patient_id = metadata$patient_id,
  timepoint = metadata$timepoint,
  pseudotime = pseudotime,
  uncertainty = uncertainty
)

# --- Plot 1: Pseudotime vs actual time (per patient trajectories) ---
tryCatch({
  p1 <- ggplot(plot_df, aes(x = timepoint, y = pseudotime, group = patient_id, color = patient_id)) +
    geom_line(alpha = 0.6) +
    geom_point(aes(size = 1 - uncertainty), alpha = 0.8) +
    scale_size_continuous(name = "Confidence", range = c(1, 4)) +
    labs(
      title = "TimeAx: Pseudotime vs Actual Time",
      subtitle = "Each line = one patient trajectory; point size = confidence",
      x = "Actual Time",
      y = "Disease Pseudotime",
      color = "Patient"
    ) +
    theme_prism(base_size = 12) +
    theme(legend.position = "right")

  # Hide patient legend if too many patients
  if (length(unique(plot_df$patient_id)) > 15) {
    p1 <- p1 + guides(color = "none")
  }

  .save_plot(p1, "timeax_pseudotime_vs_time")
}, error = function(e) {
  cat("  ✗ Pseudotime vs time plot failed:", conditionMessage(e), "\n")
})

# --- Plot 2: Patient progression rates ---
tryCatch({
  # Compute per-patient progression stats
  patient_stats <- do.call(rbind, lapply(split(plot_df, plot_df$patient_id), function(d) {
    d <- d[order(d$timepoint), ]
    data.frame(
      patient_id = d$patient_id[1],
      pseudotime_change = d$pseudotime[nrow(d)] - d$pseudotime[1],
      time_span = max(d$timepoint) - min(d$timepoint),
      n_timepoints = nrow(d),
      mean_uncertainty = mean(d$uncertainty)
    )
  }))

  patient_stats$rate <- ifelse(
    patient_stats$time_span > 0,
    patient_stats$pseudotime_change / patient_stats$time_span,
    0
  )
  patient_stats <- patient_stats[order(patient_stats$rate, decreasing = TRUE), ]
  patient_stats$patient_id <- factor(patient_stats$patient_id, levels = patient_stats$patient_id)

  p2 <- ggplot(patient_stats, aes(x = patient_id, y = rate, fill = rate)) +
    geom_col() +
    scale_fill_gradient2(low = "#2166AC", mid = "#F7F7F7", high = "#B2182B", midpoint = median(patient_stats$rate)) +
    labs(
      title = "TimeAx: Patient Progression Rates",
      subtitle = "Pseudotime change per unit time; red = fast, blue = slow",
      x = "Patient",
      y = "Progression Rate (pseudotime / time)"
    ) +
    theme_prism(base_size = 12) +
    theme(
      axis.text.x = element_text(angle = 45, hjust = 1, size = 8),
      legend.position = "none"
    )

  .save_plot(p2, "timeax_progression_rates")
}, error = function(e) {
  cat("  ✗ Progression rates plot failed:", conditionMessage(e), "\n")
})

# --- Plot 3: Seed feature dynamics along pseudotime ---
tryCatch({
  seed_names <- model$seed  # character vector of feature names
  n_show <- min(length(seed_names), 9)  # Show up to 9 seed features
  top_seeds <- seed_names[seq_len(n_show)]

  seed_long <- do.call(rbind, lapply(top_seeds, function(feat) {
    data.frame(
      feature = feat,
      pseudotime = pseudotime,
      expression = as.numeric(data_matrix[feat, ])
    )
  }))

  p3 <- ggplot(seed_long, aes(x = pseudotime, y = expression)) +
    geom_point(alpha = 0.3, size = 1, color = "gray50") +
    geom_smooth(method = "loess", se = TRUE, color = "#D6604D", fill = "#FDDBC7") +
    facet_wrap(~ feature, scales = "free_y", ncol = 3) +
    labs(
      title = "TimeAx: Seed Feature Dynamics",
      subtitle = "Expression trends along disease pseudotime (LOESS smooth)",
      x = "Disease Pseudotime",
      y = "Expression"
    ) +
    theme_prism(base_size = 10)

  plot_height <- ceiling(n_show / 3) * 3
  .save_plot(p3, "timeax_seed_dynamics", width = 10, height = max(plot_height, 4))
}, error = function(e) {
  cat("  ✗ Seed dynamics plot failed:", conditionMessage(e), "\n")
})

# --- Plot 4: Uncertainty distribution ---
tryCatch({
  p4 <- ggplot(plot_df, aes(x = pseudotime, y = uncertainty)) +
    geom_point(aes(color = uncertainty), alpha = 0.7, size = 2) +
    geom_smooth(method = "loess", se = TRUE, color = "black", linewidth = 0.8) +
    scale_color_gradient(low = "#4393C3", high = "#D6604D") +
    labs(
      title = "TimeAx: Pseudotime Uncertainty",
      subtitle = "Higher uncertainty = less confident positioning on trajectory",
      x = "Disease Pseudotime",
      y = "Uncertainty Score"
    ) +
    theme_prism(base_size = 12) +
    theme(legend.position = "none")

  .save_plot(p4, "timeax_uncertainty")
}, error = function(e) {
  cat("  ✗ Uncertainty plot failed:", conditionMessage(e), "\n")
})

cat("\n=== TimeAx Complete ===\n")
cat("Results saved to:", output_dir, "\n")

