###############################################################################
# export_results.R — Export multi-trait PRS results and RDS for downstream use
#
# Function:
#   export_all(all_results, output_dir)
###############################################################################

library(data.table)
library(dplyr)

# --- Helper: population summary -----------------------------------------------

.make_population_summary <- function(combined_scores) {
    if (!"super_population" %in% names(combined_scores)) return(NULL)

    prs_cols <- grep("^prs_", names(combined_scores), value = TRUE)
    trait_labels <- sub("^prs_", "", prs_cols)

    rows <- list()
    for (i in seq_along(prs_cols)) {
        s <- combined_scores %>%
            filter(!is.na(super_population)) %>%
            group_by(super_population) %>%
            summarise(
                n = n(),
                mean_z = round(mean(.data[[prs_cols[i]]], na.rm = TRUE), 4),
                sd_z = round(sd(.data[[prs_cols[i]]], na.rm = TRUE), 4),
                min_z = round(min(.data[[prs_cols[i]]], na.rm = TRUE), 4),
                max_z = round(max(.data[[prs_cols[i]]], na.rm = TRUE), 4),
                .groups = "drop"
            ) %>%
            mutate(trait = trait_labels[i])
        rows[[i]] <- s
    }

    # Add composite risk summary
    comp_s <- combined_scores %>%
        filter(!is.na(super_population)) %>%
        group_by(super_population) %>%
        summarise(
            n = n(),
            mean_z = round(mean(composite_risk, na.rm = TRUE), 4),
            sd_z = round(sd(composite_risk, na.rm = TRUE), 4),
            min_z = round(min(composite_risk, na.rm = TRUE), 4),
            max_z = round(max(composite_risk, na.rm = TRUE), 4),
            .groups = "drop"
        ) %>%
        mutate(trait = "COMPOSITE")
    rows[[length(rows) + 1]] <- comp_s

    do.call(rbind, rows)
}

# --- Main export function -----------------------------------------------------

