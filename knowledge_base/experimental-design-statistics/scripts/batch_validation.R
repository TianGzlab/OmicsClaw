# Batch Design Validation Functions
# Validate batch assignments to prevent confounding and check balance

#' Internal helper to save plots in both PNG and SVG formats
#' @param plot ggplot object
#' @param base_path Base file path (extension will be replaced)
#' @param width Plot width in inches
#' @param height Plot height in inches
#' @param dpi Resolution for PNG
.save_plot <- function(plot, base_path, width = 8, height = 6, dpi = 300) {
  # Always save PNG
  png_path <- sub("\\.(svg|png)$", ".png", base_path)
  ggplot2::ggsave(png_path, plot = plot, width = width, height = height, dpi = dpi, device = "png")
  cat("   Saved:", png_path, "\n")

  # Always try SVG - try ggsave first, fall back to svg() device
  svg_path <- sub("\\.(svg|png)$", ".svg", base_path)
  tryCatch({
    ggplot2::ggsave(svg_path, plot = plot, width = width, height = height, device = "svg")
    cat("   Saved:", svg_path, "\n")
  }, error = function(e) {
    # If ggsave fails, try base R svg() device directly
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

#' Check for confounding between batch and condition
#'
#' @param batch_assignment Data frame with batch assignments
#' @param condition_var Name of condition variable column
#' @param batch_var Name of batch variable column (default: "batch")
#' @return List with test results and interpretation
#' @export
#' @examples
#' # Check if batch is confounded with condition
#' # confounding_check <- check_confounding(batch_design, "condition")
check_confounding <- function(batch_assignment,
                              condition_var,
                              batch_var = "batch") {

  # Validate inputs
  if (!condition_var %in% colnames(batch_assignment)) {
    stop(paste0("Condition variable '", condition_var, "' not found in data"))
  }

  if (!batch_var %in% colnames(batch_assignment)) {
    stop(paste0("Batch variable '", batch_var, "' not found in data"))
  }

  # Create contingency table
  cont_table <- table(batch_assignment[[batch_var]], batch_assignment[[condition_var]])

  # Perform chi-square test
  chi_test <- chisq.test(cont_table)

  # Interpretation
  is_confounded <- chi_test$p.value < 0.05

  if (is_confounded) {
    result_message <- paste0(
      "WARNING: Batch is CONFOUNDED with ", condition_var, "!\n",
      "Chi-square test p-value: ", format(chi_test$p.value, digits = 4), " < 0.05\n",
      "This design will not allow separation of batch effects from biological effects.\n",
      "RECOMMENDATION: Regenerate batch assignment."
    )
    status <- "FAILED"
  } else {
    result_message <- paste0(
      "PASS: No confounding detected between batch and ", condition_var, "\n",
      "Chi-square test p-value: ", format(chi_test$p.value, digits = 4), " > 0.05\n",
      "Batch effects can be separated from biological effects."
    )
    status <- "PASSED"
  }

  result <- list(
    status = status,
    is_confounded = is_confounded,
    p_value = chi_test$p.value,
    contingency_table = cont_table,
    message = result_message,
    test = chi_test
  )

  # Print message
  cat(result_message, "\n")

  return(result)
}


#' Check balance of covariates across batches
#'
#' @param batch_assignment Data frame with batch assignments
#' @param covariates Vector of covariate column names to check
#' @param batch_var Name of batch variable column (default: "batch")
#' @return Data frame with balance statistics for each covariate
#' @export
#' @examples
#' # Check balance of sex and age across batches
#' # balance_check <- check_balance(batch_design, c("sex", "age_group"))
check_balance <- function(batch_assignment,
                         covariates,
                         batch_var = "batch") {

  if (!batch_var %in% colnames(batch_assignment)) {
    stop(paste0("Batch variable '", batch_var, "' not found in data"))
  }

  missing_covars <- covariates[!covariates %in% colnames(batch_assignment)]
  if (length(missing_covars) > 0) {
    stop(paste0("Covariates not found: ", paste(missing_covars, collapse = ", ")))
  }

  # Check balance for each covariate
  balance_results <- data.frame(
    covariate = character(),
    chi_square_p = numeric(),
    is_balanced = logical(),
    interpretation = character(),
    stringsAsFactors = FALSE
  )

  for (covar in covariates) {
    # Create contingency table
    cont_table <- table(batch_assignment[[batch_var]], batch_assignment[[covar]])

    # Chi-square test
    chi_test <- chisq.test(cont_table)

    # Interpret balance (less stringent than confounding check)
    is_balanced <- chi_test$p.value > 0.05

    if (is_balanced) {
      interpretation <- "Well balanced"
    } else if (chi_test$p.value > 0.01) {
      interpretation <- "Moderately balanced"
    } else {
      interpretation <- "Poorly balanced - consider regenerating"
    }

    balance_results <- rbind(balance_results, data.frame(
      covariate = covar,
      chi_square_p = chi_test$p.value,
      is_balanced = is_balanced,
      interpretation = interpretation,
      stringsAsFactors = FALSE
    ))
  }

  # Print summary
  cat("\nCovariate Balance Summary:\n")
  cat("==========================\n")
  for (i in 1:nrow(balance_results)) {
    cat(sprintf("%s: %s (p = %.4f)\n",
                balance_results$covariate[i],
                balance_results$interpretation[i],
                balance_results$chi_square_p[i]))
  }

  return(balance_results)
}


#' Visualize batch design
#'
#' @param batch_assignment Data frame with batch assignments
#' @param condition_var Name of condition variable
#' @param batch_var Name of batch variable (default: "batch")
#' @param output_file Output file path (default: NULL, displays plot)
#' @export
visualize_batch_design <- function(batch_assignment,
                                   condition_var,
                                   batch_var = "batch",
                                   output_file = NULL) {

  if (!requireNamespace("ggplot2", quietly = TRUE) || !requireNamespace("ggprism", quietly = TRUE)) {
    stop("Packages 'ggplot2' and 'ggprism' are required for visualization.")
  }

  # Create summary table
  summary_table <- as.data.frame(table(
    Batch = batch_assignment[[batch_var]],
    Condition = batch_assignment[[condition_var]]
  ))

  # Create plot
  p <- ggplot2::ggplot(summary_table, ggplot2::aes(x = Batch, y = Freq, fill = Condition)) +
    ggplot2::geom_bar(stat = "identity", position = "dodge") +
    ggprism::theme_prism() +
    ggplot2::labs(
      title = "Batch Design: Samples per Batch by Condition",
      x = "Batch",
      y = "Number of Samples",
      fill = "Condition"
    ) +
    ggplot2::theme(
      legend.position = "right",
      plot.title = ggplot2::element_text(hjust = 0.5, face = "bold")
    )

  # Save or display
  if (!is.null(output_file)) {
    message("Saving batch design plots:")
    .save_plot(p, output_file, width = 8, height = 6, dpi = 300)
  } else {
    print(p)
  }

  return(p)
}


#' Generate comprehensive batch validation report
#'
#' @param batch_assignment Data frame with batch assignments
#' @param condition_var Name of condition variable
#' @param covariates Vector of covariate names (optional)
#' @param output_file Optional file to save report (markdown format)
#' @return List with all validation results
#' @export
generate_batch_report <- function(batch_assignment,
                                  condition_var,
                                  covariates = NULL,
                                  output_file = NULL) {

  report <- list()

  # 1. Confounding check (CRITICAL)
  cat("\n=== CRITICAL: Confounding Check ===\n")
  report$confounding <- check_confounding(batch_assignment, condition_var)

  # 2. Balance checks
  if (!is.null(covariates)) {
    cat("\n\n=== Covariate Balance Checks ===\n")
    report$balance <- check_balance(batch_assignment, covariates)
  }

  # 3. Sample size summary
  cat("\n\n=== Sample Size Summary ===\n")
  report$sample_summary <- as.data.frame(table(
    Batch = batch_assignment$batch,
    Condition = batch_assignment[[condition_var]]
  ))
  print(report$sample_summary)

  # 4. Overall summary
  cat("\n\n=== Overall Assessment ===\n")
  if (report$confounding$status == "PASSED") {
    cat("✓ PASS: Design is valid (no confounding detected)\n")

    if (!is.null(covariates)) {
      all_balanced <- all(report$balance$is_balanced)
      if (all_balanced) {
        cat("✓ All covariates are well balanced\n")
      } else {
        poorly_balanced <- report$balance$covariate[!report$balance$is_balanced]
        cat("⚠ Some covariates poorly balanced:", paste(poorly_balanced, collapse = ", "), "\n")
        cat("  Consider: (1) regenerating assignment, or (2) including as covariates in analysis\n")
      }
    }
  } else {
    cat("✗ FAIL: Design has confounding - DO NOT USE\n")
    cat("  MUST regenerate batch assignment\n")
  }

  # Save report if requested
  if (!is.null(output_file)) {
    sink(output_file)
    cat("# Batch Design Validation Report\n\n")
    cat("Generated:", format(Sys.time(), "%Y-%m-%d %H:%M:%S"), "\n\n")
    cat("## Confounding Check\n")
    cat(report$confounding$message, "\n\n")
    if (!is.null(covariates)) {
      cat("## Covariate Balance\n")
      print(report$balance)
    }
    sink()
    message(paste0("Report saved to: ", output_file))
  }

  return(report)
}


#' Check for recommended metadata to record
#'
#' @param batch_assignment Data frame with batch assignments
#' @return List of recommended metadata fields and which are present
#' @export
check_metadata_completeness <- function(batch_assignment) {

  # Recommended metadata fields to always record
  recommended_fields <- c(
    "sample_id",
    "batch",
    "processing_date",
    "operator",
    "reagent_lot",
    "instrument",
    "plate",
    "well",
    "library_prep_batch",
    "sequencing_run",
    "flowcell"
  )

  # Check which are present
  present_fields <- recommended_fields[recommended_fields %in% colnames(batch_assignment)]
  missing_fields <- recommended_fields[!recommended_fields %in% colnames(batch_assignment)]

  cat("\n=== Metadata Completeness Check ===\n")
  cat("Present fields (", length(present_fields), "/", length(recommended_fields), "):\n", sep = "")
  cat("  ", paste(present_fields, collapse = ", "), "\n\n")

  if (length(missing_fields) > 0) {
    cat("Missing recommended fields:\n")
    cat("  ", paste(missing_fields, collapse = ", "), "\n\n")
    cat("RECOMMENDATION: Record these fields during sample processing\n")
    cat("They are essential for:\n")
    cat("  1. Diagnosing batch effects if detected\n")
    cat("  2. Batch effect correction (SVA, ComBat)\n")
    cat("  3. Reproducibility and troubleshooting\n")
  } else {
    cat("✓ All recommended metadata fields present\n")
  }

  result <- list(
    present = present_fields,
    missing = missing_fields,
    completeness = length(present_fields) / length(recommended_fields)
  )

  return(result)
}

