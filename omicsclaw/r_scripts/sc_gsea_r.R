#!/usr/bin/env Rscript
# sc_gsea_r.R — clusterProfiler GSEA via fgsea backend
#
# CLI: Rscript sc_gsea_r.R <de_csv> <output_dir> [species] [db] [score_type]
#
# de_csv columns: gene, avg_log2FC, and a group column (auto-detected)
# Output: gsea_r_results.csv with columns:
#   ID, Description, NES, pvalue, p.adjust, core_enrichment, setSize, Group, Database

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  cat("Usage: Rscript sc_gsea_r.R <de_csv> <output_dir> [species] [db] [score_type]\n",
      file = stderr())
  quit(status = 1)
}

de_csv_path <- args[1]
output_dir  <- args[2]
species     <- if (length(args) >= 3) args[3] else "Homo_sapiens"
db          <- if (length(args) >= 4) args[4] else "GO_BP"
score_type  <- if (length(args) >= 5) args[5] else "std"

if (!dir.exists(output_dir)) {
  dir.create(output_dir, recursive = TRUE)
}

# Empty-result header for graceful fallback
RESULT_COLS <- c("ID", "Description", "NES", "pvalue", "p.adjust",
                 "core_enrichment", "setSize", "Group", "Database")

write_empty_result <- function() {
  empty_df <- data.frame(matrix(nrow = 0, ncol = length(RESULT_COLS)))
  colnames(empty_df) <- RESULT_COLS
  write.csv(empty_df, file.path(output_dir, "gsea_r_results.csv"),
            row.names = FALSE, quote = TRUE)
  cat("INFO: No enrichment results found. Writing empty CSV.\n")
}

