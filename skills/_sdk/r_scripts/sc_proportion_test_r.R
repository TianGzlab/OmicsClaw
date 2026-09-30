#!/usr/bin/env Rscript
# sc_proportion_test_r.R -- Monte Carlo permutation test for cell type proportion changes
#
# Base R only -- zero external package dependencies.
#
# CLI:
#   Rscript sc_proportion_test_r.R <meta_csv> <output_dir> <group_by> <split_by> [comparison] [n_permutations]
#
# Input:  cell metadata CSV with at minimum: cell_id, <group_by>, <split_by>
# Output: proportion_test_results.csv in output_dir
#
# Based on the permutation + bootstrap approach from scop::RunProportionTest.

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 4) {
  cat("Usage: Rscript sc_proportion_test_r.R <meta_csv> <output_dir> <group_by> <split_by> [comparison] [n_permutations]\n")
  cat("  meta_csv       : CSV with cell metadata (must contain group_by and split_by columns)\n")
  cat("  output_dir     : directory for proportion_test_results.csv\n")
  cat("  group_by       : column name for cell type labels\n")
  cat("  split_by       : column name for condition\n")
  cat("  comparison     : 'auto' or 'CondA_vs_CondB' (default: auto)\n")
  cat("  n_permutations : integer (default: 1000)\n")
  quit(status = 1)
}

meta_csv   <- args[1]
output_dir <- args[2]
group_by   <- args[3]
split_by   <- args[4]
comparison <- if (length(args) >= 5) args[5] else "auto"
n_perm     <- if (length(args) >= 6) as.integer(args[6]) else 1000L

# ---------------------------------------------------------------------------
# Permutation test function (base R only)
# ---------------------------------------------------------------------------

