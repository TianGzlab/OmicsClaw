###############################################################################
# load_pgs_weights.R — Search PGS Catalog and download scoring weights
#
# Functions:
#   search_pgs_catalog(trait)      — Search for available PGS scores by trait
#   download_pgs_weights(pgs_id)   — Download a single harmonized scoring file
#   get_demo_traits()              — Get cardiometabolic demo trait configuration
#   load_demo_weights(data_dir)    — Download all 5 cardiometabolic demo weights
###############################################################################

library(data.table)

if (!requireNamespace("jsonlite", quietly = TRUE)) {
    install.packages("jsonlite")
}

`%||%` <- function(a, b) if (!is.null(a)) a else b

# --- Search PGS Catalog ------------------------------------------------------

#' Search PGS Catalog for available scores by trait name
#' @param trait Character string (e.g. "coronary artery disease", "BMI", "LDL cholesterol")
#' @return data.frame of matching scores with id, name, trait, variants, method, publication
search_pgs_catalog <- function(trait) {
    cat("Searching PGS Catalog for '", trait, "'...\n", sep = "")

    trait_url <- paste0("https://www.pgscatalog.org/rest/trait/search?term=",
                        utils::URLencode(trait))
    trait_resp <- jsonlite::fromJSON(trait_url, flatten = TRUE)

    if (length(trait_resp$results) == 0) {
        cat("  No traits found matching '", trait, "'\n", sep = "")
        return(data.frame())
    }

    all_pgs_ids <- unique(unlist(trait_resp$results$associated_pgs_ids))
    if (length(all_pgs_ids) == 0) {
        cat("  Traits found but no associated PGS scores\n")
        return(data.frame())
    }

    cat("  Found", length(all_pgs_ids), "scores across",
        nrow(trait_resp$results), "matching traits\n\n")

    # Fetch details for top scores (limit to first 20 to avoid rate limiting)
    fetch_ids <- head(all_pgs_ids, 20)
    scores <- do.call(rbind, lapply(fetch_ids, function(pgs_id) {
        score_url <- paste0("https://www.pgscatalog.org/rest/score/", pgs_id)
        tryCatch({
            s <- jsonlite::fromJSON(score_url, flatten = TRUE)
            data.frame(
                pgs_id = s$id,
                name = s$name %||% NA_character_,
                trait = s$trait_reported %||% NA_character_,
                variants = s$variants_number %||% NA_integer_,
                method = s$method_name %||% NA_character_,
                genome_build = s$variants_genomebuild %||% NA_character_,
                publication = paste0(s$publication$firstauthor %||% "Unknown",
                                     " (", substr(s$publication$date_publication %||% "", 1, 4), ")"),
                stringsAsFactors = FALSE
            )
        }, error = function(e) NULL)
    }))

    if (is.null(scores) || nrow(scores) == 0) {
        cat("  Could not fetch score details\n")
        return(data.frame())
    }

    cat("  Available PGS scores:\n")
    cat("  ", paste(rep("-", 80), collapse = ""), "\n")
    for (i in seq_len(min(nrow(scores), 15))) {
        cat(sprintf("  %s | %s variants | %s | %s\n",
                    scores$pgs_id[i],
                    format(scores$variants[i], big.mark = ","),
                    scores$method[i] %||% "N/A",
                    scores$publication[i]))
    }
    if (nrow(scores) > 15) cat("  ... and", nrow(scores) - 15, "more\n")
    cat("  ", paste(rep("-", 80), collapse = ""), "\n\n")

    return(scores)
}

# --- Download single PGS scoring file ----------------------------------------

