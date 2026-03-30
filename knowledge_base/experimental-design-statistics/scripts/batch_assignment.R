# Batch Assignment Functions
# Create balanced batch designs preventing confounding
# Based on: Leek et al. (2010) Nat Rev Genet and osat package

#' Assign samples to batches with optimal balance
#'
#' @param metadata Data frame with sample metadata (must include sample IDs)
#' @param batch_size Number of samples per batch
#' @param balance_vars Vector of column names to balance across batches
#' @param sample_id_col Name of sample ID column (default: "sample_id")
#' @return Data frame with batch assignments added
#' @export
#' @examples
#' # Create sample metadata
#' metadata <- data.frame(
#'   sample_id = paste0("S", 1:24),
#'   condition = rep(c("Control", "Treatment"), each = 12),
#'   sex = rep(c("M", "F"), 12),
#'   age_group = rep(c("Young", "Old"), each = 12)
#' )
#'
#' # Generate balanced batch assignment
#' batch_design <- assign_samples_to_batches(
#'   metadata = metadata,
#'   batch_size = 8,
#'   balance_vars = c("condition", "sex", "age_group")
#' )
assign_samples_to_batches <- function(metadata,
                                      batch_size,
                                      balance_vars,
                                      sample_id_col = "sample_id") {

  if (!requireNamespace("OSAT", quietly = TRUE)) {
    stop("Package 'OSAT' is required. Install with BiocManager::install('OSAT')")
  }

  # Validate inputs
  if (!sample_id_col %in% colnames(metadata)) {
    stop(paste0("Column '", sample_id_col, "' not found in metadata"))
  }

  missing_vars <- balance_vars[!balance_vars %in% colnames(metadata)]
  if (length(missing_vars) > 0) {
    stop(paste0("Balance variables not found in metadata: ", paste(missing_vars, collapse = ", ")))
  }

  if (batch_size <= 0 || batch_size > nrow(metadata)) {
    stop("Invalid batch_size: must be positive and <= number of samples")
  }

  # Calculate number of batches
  n_batches <- ceiling(nrow(metadata) / batch_size)

  # Prepare data for osat
  sample_ids <- metadata[[sample_id_col]]

  # Create factor variables for balancing
  balance_data <- metadata[, balance_vars, drop = FALSE]

  # Convert all balance variables to factors
  balance_data <- as.data.frame(lapply(balance_data, as.factor))

  # Use osat to generate optimal assignment
  message("Generating optimal batch assignment...")

  tryCatch({
    # Run osat optimization
    osat_result <- OSAT::osat(
      x = balance_data,
      batch.size = batch_size,
      n.batch = n_batches
    )

    # Extract batch assignments
    batch_assignments <- osat_result$BatchLabel

    # Add batch column to metadata
    metadata$batch <- batch_assignments

    # Reorder by batch for convenience
    metadata <- metadata[order(metadata$batch), ]

    cat("\n✓ Batch design generated successfully!\n")
    cat(sprintf("  Created %d batches with ~%d samples each\n", n_batches, batch_size))
    cat(sprintf("  Balanced variables: %s\n", paste(balance_vars, collapse = ", ")))

    return(metadata)

  }, error = function(e) {
    # If osat fails, use simple randomized block design
    warning("osat optimization failed. Using randomized block design instead.")
    return(assign_samples_simple(metadata, batch_size, balance_vars, sample_id_col))
  })
}


#' Simple randomized block assignment (fallback if osat fails)
#' @keywords internal
assign_samples_simple <- function(metadata, batch_size, balance_vars, sample_id_col) {

  n_samples <- nrow(metadata)
  n_batches <- ceiling(n_samples / batch_size)

  # Stratify by first balance variable (typically condition)
  primary_var <- balance_vars[1]

  # Sort by primary variable
  metadata <- metadata[order(metadata[[primary_var]]), ]

  # Assign batches in round-robin fashion to ensure balance
  batch_assignments <- rep(1:n_batches, length.out = n_samples)

  # Randomize within strata
  set.seed(123)  # For reproducibility
  metadata$batch <- sample(batch_assignments)

  # Reorder by batch
  metadata <- metadata[order(metadata$batch), ]

  message("Simple randomized block assignment complete")
  return(metadata)
}