.run_permutation <- function(meta, group_col, split_col, group1, group2, n_perm) {
  # Filter cells belonging to this comparison

sub <- meta[meta[[split_col]] %in% c(group1, group2), , drop = FALSE]
  if (nrow(sub) < 10) {
    cat("  WARNING: fewer than 10 cells for comparison", group1, "vs", group2, "-- skipping\n")
    return(NULL)
  }

  clusters <- sort(unique(as.character(sub[[group_col]])))
  if (length(clusters) < 1) return(NULL)

  # --- Observed proportions ---
  count_observed <- table(factor(sub[[split_col]], levels = c(group1, group2)),
                          factor(sub[[group_col]], levels = clusters))
  prop_obs <- sweep(count_observed, 1, pmax(rowSums(count_observed), 1), "/")
  # Pseudocount to avoid log2(0)
  p1 <- as.numeric(prop_obs[group1, ]) + 1e-9
  p2 <- as.numeric(prop_obs[group2, ]) + 1e-9
  obs_log2FD <- log2(p1 / p2)
  names(obs_log2FD) <- clusters

  # --- Permutation loop ---
  labels <- sub[[split_col]]
  n <- length(labels)
  perm_log2FD <- matrix(NA_real_, nrow = n_perm, ncol = length(clusters),
                        dimnames = list(NULL, clusters))

  set.seed(42)
  for (i in seq_len(n_perm)) {
    perm_labels <- sample(labels, n, replace = FALSE)
    ct <- table(factor(perm_labels, levels = c(group1, group2)),
                factor(sub[[group_col]], levels = clusters))
    pp1 <- as.numeric(ct[group1, ]) / (max(sum(ct[group1, ]), 1)) + 1e-9
    pp2 <- as.numeric(ct[group2, ]) / (max(sum(ct[group2, ]), 1)) + 1e-9
    perm_log2FD[i, ] <- log2(pp1 / pp2)
  }

  # --- P-values (two-sided: fraction of |perm| >= |obs|) ---
  pval <- sapply(seq_along(clusters), function(j) {
    mean(abs(perm_log2FD[, j]) >= abs(obs_log2FD[j]), na.rm = TRUE)
  })
  names(pval) <- clusters
  fdr <- p.adjust(pval, method = "BH")

  # --- Bootstrap CI from permutation distribution ---
  boot_mean <- colMeans(perm_log2FD, na.rm = TRUE)
  boot_ci_lo <- apply(perm_log2FD, 2, quantile, probs = 0.025, na.rm = TRUE)
  boot_ci_hi <- apply(perm_log2FD, 2, quantile, probs = 0.975, na.rm = TRUE)

  data.frame(
    clusters         = clusters,
    group1           = group1,
    group2           = group2,
    comparison       = paste0(group1, "_vs_", group2),
    obs_log2FD       = as.numeric(obs_log2FD[clusters]),
    pval             = as.numeric(pval[clusters]),
    FDR              = as.numeric(fdr[clusters]),
    boot_mean_log2FD = as.numeric(boot_mean[clusters]),
    boot_CI_2.5      = as.numeric(boot_ci_lo[clusters]),
    boot_CI_97.5     = as.numeric(boot_ci_hi[clusters]),
    stringsAsFactors = FALSE
  )
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

tryCatch({
  # Read metadata
  meta <- read.csv(meta_csv, stringsAsFactors = FALSE)
  cat("Read", nrow(meta), "cells from", meta_csv, "\n")

  # Validate columns
  if (!group_by %in% colnames(meta)) {
    stop(sprintf("group_by column '%s' not found in metadata. Available: %s",
                 group_by, paste(colnames(meta), collapse = ", ")))
  }
  if (!split_by %in% colnames(meta)) {
    stop(sprintf("split_by column '%s' not found in metadata. Available: %s",
                 split_by, paste(colnames(meta), collapse = ", ")))
  }

  # Auto-cap permutations for demo speed: < 200 cells => max 200 permutations
  if (nrow(meta) < 200 && n_perm > 200) {
    cat("  NOTE: Small dataset (", nrow(meta), " cells) -- capping permutations at 200 for speed\n")
    n_perm <- 200L
  }

  # Create output directory
  if (!dir.exists(output_dir)) {
    dir.create(output_dir, recursive = TRUE)
  }

  # Build comparison pairs
  conditions <- sort(unique(as.character(meta[[split_by]])))
  cat("Conditions found:", paste(conditions, collapse = ", "), "\n")

  if (comparison == "auto") {
    # All unique ordered pairs
    if (length(conditions) < 2) {
      stop(sprintf("Need at least 2 conditions in '%s', found: %s",
                   split_by, paste(conditions, collapse = ", ")))
    }
    pairs <- combn(conditions, 2, simplify = FALSE)
  } else {
    # Parse "CondA_vs_CondB" format
    parts <- strsplit(comparison, "_vs_")[[1]]
    if (length(parts) != 2) {
      stop(sprintf("comparison must be 'auto' or 'CondA_vs_CondB', got: '%s'", comparison))
    }
    pairs <- list(parts)
  }

  cat("Running", length(pairs), "comparison(s) with", n_perm, "permutations each\n")

  # Run permutation test for each comparison
  all_results <- list()
  for (pair in pairs) {
    g1 <- pair[1]
    g2 <- pair[2]
    cat("  Comparison:", g1, "vs", g2, "\n")
    res <- .run_permutation(meta, group_by, split_by, g1, g2, n_perm)
    if (!is.null(res)) {
      all_results[[length(all_results) + 1]] <- res
    }
  }

  # Combine results
  if (length(all_results) > 0) {
    combined <- do.call(rbind, all_results)
  } else {
    # Empty result with correct headers
    combined <- data.frame(
      clusters = character(0),
      group1 = character(0),
      group2 = character(0),
      comparison = character(0),
      obs_log2FD = numeric(0),
      pval = numeric(0),
      FDR = numeric(0),
      boot_mean_log2FD = numeric(0),
      boot_CI_2.5 = numeric(0),
      boot_CI_97.5 = numeric(0),
      stringsAsFactors = FALSE
    )
    cat("  WARNING: No valid comparisons produced results\n")
  }

  # Write output
  out_path <- file.path(output_dir, "proportion_test_results.csv")
  write.csv(combined, out_path, row.names = FALSE)
  cat("Wrote", nrow(combined), "rows to", out_path, "\n")
  cat("Done.\n")

}, error = function(e) {
  cat("ERROR:", conditionMessage(e), "\n", file = stderr())
  quit(status = 1)
})