#' Export all multi-trait PRS results
#' @param all_results list from score_traits.R
#' @param output_dir Directory to save files (default: "results")
export_all <- function(all_results, output_dir = "results") {
    cat("\n=== Exporting Multi-Trait PRS Results ===\n\n")

    dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)

    # 1. Combined scores (wide format: one row per individual, one column per trait)
    cat("[1/7] Combined PRS scores (wide format)\n")
    fwrite(all_results$combined_scores, file.path(output_dir, "combined_prs_scores.csv"))
    cat("  Saved:", file.path(output_dir, "combined_prs_scores.csv"), "\n")
    cat("  (", nrow(all_results$combined_scores), " individuals x ",
        all_results$n_traits, " traits)\n\n", sep = "")

    # 2. Per-trait scores (individual CSVs)
    cat("[2/7] Per-trait PRS scores\n")
    for (trait_name in all_results$trait_names) {
        fname <- paste0("prs_scores_", tolower(trait_name), ".csv")
        fwrite(all_results$per_trait[[trait_name]], file.path(output_dir, fname))
        cat("  Saved:", file.path(output_dir, fname), "\n")
    }
    cat("\n")

    # 3. Correlation matrix
    cat("[3/7] PRS correlation matrix\n")
    cor_df <- as.data.frame(all_results$cor_matrix)
    cor_df$trait <- rownames(cor_df)
    cor_df <- cor_df[, c("trait", setdiff(names(cor_df), "trait"))]
    fwrite(cor_df, file.path(output_dir, "prs_correlation_matrix.csv"))
    cat("  Saved:", file.path(output_dir, "prs_correlation_matrix.csv"), "\n\n")

    # 4. Population-stratified summary statistics
    cat("[4/7] Population summary statistics\n")
    pop_summary <- .make_population_summary(all_results$combined_scores)
    if (!is.null(pop_summary)) {
        fwrite(pop_summary, file.path(output_dir, "population_summary.csv"))
        cat("  Saved:", file.path(output_dir, "population_summary.csv"), "\n\n")
    } else {
        cat("  Skipped (no population labels)\n\n")
    }

    # 5. Match reports (all traits)
    cat("[5/7] Variant match reports\n")
    match_combined <- do.call(rbind, lapply(names(all_results$match_reports), function(t) {
        mr <- all_results$match_reports[[t]]
        mr$trait <- t
        mr
    }))
    fwrite(match_combined, file.path(output_dir, "match_reports.csv"))
    cat("  Saved:", file.path(output_dir, "match_reports.csv"), "\n\n")

    # 6. Analysis object (RDS) — CRITICAL for downstream skills
    cat("[6/7] Analysis object (RDS)\n")
    analysis_obj <- list(
        pathway = "pgs_catalog_multi",
        combined_scores = all_results$combined_scores,
        per_trait = all_results$per_trait,
        cor_matrix = all_results$cor_matrix,
        match_reports = all_results$match_reports,
        snp_weights = all_results$snp_weights,
        trait_info = lapply(all_results$trait_weights, function(tw) {
            list(
                pgs_id = tw$pgs_id,
                trait_name = tw$trait_name,
                short_name = tw$short_name,
                score_name = tw$score_meta$name,
                variants_total = tw$score_meta$variants_number,
                publication = paste0(tw$score_meta$publication$firstauthor,
                                     " (", substr(tw$score_meta$publication$date_publication, 1, 4), ")")
            )
        }),
        parameters = list(
            method = "PGS Catalog (pre-computed weights)",
            n_traits = all_results$n_traits,
            trait_names = all_results$trait_names,
            n_individuals = all_results$n_individuals,
            reference_panel = "1000 Genomes Phase 3",
            genome_build = "GRCh37"
        )
    )
    saveRDS(analysis_obj, file.path(output_dir, "prs_analysis.rds"))
    cat("  Saved:", file.path(output_dir, "prs_analysis.rds"), "\n")
    cat("  (Load with: obj <- readRDS('prs_analysis.rds'))\n\n")

    # 7. Human-readable report
    cat("[7/7] Analysis report\n")
    report_lines <- c(
        "=== Multi-Trait Polygenic Risk Score Analysis Report ===",
        paste("Date:", Sys.time()),
        paste("Method: PGS Catalog (pre-computed weights)"),
        paste("Reference: 1000 Genomes Phase 3 (", all_results$n_individuals, " individuals)", sep = ""),
        ""
    )

    # Per-trait summary
    report_lines <- c(report_lines, "--- Trait Summary ---")
    for (t in all_results$trait_names) {
        tw <- all_results$trait_weights[[t]]
        mr <- all_results$match_reports[[t]]
        report_lines <- c(report_lines,
            paste0(t, ": ", tw$trait_name, " (", tw$pgs_id, ")"),
            paste0("  Matched: ", format(mr$n[2], big.mark = ","), "/",
                   format(mr$n[1], big.mark = ","), " (", mr$pct[2], "%)")
        )
    }

    report_lines <- c(report_lines, "",
        "--- Correlation Matrix ---",
        paste(capture.output(print(round(all_results$cor_matrix, 3))), collapse = "\n"),
        "",
        "--- Output Files ---",
        "combined_prs_scores.csv         All individuals x all traits (wide format)",
        "prs_scores_<trait>.csv          Per-trait individual scores",
        "prs_correlation_matrix.csv      Trait-trait PRS correlation",
        "population_summary.csv          Mean PRS by super-population per trait",
        "match_reports.csv               Variant matching summary per trait",
        "prs_analysis.rds                Complete analysis object (downstream use)",
        "distribution_<trait>.png/svg    PRS distribution histograms",
        "population_<trait>.png/svg      PRS by super-population boxplots",
        "dashboard_correlation_matrix.png/svg  Trait correlation heatmap",
        "dashboard_composite_risk.png/svg      Composite risk by population",
        "dashboard_population_heatmap.png/svg  Mean PRS x population x trait"
    )

    writeLines(report_lines, file.path(output_dir, "analysis_report.txt"))
    cat("  Saved:", file.path(output_dir, "analysis_report.txt"), "\n")

    cat("\n=== Export Complete ===\n")
    cat("All outputs saved to:", output_dir, "\n")
}