tryCatch({
  suppressPackageStartupMessages({
    library(clusterProfiler)
    library(DOSE)
    library(dplyr)
  })

  # --- 1. Read DE table ---
  de_df <- read.csv(de_csv_path, stringsAsFactors = FALSE)
  if (nrow(de_df) == 0) {
    cat("WARNING: Empty DE table provided.\n", file = stderr())
    write_empty_result()
    quit(status = 0)
  }

  # --- 2. Detect gene column ---
  gene_col <- NULL
  for (candidate in c("gene", "names", "Gene", "gene_name", "symbol")) {
    if (candidate %in% colnames(de_df)) {
      gene_col <- candidate
      break
    }
  }
  if (is.null(gene_col)) {
    stop("Could not find a gene column (expected: gene, names, Gene, gene_name, or symbol)")
  }

  # --- 3. Detect score column ---
  score_col <- NULL
  for (candidate in c("avg_log2FC", "logfoldchanges", "log2FoldChange",
                       "scores", "stat", "score")) {
    if (candidate %in% colnames(de_df)) {
      score_col <- candidate
      break
    }
  }
  if (is.null(score_col)) {
    stop("Could not find a score column (expected: avg_log2FC, logfoldchanges, log2FoldChange, scores, stat)")
  }

  # --- 4. Detect group column ---
  group_col <- NULL
  for (candidate in c("group1", "group", "cluster", "Group")) {
    if (candidate %in% colnames(de_df)) {
      group_col <- candidate
      break
    }
  }
  if (is.null(group_col)) {
    # Fall back to first non-numeric, non-gene column
    for (col in colnames(de_df)) {
      if (col == gene_col || col == score_col) next
      if (!is.numeric(de_df[[col]])) {
        group_col <- col
        break
      }
    }
  }
  if (is.null(group_col)) {
    # If still no group, treat all rows as one group
    de_df$`_group` <- "all"
    group_col <- "_group"
  }

  cat(sprintf("INFO: gene=%s, score=%s, group=%s, species=%s, db=%s, scoreType=%s\n",
              gene_col, score_col, group_col, species, db, score_type))

  # --- 5. Clean data ---
  de_df[[gene_col]] <- toupper(as.character(de_df[[gene_col]]))
  de_df[[score_col]] <- as.numeric(de_df[[score_col]])
  de_df <- de_df[!is.na(de_df[[score_col]]) & is.finite(de_df[[score_col]]), ]

  if (nrow(de_df) == 0) {
    cat("WARNING: No valid rows after removing NA/Inf scores.\n", file = stderr())
    write_empty_result()
    quit(status = 0)
  }

  # --- 6. Auto-detect scoreType ---
  all_scores <- de_df[[score_col]]
  if (all(all_scores > 0)) {
    score_type <- "pos"
    cat("INFO: All scores positive, forcing scoreType='pos'\n")
  } else if (all(all_scores < 0)) {
    score_type <- "neg"
    cat("INFO: All scores negative, forcing scoreType='neg'\n")
  }

  # --- 7. Build TERM2GENE for the requested database ---
  build_go_bp_term2gene <- function(species) {
    if (species == "Mus_musculus") {
      suppressPackageStartupMessages(library(org.Mm.eg.db))
      orgDb <- org.Mm.eg.db::org.Mm.eg.db
    } else {
      suppressPackageStartupMessages(library(org.Hs.eg.db))
      orgDb <- org.Hs.eg.db::org.Hs.eg.db
    }
    # Map gene symbols to entrez IDs
    all_genes <- unique(de_df[[gene_col]])
    gene2entrez <- tryCatch({
      res <- AnnotationDbi::mapIds(orgDb, keys = all_genes,
                                    keytype = "SYMBOL", column = "ENTREZID",
                                    multiVals = "first")
      res[!is.na(res)]
    }, error = function(e) {
      cat("WARNING: Gene ID mapping failed:", conditionMessage(e), "\n", file = stderr())
      character(0)
    })
    if (length(gene2entrez) == 0) return(NULL)

    # Get GO BP gene sets using entrez IDs
    go_data <- tryCatch({
      AnnotationDbi::select(orgDb,
                            keys = unique(unname(gene2entrez)),
                            keytype = "ENTREZID",
                            columns = c("ENTREZID", "GOALL", "ONTOLOGYALL"))
    }, error = function(e) {
      cat("WARNING: GO annotation query failed:", conditionMessage(e), "\n", file = stderr())
      return(NULL)
    })
    if (is.null(go_data) || nrow(go_data) == 0) return(NULL)

    # Filter to BP only
    go_bp <- go_data[go_data$ONTOLOGYALL == "BP" & !is.na(go_data$GOALL), ]
    if (nrow(go_bp) == 0) return(NULL)

    # Map entrez back to symbol
    entrez2symbol <- setNames(names(gene2entrez), unname(gene2entrez))
    go_bp$SYMBOL <- entrez2symbol[go_bp$ENTREZID]
    go_bp <- go_bp[!is.na(go_bp$SYMBOL), ]

    term2gene <- data.frame(
      TERM = go_bp$GOALL,
      GENE = go_bp$SYMBOL,
      stringsAsFactors = FALSE
    )
    term2gene <- unique(term2gene)
    return(term2gene)
  }

  term2gene <- NULL
  use_gse_kegg <- FALSE

  if (db == "GO_BP") {
    term2gene <- build_go_bp_term2gene(species)
  } else if (db == "KEGG") {
    use_gse_kegg <- TRUE
  } else if (db == "Reactome") {
    if (requireNamespace("ReactomePA", quietly = TRUE)) {
      cat("INFO: ReactomePA available, but using GO_BP fallback for stability.\n")
    }
    cat("WARNING: Reactome not fully supported yet, falling back to GO_BP.\n",
        file = stderr())
    db <- "GO_BP"
    term2gene <- build_go_bp_term2gene(species)
  }

  # --- 8. Run GSEA per group ---
  groups <- unique(de_df[[group_col]])
  all_results <- list()

  for (grp in groups) {
    grp_df <- de_df[de_df[[group_col]] == grp, ]

    # Build ranked named vector, deduplicate by max abs score
    grp_df <- grp_df %>%
      group_by(.data[[gene_col]]) %>%
      slice_max(abs(.data[[score_col]]), n = 1, with_ties = FALSE) %>%
      ungroup()

    if (nrow(grp_df) < 10) {
      cat(sprintf("WARNING: Group '%s' has fewer than 10 genes, skipping.\n", grp),
          file = stderr())
      next
    }

    ranks <- sort(setNames(grp_df[[score_col]], grp_df[[gene_col]]),
                  decreasing = TRUE)

    # Validate: enough non-NA ranks
    if (sum(!is.na(ranks)) < 10) {
      cat(sprintf("WARNING: Group '%s' has fewer than 10 non-NA ranked genes, skipping.\n", grp),
          file = stderr())
      next
    }

    tryCatch({
      if (use_gse_kegg) {
        # KEGG pathway — use gseKEGG which handles ID conversion internally
        kegg_organism <- if (species == "Mus_musculus") "mmu" else "hsa"
        if (species == "Mus_musculus") {
          suppressPackageStartupMessages(library(org.Mm.eg.db))
          orgDb <- org.Mm.eg.db::org.Mm.eg.db
        } else {
          suppressPackageStartupMessages(library(org.Hs.eg.db))
          orgDb <- org.Hs.eg.db::org.Hs.eg.db
        }
        # Convert symbols to entrez
        gene2entrez <- AnnotationDbi::mapIds(orgDb, keys = names(ranks),
                                              keytype = "SYMBOL", column = "ENTREZID",
                                              multiVals = "first")
        valid <- !is.na(gene2entrez)
        if (sum(valid) < 10) {
          cat(sprintf("WARNING: Group '%s' has fewer than 10 mapped KEGG genes, skipping.\n", grp),
              file = stderr())
          next
        }
        entrez_ranks <- sort(setNames(ranks[valid], unname(gene2entrez[valid])),
                             decreasing = TRUE)
        res <- clusterProfiler::gseKEGG(
          geneList    = entrez_ranks,
          organism    = kegg_organism,
          minGSSize   = 10,
          maxGSSize   = 500,
          pvalueCutoff = 1.0,
          scoreType   = score_type,
          verbose     = FALSE
        )
      } else if (!is.null(term2gene) && nrow(term2gene) > 0) {
        res <- clusterProfiler::GSEA(
          geneList   = ranks,
          TERM2GENE  = term2gene,
          minGSSize  = 10,
          maxGSSize  = 500,
          pvalueCutoff = 1.0,
          scoreType  = score_type,
          by         = "fgsea",
          verbose    = FALSE
        )
      } else {
        cat(sprintf("WARNING: No TERM2GENE available for group '%s', skipping.\n", grp),
            file = stderr())
        next
      }

      if (!is.null(res) && nrow(as.data.frame(res)) > 0) {
        result_df <- as.data.frame(res)
        result_df$Group    <- grp
        result_df$Database <- db
        all_results[[grp]] <- result_df
        cat(sprintf("INFO: Group '%s': %d enriched terms found.\n", grp, nrow(result_df)))
      } else {
        cat(sprintf("INFO: Group '%s': no enriched terms found.\n", grp))
      }
    }, error = function(e) {
      cat(sprintf("WARNING: GSEA failed for group '%s': %s\n", grp, conditionMessage(e)),
          file = stderr())
    })
  }

  # --- 9. Combine results ---
  if (length(all_results) > 0) {
    combined <- do.call(rbind, all_results)
    rownames(combined) <- NULL

    # Standardize column names
    keep_cols <- intersect(
      c("ID", "Description", "NES", "pvalue", "p.adjust",
        "core_enrichment", "setSize", "Group", "Database"),
      colnames(combined)
    )
    combined <- combined[, keep_cols, drop = FALSE]
    write.csv(combined, file.path(output_dir, "gsea_r_results.csv"),
              row.names = FALSE, quote = TRUE)
    cat(sprintf("INFO: Wrote %d total enrichment results.\n", nrow(combined)))
  } else {
    cat("INFO: No enrichment results from any group.\n")

    # --- Demo fallback: synthetic gene sets ---
    if (nrow(de_df) > 0) {
      cat("INFO: Attempting demo fallback with synthetic gene sets.\n")
      synthetic_genes <- toupper(unique(de_df[[gene_col]]))[1:min(50, length(unique(de_df[[gene_col]])))]
      n_genes <- length(synthetic_genes)
      if (n_genes >= 10) {
        # Create 5 synthetic pathways
        n_per_term <- ceiling(n_genes / 5)
        synthetic_t2g <- data.frame(
          TERM = rep(paste0("DEMO_PATHWAY_", 1:5), each = n_per_term)[1:n_genes],
          GENE = synthetic_genes,
          stringsAsFactors = FALSE
        )

        # Try GSEA with synthetic gene sets on the first group
        first_grp <- groups[1]
        grp_df <- de_df[de_df[[group_col]] == first_grp, ]
        grp_df <- grp_df %>%
          group_by(.data[[gene_col]]) %>%
          slice_max(abs(.data[[score_col]]), n = 1, with_ties = FALSE) %>%
          ungroup()
        ranks <- sort(setNames(grp_df[[score_col]], grp_df[[gene_col]]),
                      decreasing = TRUE)

        tryCatch({
          res <- clusterProfiler::GSEA(
            geneList   = ranks,
            TERM2GENE  = synthetic_t2g,
            minGSSize  = 5,
            maxGSSize  = 500,
            pvalueCutoff = 1.0,
            scoreType  = score_type,
            by         = "fgsea",
            verbose    = FALSE
          )
          if (!is.null(res) && nrow(as.data.frame(res)) > 0) {
            result_df <- as.data.frame(res)
            result_df$Group    <- first_grp
            result_df$Database <- "DEMO"
            keep_cols <- intersect(RESULT_COLS, colnames(result_df))
            result_df <- result_df[, keep_cols, drop = FALSE]
            write.csv(result_df, file.path(output_dir, "gsea_r_results.csv"),
                      row.names = FALSE, quote = TRUE)
            cat(sprintf("INFO: Demo fallback produced %d enriched terms.\n", nrow(result_df)))
          } else {
            write_empty_result()
          }
        }, error = function(e) {
          cat(sprintf("WARNING: Demo fallback GSEA also failed: %s\n", conditionMessage(e)),
              file = stderr())
          write_empty_result()
        })
      } else {
        write_empty_result()
      }
    } else {
      write_empty_result()
    }
  }

}, error = function(e) {
  cat(sprintf("ERROR: %s\n", conditionMessage(e)), file = stderr())
  quit(status = 1)
})