#' Download a harmonized PGS Catalog scoring file
#' @param pgs_id PGS Catalog ID (e.g. "PGS000018")
#' @param genome_build "GRCh37" or "GRCh38" (default: "GRCh37" for 1000G Phase 3)
#' @param data_dir Directory to store files (default: "data")
#' @return list with weights (data.frame), pgs_id, score_meta
download_pgs_weights <- function(pgs_id, genome_build = "GRCh37", data_dir = "data") {
    cat("  Downloading", pgs_id, "...\n")

    dir.create(data_dir, showWarnings = FALSE, recursive = TRUE)

    # Fetch score metadata
    score_url <- paste0("https://www.pgscatalog.org/rest/score/", pgs_id)
    score_meta <- jsonlite::fromJSON(score_url, flatten = TRUE)

    cat("    Score:", score_meta$name %||% pgs_id, "\n")
    cat("    Trait:", score_meta$trait_reported %||% "Unknown", "\n")
    cat("    Variants:", format(score_meta$variants_number %||% 0, big.mark = ","), "\n")

    # Download harmonized scoring file
    score_path <- file.path(data_dir, paste0(pgs_id, "_", genome_build, ".txt.gz"))

    if (!file.exists(score_path)) {
        hm_url <- paste0("https://ftp.ebi.ac.uk/pub/databases/spot/pgs/scores/",
                         pgs_id, "/ScoringFiles/Harmonized/",
                         pgs_id, "_hmPOS_", genome_build, ".txt.gz")

        cat("    Downloading harmonized scoring file...\n")

        old_timeout <- getOption("timeout")
        options(timeout = 600)
        on.exit(options(timeout = old_timeout), add = TRUE)

        tryCatch({
            download.file(hm_url, score_path, mode = "wb", quiet = TRUE)
            if (!file.exists(score_path) || file.size(score_path) < 100) {
                stop("Download produced empty file")
            }
        }, error = function(e) {
            stop("Failed to download ", pgs_id, " (", genome_build, "): ", conditionMessage(e),
                 "\n  Try: search_pgs_catalog() to find alternative score IDs")
        })
    } else {
        cat("    Scoring file already cached\n")
    }

    # Parse scoring file (skip # header lines)
    con <- gzfile(score_path)
    header_lines <- readLines(con, n = 50)
    close(con)
    skip_n <- sum(grepl("^#", header_lines))

    weights <- fread(score_path, skip = skip_n)

    # Standardize column names
    pgs_col_map <- c(
        "chr_name" = "chr", "hm_chr" = "chr",
        "chr_position" = "pos", "hm_pos" = "pos",
        "effect_allele" = "effect_allele",
        "other_allele" = "other_allele",
        "effect_weight" = "weight",
        "rsID" = "rsid", "hm_rsID" = "rsid",
        "allelefrequency_effect" = "eaf"
    )
    current <- names(weights)
    for (i in seq_along(current)) {
        if (current[i] %in% names(pgs_col_map)) {
            names(weights)[i] <- pgs_col_map[current[i]]
        }
    }

    # Filter valid rows
    weights <- weights[!is.na(chr) & !is.na(pos) & !is.na(weight)]
    weights$chr <- as.integer(weights$chr)
    weights$pos <- as.integer(weights$pos)
    weights$weight <- as.numeric(weights$weight)

    cat("    \u2713 Loaded", format(nrow(weights), big.mark = ","), "variant weights\n")

    return(list(
        weights = weights,
        pgs_id = pgs_id,
        score_meta = score_meta
    ))
}

# --- Demo trait configuration -------------------------------------------------

#' Get cardiometabolic demo trait configuration
#' @return list of trait definitions with name, short_name, pgs_id
get_demo_traits <- function() {
    list(
        list(name = "Coronary Artery Disease", short_name = "CAD", pgs_id = "PGS000018"),
        list(name = "Type 2 Diabetes",         short_name = "T2D", pgs_id = "PGS000014"),
        list(name = "LDL Cholesterol",         short_name = "LDL", pgs_id = "PGS000062"),
        list(name = "Body Mass Index",         short_name = "BMI", pgs_id = "PGS000027"),
        list(name = "Systolic Blood Pressure", short_name = "SBP", pgs_id = "PGS000299")
    )
}

# --- Load all demo weights ----------------------------------------------------

#' Download PGS Catalog weights for all 5 cardiometabolic demo traits
#' @param data_dir Directory to store files (default: "data")
#' @return Named list of weight data (keyed by short_name)
load_demo_weights <- function(data_dir = "data") {
    cat("=== Loading PGS Catalog Weights for Cardiometabolic Traits ===\n\n")

    traits <- get_demo_traits()
    trait_weights <- list()
    failed <- character(0)

    for (trait in traits) {
        cat("[", trait$short_name, "]", trait$name, "(", trait$pgs_id, ")\n")
        tryCatch({
            result <- download_pgs_weights(trait$pgs_id, data_dir = data_dir)
            trait_weights[[trait$short_name]] <- list(
                weights = result$weights,
                pgs_id = result$pgs_id,
                score_meta = result$score_meta,
                trait_name = trait$name,
                short_name = trait$short_name
            )
        }, error = function(e) {
            cat("    \u2716 FAILED:", conditionMessage(e), "\n")
            cat("    Use search_pgs_catalog('", trait$name,
                "') to find alternative PGS IDs\n", sep = "")
            failed <<- c(failed, trait$short_name)
        })
        cat("\n")
    }

    n_loaded <- length(trait_weights)
    n_failed <- length(failed)

    cat("\u2713 PGS Catalog weights loaded: ", n_loaded, "/", n_loaded + n_failed, " traits\n", sep = "")
    if (n_failed > 0) {
        cat("\u2716 Failed traits: ", paste(failed, collapse = ", "), "\n")
        cat("  Use search_pgs_catalog() to find alternative PGS IDs for failed traits\n")
    }

    return(trait_weights)
}

