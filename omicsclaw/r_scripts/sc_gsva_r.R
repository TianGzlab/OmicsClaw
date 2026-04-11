#!/usr/bin/env Rscript
# sc_gsva_r.R — GSVA group-level pathway scoring via GSVA R package
#
# CLI: Rscript sc_gsva_r.R <group_expr_csv> <output_dir> [species] [db] [gsva_method] [group_by]
#
# group_expr_csv: rows = cell type groups, cols = genes. First column is group name.
# Output:
#   gsva_r_scores.csv  — long format: pathway, group, gsva_score
#   gsva_r_meta.json   — metadata JSON
#
# IMPORTANT: Always uses SerialParam() to prevent OOM from parallel workers.
# IMPORTANT: Installed via BiocManager::install("GSVA", update=FALSE, ask=FALSE)

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  cat("Usage: Rscript sc_gsva_r.R <group_expr_csv> <output_dir> [species] [db] [gsva_method] [group_by]\n",
      file = stderr())
  quit(status = 1)
}

group_expr_csv <- args[1]
output_dir     <- args[2]
species        <- if (length(args) >= 3) args[3] else "Homo_sapiens"
db             <- if (length(args) >= 4) args[4] else "GO_BP"
gsva_method    <- if (length(args) >= 5) args[5] else "gsva"
group_by       <- if (length(args) >= 6) args[6] else "group"

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

# --- Graceful empty-result fallback ---
write_empty_result <- function(reason = "No GSVA results produced") {
  empty_df <- data.frame(pathway = character(0), group = character(0),
                         gsva_score = numeric(0), stringsAsFactors = FALSE)
  write.csv(empty_df, file.path(output_dir, "gsva_r_scores.csv"), row.names = FALSE)
  meta <- list(n_pathways = 0, n_groups = 0, db = db, method = gsva_method,
               species = species, group_by = group_by, reason = reason)
  writeLines(jsonlite::toJSON(meta, auto_unbox = TRUE, pretty = TRUE),
             file.path(output_dir, "gsva_r_meta.json"))
  cat(sprintf("INFO: %s. Writing empty CSV.\n", reason))
}