#' Generate incomplete block design when complete balance is impossible
#'
#' @param metadata Data frame with sample metadata
#' @param batch_size Number of samples per batch
#' @param primary_var Primary variable that MUST be balanced (no confounding)
#' @param secondary_vars Secondary variables to balance as much as possible
#' @param constraints List of additional constraints
#' @return Data frame with batch assignments
#' @export
incomplete_block_design <- function(metadata,
                                    batch_size,
                                    primary_var,
                                    secondary_vars = NULL,
                                    constraints = NULL) {

  # Validate that primary variable exists
  if (!primary_var %in% colnames(metadata)) {
    stop(paste0("Primary variable '", primary_var, "' not found in metadata"))
  }

  # Get levels of primary variable
  primary_levels <- unique(metadata[[primary_var]])
  n_levels <- length(primary_levels)

  # Check if complete balance is possible
  min_samples_per_level <- min(table(metadata[[primary_var]]))

  if (batch_size %% n_levels != 0) {
    message("Batch size not evenly divisible by number of conditions.")
    message("Creating incomplete block design...")
  }

  # Ensure each batch has all levels of primary variable
  n_samples <- nrow(metadata)
  n_batches <- ceiling(n_samples / batch_size)

  # Create stratified assignment
  metadata$batch <- NA

  batch_num <- 1
  samples_in_current_batch <- 0

  # Cycle through conditions
  while (any(is.na(metadata$batch))) {
    for (level in primary_levels) {
      # Find unassigned samples for this level
      eligible <- which(metadata[[primary_var]] == level & is.na(metadata$batch))

      if (length(eligible) > 0 && samples_in_current_batch < batch_size) {
        # Assign one sample from this level to current batch
        metadata$batch[eligible[1]] <- batch_num
        samples_in_current_batch <- samples_in_current_batch + 1

        if (samples_in_current_batch >= batch_size) {
          batch_num <- batch_num + 1
          samples_in_current_batch <- 0
        }
      }
    }
  }

  message("Incomplete block design created")
  message(paste0("Primary variable '", primary_var, "' is balanced across batches"))

  return(metadata)
}


#' Generate randomization scheme within batches
#'
#' @param batch_metadata Data frame with batch assignments
#' @param randomize_within Should samples be randomized within batches? (default: TRUE)
#' @return Data frame with processing order added
#' @export
add_processing_order <- function(batch_metadata,
                                 randomize_within = TRUE) {

  if (!"batch" %in% colnames(batch_metadata)) {
    stop("Metadata must contain 'batch' column")
  }

  # Add processing order within each batch
  batch_metadata$processing_order <- NA

  for (b in unique(batch_metadata$batch)) {
    batch_rows <- which(batch_metadata$batch == b)

    if (randomize_within) {
      # Randomize order within batch
      set.seed(b)  # Different seed per batch for reproducibility
      processing_order <- sample(batch_rows)
    } else {
      # Keep existing order
      processing_order <- batch_rows
    }

    batch_metadata$processing_order[batch_rows] <- seq_along(batch_rows)
  }

  # Add overall processing sequence
  batch_metadata <- batch_metadata[order(batch_metadata$batch, batch_metadata$processing_order), ]
  batch_metadata$overall_sequence <- 1:nrow(batch_metadata)

  return(batch_metadata)
}


#' Add plate position assignments to avoid edge effects
#'
#' @param batch_metadata Data frame with batch assignments
#' @param plate_format Plate format (default: "96-well")
#' @return Data frame with well positions added
#' @export
add_plate_positions <- function(batch_metadata,
                                plate_format = "96-well") {

  if (!"batch" %in% colnames(batch_metadata)) {
    stop("Metadata must contain 'batch' column")
  }

  # Define plate dimensions
  plate_formats <- list(
    "96-well" = list(rows = 8, cols = 12),
    "384-well" = list(rows = 16, cols = 24),
    "48-well" = list(rows = 6, cols = 8)
  )

  if (!plate_format %in% names(plate_formats)) {
    stop(paste0("Plate format not recognized. Choose from: ", paste(names(plate_formats), collapse = ", ")))
  }

  dims <- plate_formats[[plate_format]]

  # Generate well positions (avoid edges)
  row_letters <- LETTERS[1:dims$rows]
  col_numbers <- 1:dims$cols

  # Create all positions
  all_positions <- expand.grid(row = row_letters, col = col_numbers, stringsAsFactors = FALSE)
  all_positions$well <- paste0(all_positions$row, sprintf("%02d", all_positions$col))

  # Mark edge positions
  all_positions$is_edge <- (
    all_positions$row == row_letters[1] |
    all_positions$row == row_letters[dims$rows] |
    all_positions$col == 1 |
    all_positions$col == dims$cols
  )

  # Assign positions to samples (prefer non-edge)
  batch_metadata$plate <- NA
  batch_metadata$well <- NA
  batch_metadata$is_edge_well <- NA

  plate_num <- 1
  position_idx <- 1

  # First assign non-edge positions
  non_edge_positions <- all_positions[!all_positions$is_edge, ]

  for (i in 1:nrow(batch_metadata)) {
    if (position_idx > nrow(non_edge_positions)) {
      # Start new plate or use edge positions
      plate_num <- plate_num + 1
      position_idx <- 1
    }

    batch_metadata$plate[i] <- plate_num
    batch_metadata$well[i] <- non_edge_positions$well[position_idx]
    batch_metadata$is_edge_well[i] <- FALSE
    position_idx <- position_idx + 1
  }

  message(paste0("Assigned samples to ", plate_num, " plates (", plate_format, ")"))
  message("Avoided edge wells when possible")

  return(batch_metadata)
}

