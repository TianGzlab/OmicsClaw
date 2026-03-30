###############################################################################
# load_reference_data.R — Download 1000 Genomes Phase 3 reference genotypes
#
# Functions:
#   load_reference_data(data_dir) — Master: download genotypes + population labels
#
# Returns: list(obj_bigsnp, pop_labels, data_dir)
# Target: ALL 2,490 individuals across 5 super-populations (AFR, AMR, EAS, EUR, SAS)
###############################################################################

`%||%` <- function(a, b) if (!is.null(a)) a else b

# --- Package management ------------------------------------------------------

.ensure_packages <- function() {
    if (length(getOption("repos")) == 0 || getOption("repos")["CRAN"] == "@CRAN@") {
        options(repos = c(CRAN = "https://cloud.r-project.org"))
    }

    if (!requireNamespace("bigsnpr", quietly = TRUE)) {
        cat("Installing bigsnpr (this may take a few minutes)...\n")
        if (!requireNamespace("remotes", quietly = TRUE)) install.packages("remotes")
        remotes::install_github("privefl/bigsnpr")
    }

    required_cran <- c("data.table", "R.utils", "dplyr", "jsonlite")
    for (pkg in required_cran) {
        if (!requireNamespace(pkg, quietly = TRUE)) {
            cat("Installing", pkg, "...\n")
            install.packages(pkg)
        }
    }

    library(bigsnpr)
    library(bigstatsr)
    library(data.table)
    library(dplyr)
    cat("\u2713 All required packages loaded\n")
}

# --- Reference genotype download ----------------------------------------------

.download_reference_genotypes <- function(data_dir = "data") {
    bed_prefix <- file.path(data_dir, "1000G_phase3")
    rds_path <- paste0(bed_prefix, ".rds")

    if (file.exists(rds_path)) {
        cat("  1000 Genomes Phase 3 genotypes already downloaded\n")
        return(bed_prefix)
    }

    bed_path <- paste0(bed_prefix, ".bed")
    if (file.exists(bed_path)) {
        cat("  PLINK files found, converting to bigsnpr format...\n")
        snp_readBed(bed_path)
        cat("  \u2713 1000 Genomes genotypes ready\n")
        return(bed_prefix)
    }

    # Check for any existing 1000G download with different naming
    existing <- list.files(data_dir, pattern = "1000G.*\\.bed$", full.names = TRUE)
    if (length(existing) > 0) {
        base <- tools::file_path_sans_ext(existing[1])
        cat("  Found existing 1000G download, linking...\n")
        for (ext in c(".bed", ".bim", ".fam")) {
            src <- paste0(base, ext)
            dst <- paste0(bed_prefix, ext)
            if (file.exists(src) && !file.exists(dst)) file.copy(src, dst)
        }
        if (file.exists(paste0(bed_prefix, ".bed"))) {
            snp_readBed(paste0(bed_prefix, ".bed"))
            cat("  \u2713 1000 Genomes genotypes ready\n")
            return(bed_prefix)
        }
    }

    cat("  Downloading 1000 Genomes Phase 3 genotypes...\n")
    cat("  2,490 individuals from 26 populations (5 super-populations)\n")
    cat("  This may take 5-10 minutes...\n")

    old_timeout <- getOption("timeout")
    options(timeout = 900)
    on.exit(options(timeout = old_timeout), add = TRUE)

    tryCatch({
        bigsnpr::download_1000G(data_dir)

        # Rename to consistent name
        plink_files <- list.files(data_dir, pattern = "\\.bed$", full.names = TRUE)
        if (length(plink_files) > 0) {
            base <- tools::file_path_sans_ext(plink_files[1])
            for (ext in c(".bed", ".bim", ".fam")) {
                src <- paste0(base, ext)
                dst <- paste0(bed_prefix, ext)
                if (file.exists(src) && !file.exists(dst)) file.rename(src, dst)
            }
        }

        snp_readBed(paste0(bed_prefix, ".bed"))
        cat("  \u2713 1000 Genomes genotypes ready\n")
    }, error = function(e) {
        cat("  Note: bigsnpr::download_1000G() failed.\n")
        cat("  You can manually provide PLINK files (.bed/.bim/.fam) in data/\n")
        cat("  Error:", conditionMessage(e), "\n")
        stop("Reference genotype download failed. See above for details.")
    })

    return(bed_prefix)
}

# --- Population labels --------------------------------------------------------

.get_population_labels <- function(fam_path) {
    pop_url <- "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502/integrated_call_samples_v3.20130502.ALL.panel"

    old_timeout <- getOption("timeout")
    options(timeout = 120)
    on.exit(options(timeout = old_timeout), add = TRUE)

    tryCatch({
        panel <- fread(pop_url, fill = TRUE, header = FALSE)
        if (ncol(panel) >= 4) {
            panel <- panel[, 1:4]
            setnames(panel, c("sample", "pop", "super_pop", "gender"))
            panel <- panel[sample != "sample"]
        } else {
            stop("Unexpected panel format")
        }

        fam <- fread(fam_path, header = FALSE)
        setnames(fam, c("FID", "IID", "PAT", "MAT", "SEX", "PHENO"))

        pop_labels <- merge(
            fam[, .(IID)],
            panel[, .(IID = sample, population = pop, super_population = super_pop)],
            by = "IID", all.x = TRUE
        )

        n_labeled <- sum(!is.na(pop_labels$population))
        n_pops <- length(unique(pop_labels$population[!is.na(pop_labels$population)]))
        n_super <- length(unique(pop_labels$super_population[!is.na(pop_labels$super_population)]))
        cat("  Population labels:", n_labeled, "individuals from",
            n_pops, "populations (", n_super, "super-populations)\n")
        return(pop_labels)
    }, error = function(e) {
        cat("  Note: Could not download population labels (non-critical)\n")
        cat("  Error:", conditionMessage(e), "\n")
        return(NULL)
    })
}

# --- Master function ----------------------------------------------------------

#' Load 1000 Genomes Phase 3 reference data for PRS scoring
#' @param data_dir Directory to store downloaded files (default: "data")
#' @return list with obj_bigsnp, pop_labels, data_dir
load_reference_data <- function(data_dir = "data") {
    cat("=== Loading 1000 Genomes Phase 3 Reference Data ===\n\n")

    .ensure_packages()
    dir.create(data_dir, showWarnings = FALSE, recursive = TRUE)

    # Step 1: Reference genotypes
    cat("[1/2] Reference Genotypes\n")
    geno_prefix <- .download_reference_genotypes(data_dir)

    # Step 2: Population labels
    cat("\n[2/2] Population Labels\n")
    fam_path <- paste0(geno_prefix, ".fam")
    pop_labels <- .get_population_labels(fam_path)

    # Load genotype data
    rds_path <- paste0(geno_prefix, ".rds")
    obj_bigsnp <- snp_attach(rds_path)
    n_samples <- nrow(obj_bigsnp$fam)
    n_variants <- ncol(obj_bigsnp$genotypes)

    result <- list(
        obj_bigsnp = obj_bigsnp,
        pop_labels = pop_labels,
        geno_prefix = geno_prefix,
        data_dir = data_dir
    )

    cat("\n\u2713 Reference data loaded successfully (",
        format(n_variants, big.mark = ","), " variants, ",
        n_samples, " individuals)\n", sep = "")
    cat("  Target: 1000 Genomes Phase 3 (", n_samples, " individuals, 5 super-populations)\n", sep = "")

    return(result)
}

