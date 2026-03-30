#!/usr/bin/env Rscript

# =============================================================================
# Load GSE128959 bladder cancer example dataset for disease progression analysis
#
# Downloads and preprocesses the bladder cancer recurrence cohort from the
# TimeAx paper (Frishberg et al. 2023, Nature Communications).
#
# Source: https://github.com/shenorrLabTRDF/TimeAxPaperCode
# GEO: GSE128959 (Affymetrix HuGene-1.0 ST, 199 samples, 70 patients)
#
# Preprocessing (matches paper):
#   1. Load RMA-normalized, gene-symbol-mapped expression data
#   2. ComBat batch correction (11 labeling batches, no model matrix)
#   3. Filter to protein-coding genes (~17,344)
#   4. Select patients with >3 timepoints (18 patients, 84 samples)
#   5. Export as CSV files for the Python pipeline
# =============================================================================

suppressPackageStartupMessages({
  library(sva)
})

cat("\n=== Loading GSE128959 Bladder Cancer Example Dataset ===\n\n")

# Determine paths
args <- commandArgs(trailingOnly = TRUE)
if (length(args) >= 1) {
  output_dir <- args[1]
} else {
  # Fallback: resolve relative to script location
  script_dir <- tryCatch({
    initial.options <- commandArgs(trailingOnly = FALSE)
    file.arg <- grep("--file=", initial.options, value = TRUE)
    if (length(file.arg) > 0) {
      dirname(normalizePath(sub("--file=", "", file.arg)))
    } else {
      "."
    }
  }, error = function(e) ".")
  output_dir <- file.path(script_dir, "..", "data")
}

paper_data_dir <- file.path(output_dir, "paper_data")
dir.create(paper_data_dir, showWarnings = FALSE, recursive = TRUE)

# Download paper data from GitHub if not cached
repo_base <- "https://raw.githubusercontent.com/shenorrLabTRDF/TimeAxPaperCode/main/sourceCode"
files_needed <- c("UBCFullDataRaw.rds", "batchInformation.txt", "proteinCodingGenes.txt")

for (f in files_needed) {
  local_path <- file.path(paper_data_dir, f)
  if (!file.exists(local_path)) {
    cat("  Downloading", f, "...\n")
    options(timeout = 300)
    download.file(file.path(repo_base, f), local_path, mode = "wb", quiet = TRUE)
  }
}
cat("✓ Paper data available\n")

# Load data
UBCFullData <- readRDS(file.path(paper_data_dir, "UBCFullDataRaw.rds"))
annotations <- UBCFullData$annotations
GEData <- UBCFullData$GEData
sampleNames_vec <- as.character(annotations$Patient_ID)

cat("  Expression:", nrow(GEData), "genes x", ncol(GEData), "samples\n")
cat("  Patients:", length(unique(sampleNames_vec)), "\n")

# ComBat batch correction (no model matrix — matches paper exactly)
cat("\nApplying ComBat batch correction...\n")
batchInfo <- read.table(file.path(paper_data_dir, "batchInformation.txt"),
  sep = "\t", row.names = 1, header = TRUE, check.names = FALSE)
batchInfo <- batchInfo[colnames(GEData), , drop = FALSE]
GEDataCombat <- sva::ComBat(GEData, batchInfo[, 1])
cat("✓ ComBat complete (11 batches corrected)\n")

# Filter to protein-coding genes
proteinCodingGenes <- as.character(as.matrix(read.table(
  file.path(paper_data_dir, "proteinCodingGenes.txt"),
  sep = "\t", row.names = NULL, col.names = FALSE)))
pcg <- intersect(proteinCodingGenes, rownames(GEDataCombat))
GEDataFiltered <- GEDataCombat[pcg, ]
cat("✓ Filtered to", nrow(GEDataFiltered), "protein-coding genes\n")

# Select training patients (>3 timepoints)
trainPatients <- names(which(table(sampleNames_vec) > 3))
trainIdx <- which(sampleNames_vec %in% trainPatients)
trainAnnot <- annotations[trainIdx, ]

# Build expression and metadata for the pipeline
expr_train <- GEDataFiltered[, trainIdx]

# Create metadata in standard format
metadata <- data.frame(
  sample_id = rownames(trainAnnot),
  patient_id = paste0("P_", trainAnnot$Patient_ID),
  timepoint = as.numeric(gsub("T_", "", trainAnnot$Tumor_Number)),
  tumor_stage = trainAnnot$Stage,
  molecular_subtype = trainAnnot$Consensus_Subtype_RNA,
  stringsAsFactors = FALSE
)

cat("✓ Training set:", length(trainPatients), "patients,", ncol(expr_train), "samples\n")
cat("  Timepoints per patient:", paste(range(table(metadata$patient_id)), collapse = "-"), "\n")

# Export CSV files
expr_file <- file.path(output_dir, "gse128959_expression.csv")
meta_file <- file.path(output_dir, "gse128959_metadata.csv")

write.csv(expr_train, expr_file)
write.csv(metadata, meta_file, row.names = FALSE)

cat("\n✓ Example data exported:\n")
cat("  ", expr_file, "\n")
cat("  ", meta_file, "\n")
cat("\n✓ Data loaded successfully\n")

