###############################################################################
# score_traits.R — Score individuals using PGS Catalog weights
#
# Expects in environment:
#   ref_data      — from load_reference_data()
#   trait_weights  — from load_demo_weights() or manual download_pgs_weights()
#
# Creates in environment:
#   all_results   — list with per-trait scores, combined scores, match reports
###############################################################################

cat("=== Multi-Trait PRS Scoring ===\n\n")

# --- Validate inputs ----------------------------------------------------------

if (!exists("ref_data") || !is.list(ref_data)) {
    stop("'ref_data' not found. Run load_reference_data() first:\n",
         "  source('scripts/load_reference_data.R')\n",
         "  ref_data <- load_reference_data()")
}

if (!exists("trait_weights") || !is.list(trait_weights) || length(trait_weights) == 0) {
    stop("'trait_weights' not found. Run load_demo_weights() first:\n",
         "  source('scripts/load_pgs_weights.R')\n",
         "  trait_weights <- load_demo_weights()")
}

library(bigsnpr)
library(bigstatsr)
library(data.table)
library(dplyr)

obj_bigsnp <- ref_data$obj_bigsnp
pop_labels <- ref_data$pop_labels
G <- obj_bigsnp$genotypes
fam <- obj_bigsnp$fam
map <- obj_bigsnp$map
n_samples <- nrow(fam)

cat("  Reference panel:", n_samples, "individuals\n")
cat("  Traits to score:", length(trait_weights), "\n")
cat("  Traits:", paste(names(trait_weights), collapse = ", "), "\n\n")

# --- Helper: match and score a single trait -----------------------------------

.match_and_score <- function(weights_data, obj_bigsnp, pop_labels) {
    weights <- weights_data$weights
    map <- obj_bigsnp$map
    G <- obj_bigsnp$genotypes
    fam <- obj_bigsnp$fam

    # Prepare reference map
    map_df <- data.frame(
        chr = as.integer(map$chromosome),
        pos = as.integer(map$physical.pos),
        a0 = map$allele2,
        a1 = map$allele1,
        map_idx = seq_len(nrow(map)),
        stringsAsFactors = FALSE
    )

    # Prepare weights
    weights_match <- data.frame(
        chr = weights$chr,
        pos = weights$pos,
        a1 = toupper(weights$effect_allele),
        a0 = if ("other_allele" %in% names(weights)) toupper(weights$other_allele) else NA_character_,
        weight = weights$weight,
        stringsAsFactors = FALSE
    )
    if ("rsid" %in% names(weights)) weights_match$rsid <- weights$rsid

    # Match by chr:pos
    merged <- merge(weights_match, map_df, by = c("chr", "pos"),
                    suffixes = c("_wt", "_ref"), allow.cartesian = FALSE)

    if (nrow(merged) > 0) {
        direct <- toupper(merged$a1_wt) == toupper(merged$a1_ref)
        flipped <- toupper(merged$a1_wt) == toupper(merged$a0_ref)
        merged$weight_aligned <- merged$weight
        merged$weight_aligned[flipped] <- -merged$weight[flipped]
        matched <- merged[direct | flipped, ]
        matched <- matched[!duplicated(matched$map_idx), ]
    } else {
        matched <- merged
    }

    n_input <- nrow(weights)
    n_matched <- nrow(matched)
    match_rate <- round(100 * n_matched / n_input, 1)

    # Score
    prs_raw <- big_prodVec(G, matched$weight_aligned, ind.col = matched$map_idx)
    prs_z <- (prs_raw - mean(prs_raw)) / sd(prs_raw)

    scores <- data.frame(
        FID = fam$family.ID,
        IID = fam$sample.ID,
        prs_raw = prs_raw,
        prs_zscore = prs_z,
        prs_percentile = rank(prs_z) / length(prs_z) * 100,
        stringsAsFactors = FALSE
    )

    if (!is.null(pop_labels)) {
        scores <- merge(scores, pop_labels, by = "IID", all.x = TRUE)
    }

    match_report <- data.frame(
        step = c("Input weights", "Matched to genotypes", "Unmatched"),
        n = c(n_input, n_matched, n_input - n_matched),
        pct = c(100, match_rate, round(100 - match_rate, 1))
    )

    snp_weights_out <- data.frame(
        chr = matched$chr,
        pos = matched$pos,
        a1 = matched$a1_wt,
        a0 = matched$a0_ref,
        weight_original = matched$weight,
        weight_aligned = matched$weight_aligned
    )
    if ("rsid" %in% names(matched)) snp_weights_out$rsid <- matched$rsid

    list(scores = scores, match_report = match_report, snp_weights = snp_weights_out)
}

