# =============================================================================
# MOFA+ Multi-Omics Factor Analysis Workflow
# =============================================================================
# Creates a MOFA object from multi-omics data, configures model/training
# options, and trains the model. Returns a trained MOFA model object.
# =============================================================================

options(repos = c(CRAN = "https://cloud.r-project.org"))

.install_if_missing <- function(pkg, bioc = FALSE) {
    if (!requireNamespace(pkg, quietly = TRUE)) {
        cat("Installing", pkg, "...\n")
        if (bioc) {
            if (!requireNamespace("BiocManager", quietly = TRUE))
                install.packages("BiocManager")
            BiocManager::install(pkg, ask = FALSE, update = FALSE)
        } else {
            install.packages(pkg)
        }
    }
}

#' Run MOFA+ multi-omics factor analysis
#'
#' @param data_list Named list of matrices (features x samples per view)
#' @param metadata Optional data.frame of sample annotations
#' @param n_factors Number of latent factors to infer (default: 15)
#' @param likelihoods Named vector of likelihoods per view.
#'   Auto-detected if NULL: "bernoulli" for binary, "gaussian" otherwise.
#' @param convergence_mode "fast", "medium", or "slow" (default: "slow")
#' @param seed Random seed for reproducibility
#' @param scale_views Scale views to unit variance (recommended for mixed omics)
#' @param output_dir Directory for model HDF5 file
#' @return Trained MOFA model object
run_mofa_analysis <- function(data_list,
                               metadata = NULL,
                               n_factors = 15,
                               likelihoods = NULL,
                               convergence_mode = "slow",
                               seed = 42,
                               scale_views = TRUE,
                               output_dir = "mofa_results") {

    cat("\n=== Running MOFA+ Multi-Omics Factor Analysis ===\n\n")

    # --- Setup ---
    .install_if_missing("MOFA2", bioc = TRUE)
    library(MOFA2)

    if (!dir.exists(output_dir)) {
        dir.create(output_dir, recursive = TRUE)
    }

    # --- Auto-detect likelihoods ---
    if (is.null(likelihoods)) {
        likelihoods <- sapply(data_list, function(mat) {
            vals <- as.vector(mat[!is.na(mat)])
            if (all(vals %in% c(0, 1))) {
                "bernoulli"
            } else {
                "gaussian"
            }
        })
        cat("Auto-detected likelihoods:\n")
        for (v in names(likelihoods)) {
            cat(sprintf("  %-15s -> %s\n", v, likelihoods[v]))
        }
        cat("\n")
    }

    # --- Create MOFA object ---
    cat("Creating MOFA object...\n")
    mofa_obj <- create_mofa(data_list)
    cat(sprintf("  Views: %s\n", paste(views_names(mofa_obj), collapse = ", ")))
    cat(sprintf("  Samples: %d\n", sum(mofa_obj@dimensions$N)))
    cat(sprintf("  Features per view: %s\n",
                paste(mofa_obj@dimensions$D, collapse = ", ")))

    # --- Configure options ---
    cat("\nConfiguring data options...\n")
    data_opts <- get_default_data_options(mofa_obj)
    data_opts$scale_views <- scale_views
    cat(sprintf("  scale_views: %s\n", scale_views))

    cat("Configuring model options...\n")
    model_opts <- get_default_model_options(mofa_obj)
    model_opts$num_factors <- n_factors
    model_opts$likelihoods <- likelihoods
    cat(sprintf("  num_factors: %d\n", n_factors))

    cat("Configuring training options...\n")
    train_opts <- get_default_training_options(mofa_obj)
    train_opts$convergence_mode <- convergence_mode
    train_opts$seed <- seed
    train_opts$maxiter <- 1000
    train_opts$verbose <- FALSE
    cat(sprintf("  convergence_mode: %s\n", convergence_mode))

    # --- Prepare MOFA object (applies all options) ---
    mofa_obj <- prepare_mofa(mofa_obj,
                             data_options = data_opts,
                             model_options = model_opts,
                             training_options = train_opts)
    cat(sprintf("  seed: %d\n", seed))
    cat(sprintf("  maxiter: %d\n", train_opts$maxiter))

    # --- Train model ---
    outfile <- file.path(output_dir, "mofa_model.hdf5")
    cat(sprintf("\nTraining MOFA model (this may take 2-5 minutes)...\n"))
    cat("  (First run also sets up Python environment via basilisk, ~1-3 min extra)\n\n")

    model <- run_mofa(mofa_obj, outfile = outfile, use_basilisk = TRUE)

    # --- Add metadata ---
    if (!is.null(metadata)) {
        cat("Adding sample metadata...\n")
        tryCatch({
            # Align metadata to model samples
            model_samples <- unlist(samples_names(model))
            common <- intersect(model_samples, rownames(metadata))
            if (length(common) > 0) {
                meta_aligned <- metadata[common, , drop = FALSE]
                meta_aligned$sample <- common
                meta_aligned$group <- "group1"
                samples_metadata(model) <- meta_aligned
                cat(sprintf("  Metadata attached for %d / %d samples\n",
                            length(common), length(model_samples)))
            } else {
                cat("  Warning: No sample overlap between metadata and model.\n")
            }
        }, error = function(e) {
            cat(sprintf("  Warning: Could not attach metadata: %s\n", e$message))
        })
    }

    # --- Print variance explained summary ---
    cat("\n--- Variance Explained Summary ---\n")
    r2 <- get_variance_explained(model)
    r2_per_factor <- r2$r2_per_factor[[1]]  # group 1
    r2_total <- r2$r2_total[[1]]

    cat("\nTotal variance explained per view:\n")
    for (v in names(r2_total)) {
        cat(sprintf("  %-15s %5.1f%%\n", v, r2_total[v]))
    }

    cat(sprintf("\nActive factors (R² > 1%% in any view): %d / %d\n",
                sum(apply(r2_per_factor, 1, max) > 1), nrow(r2_per_factor)))

    # Store parameters in model for export
    model@cache[["analysis_params"]] <- list(
        n_factors = n_factors,
        convergence_mode = convergence_mode,
        seed = seed,
        scale_views = scale_views,
        likelihoods = likelihoods,
        output_dir = output_dir
    )

    cat("\n✓ MOFA model trained successfully!\n\n")
    return(model)
}