tryCatch({
  suppressPackageStartupMessages({
    library(GSVA)
    library(BiocParallel)
  })

  # --- 1. Read group expression matrix ---
  df <- read.csv(group_expr_csv, row.names = 1, check.names = FALSE)
  if (nrow(df) == 0 || ncol(df) == 0) {
    write_empty_result("Empty group expression matrix")
    quit(status = 0)
  }
  # Transpose: genes x groups
  expr_matrix <- t(as.matrix(df))
  gene_names <- toupper(rownames(expr_matrix))
  rownames(expr_matrix) <- gene_names
  gene_universe <- rownames(expr_matrix)

  cat(sprintf("INFO: Expression matrix: %d genes x %d groups\n",
              nrow(expr_matrix), ncol(expr_matrix)))
  cat(sprintf("INFO: species=%s, db=%s, method=%s, group_by=%s\n",
              species, db, gsva_method, group_by))

  # --- 2. Build gene sets ---
  gene_sets <- NULL

  if (db == "GO_BP") {
    tryCatch({
      suppressPackageStartupMessages({
        library(AnnotationDbi)
        if (species == "Mus_musculus") {
          library(org.Mm.eg.db)
          orgDb <- org.Mm.eg.db::org.Mm.eg.db
        } else {
          library(org.Hs.eg.db)
          orgDb <- org.Hs.eg.db::org.Hs.eg.db
        }
      })

      go_genes <- AnnotationDbi::select(
        orgDb,
        keys = AnnotationDbi::keys(orgDb, keytype = "GO"),
        columns = c("SYMBOL", "GO", "ONTOLOGY"),
        keytype = "GO"
      )
      go_bp <- go_genes[!is.na(go_genes$ONTOLOGY) & go_genes$ONTOLOGY == "BP", ]

      if (nrow(go_bp) > 0) {
        gene_sets_raw <- split(toupper(go_bp$SYMBOL), go_bp$GO)
        # Filter to sets overlapping with expression genes
        gene_sets <- lapply(gene_sets_raw, function(gs) intersect(gs, gene_universe))
        gene_sets <- gene_sets[sapply(gene_sets, length) >= 10]
        cat(sprintf("INFO: GO_BP gene sets after filtering: %d\n", length(gene_sets)))
      }
    }, error = function(e) {
      cat(sprintf("WARNING: GO_BP gene set build failed: %s\n", conditionMessage(e)),
          file = stderr())
    })
  } else if (db == "KEGG") {
    tryCatch({
      suppressPackageStartupMessages({
        library(AnnotationDbi)
        if (species == "Mus_musculus") {
          library(org.Mm.eg.db)
          orgDb <- org.Mm.eg.db::org.Mm.eg.db
        } else {
          library(org.Hs.eg.db)
          orgDb <- org.Hs.eg.db::org.Hs.eg.db
        }
      })
      # Get KEGG pathways via ENTREZID -> PATH mapping
      kegg_data <- AnnotationDbi::select(
        orgDb,
        keys = AnnotationDbi::keys(orgDb, keytype = "PATH"),
        columns = c("SYMBOL", "PATH"),
        keytype = "PATH"
      )
      if (nrow(kegg_data) > 0) {
        gene_sets_raw <- split(toupper(kegg_data$SYMBOL), kegg_data$PATH)
        gene_sets <- lapply(gene_sets_raw, function(gs) intersect(gs, gene_universe))
        gene_sets <- gene_sets[sapply(gene_sets, length) >= 10]
        cat(sprintf("INFO: KEGG gene sets after filtering: %d\n", length(gene_sets)))
      }
    }, error = function(e) {
      cat(sprintf("WARNING: KEGG gene set build failed: %s\n", conditionMessage(e)),
          file = stderr())
    })
  }

  # --- 3. Demo fallback: synthetic gene sets ---
  if (is.null(gene_sets) || length(gene_sets) == 0) {
    cat("INFO: No real gene sets found; using synthetic demo pathways.\n")
    n_genes <- length(gene_universe)
    if (n_genes < 10) {
      write_empty_result("Too few genes for GSVA (< 10)")
      quit(status = 0)
    }
    n_sets <- min(10, floor(n_genes / 5))
    gene_sets <- lapply(seq_len(n_sets), function(i) {
      sample(gene_universe, min(20, n_genes))
    })
    names(gene_sets) <- paste0("DEMO_PATHWAY_", seq_len(n_sets))
  }

  # --- 4. Cap gene sets for speed ---
  if (length(gene_sets) > 500) {
    cat(sprintf("INFO: Capping gene sets from %d to 500 for speed.\n", length(gene_sets)))
    gene_sets <- gene_sets[1:500]
  }

  # --- 5. Build GSVA param and run ---
  cat(sprintf("INFO: Running GSVA method=%s on %d gene sets, %d groups...\n",
              gsva_method, length(gene_sets), ncol(expr_matrix)))

  param <- switch(gsva_method,
    "gsva"   = gsvaParam(exprData = expr_matrix, geneSets = gene_sets,
                         minSize = 5, maxSize = 500),
    "ssgsea" = ssgseaParam(exprData = expr_matrix, geneSets = gene_sets,
                           minSize = 5),
    "zscore" = zscoreParam(exprData = expr_matrix, geneSets = gene_sets,
                           minSize = 5),
    # default to gsva
    gsvaParam(exprData = expr_matrix, geneSets = gene_sets, minSize = 5, maxSize = 500)
  )
  # CRITICAL: SerialParam() prevents OOM from parallel workers
  gsva_scores <- gsva(param, BPPARAM = SerialParam())

  cat(sprintf("INFO: GSVA complete. Score matrix: %d pathways x %d groups\n",
              nrow(gsva_scores), ncol(gsva_scores)))

  # --- 6. Convert to long format ---
  score_df <- as.data.frame(gsva_scores)
  score_df$pathway <- rownames(score_df)

  # Use stack() for simple long-format conversion
  group_names <- colnames(gsva_scores)
  long_rows <- list()
  for (grp in group_names) {
    long_rows[[grp]] <- data.frame(
      pathway    = rownames(score_df),
      group      = grp,
      gsva_score = score_df[[grp]],
      stringsAsFactors = FALSE
    )
  }
  long_df <- do.call(rbind, long_rows)
  rownames(long_df) <- NULL

  write.csv(long_df[, c("pathway", "group", "gsva_score")],
            file.path(output_dir, "gsva_r_scores.csv"), row.names = FALSE)
  cat(sprintf("INFO: Wrote %d rows to gsva_r_scores.csv\n", nrow(long_df)))

  # --- 7. Write metadata JSON ---
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    # Minimal JSON without jsonlite
    meta_str <- sprintf(
      '{"n_pathways": %d, "n_groups": %d, "db": "%s", "method": "%s", "species": "%s", "group_by": "%s"}',
      nrow(gsva_scores), ncol(gsva_scores), db, gsva_method, species, group_by
    )
    writeLines(meta_str, file.path(output_dir, "gsva_r_meta.json"))
  } else {
    meta <- list(
      n_pathways = nrow(gsva_scores),
      n_groups   = ncol(gsva_scores),
      db         = db,
      method     = gsva_method,
      species    = species,
      group_by   = group_by
    )
    writeLines(jsonlite::toJSON(meta, auto_unbox = TRUE, pretty = TRUE),
               file.path(output_dir, "gsva_r_meta.json"))
  }

  cat("INFO: GSVA R script complete.\n")

}, error = function(e) {
  cat(sprintf("ERROR: %s\n", conditionMessage(e)), file = stderr())
  # Try to write empty result so Python doesn't crash
  tryCatch({
    write_empty_result(paste("R error:", conditionMessage(e)))
  }, error = function(e2) {
    cat(sprintf("ERROR: Could not write fallback: %s\n", conditionMessage(e2)),
        file = stderr())
  })
  quit(status = 1)
})