# --- Score all traits ---------------------------------------------------------

per_trait <- list()
match_reports <- list()
snp_weights_all <- list()

for (trait_name in names(trait_weights)) {
    tw <- trait_weights[[trait_name]]
    cat("[", trait_name, "] Scoring", tw$trait_name, "(", tw$pgs_id, ")\n")

    result <- .match_and_score(tw, obj_bigsnp, pop_labels)

    mr <- result$match_report
    cat("  Matched:", format(mr$n[2], big.mark = ","), "/",
        format(mr$n[1], big.mark = ","), "weights (", mr$pct[2], "%)\n")
    cat("  PRS range: z =", round(min(result$scores$prs_zscore), 2),
        "to", round(max(result$scores$prs_zscore), 2), "\n")

    per_trait[[trait_name]] <- result$scores
    match_reports[[trait_name]] <- result$match_report
    snp_weights_all[[trait_name]] <- result$snp_weights

    # Population summary
    if ("super_population" %in% names(result$scores)) {
        pop_sum <- result$scores %>%
            group_by(super_population) %>%
            summarise(n = n(), mean_z = round(mean(prs_zscore), 3), .groups = "drop") %>%
            arrange(desc(mean_z))
        cat("  Population means (super-pop):\n")
        for (r in seq_len(nrow(pop_sum))) {
            cat("    ", pop_sum$super_population[r], ": z =",
                sprintf("%+.3f", pop_sum$mean_z[r]),
                "(n =", pop_sum$n[r], ")\n")
        }
    }
    cat("\n")
}

# --- Build combined scores matrix ---------------------------------------------

cat("=== Building Combined Scores ===\n\n")

# Create wide-format combined scores
base_df <- per_trait[[1]][, c("IID", "FID")]
if ("population" %in% names(per_trait[[1]])) base_df$population <- per_trait[[1]]$population
if ("super_population" %in% names(per_trait[[1]])) base_df$super_population <- per_trait[[1]]$super_population

for (trait_name in names(per_trait)) {
    col_name <- paste0("prs_", trait_name)
    base_df[[col_name]] <- per_trait[[trait_name]]$prs_zscore[
        match(base_df$IID, per_trait[[trait_name]]$IID)]
}

# Composite risk: mean z-score across all traits
prs_cols <- grep("^prs_", names(base_df), value = TRUE)
base_df$composite_risk <- rowMeans(base_df[, prs_cols, drop = FALSE], na.rm = TRUE)
base_df$composite_percentile <- rank(base_df$composite_risk) / nrow(base_df) * 100

combined_scores <- base_df

# Correlation matrix
prs_matrix <- as.matrix(combined_scores[, prs_cols])
colnames(prs_matrix) <- sub("^prs_", "", colnames(prs_matrix))
cor_matrix <- cor(prs_matrix, use = "pairwise.complete.obs")

cat("  Combined scores for", nrow(combined_scores), "individuals across",
    length(prs_cols), "traits\n")
cat("  Composite risk range: z =", round(min(combined_scores$composite_risk), 2),
    "to", round(max(combined_scores$composite_risk), 2), "\n\n")

cat("  PRS Correlation Matrix:\n")
print(round(cor_matrix, 3))

# --- Build all_results --------------------------------------------------------

all_results <- list(
    per_trait = per_trait,
    combined_scores = combined_scores,
    cor_matrix = cor_matrix,
    match_reports = match_reports,
    snp_weights = snp_weights_all,
    trait_weights = trait_weights,
    n_traits = length(per_trait),
    n_individuals = nrow(combined_scores),
    trait_names = names(per_trait)
)

cat("\n\u2713 Multi-trait PRS scoring completed successfully! (",
    length(per_trait), " traits, ", nrow(combined_scores), " individuals)\n", sep = "")

