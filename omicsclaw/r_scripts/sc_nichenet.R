#!/usr/bin/env Rscript

args <- commandArgs(trailingOnly = TRUE)

if (length(args) < 10) {
  cat(
    "Usage: Rscript sc_nichenet.R <h5ad_file> <output_dir> <cell_type_key> <condition_key> <condition_oi> <condition_ref> <receiver> <senders_csv> <top_ligands> <expression_pct>\n"
  )
  quit(status = 1)
}

h5ad_file <- args[1]
output_dir <- args[2]
cell_type_key <- args[3]
condition_key <- args[4]
condition_oi <- args[5]
condition_ref <- args[6]
receiver <- args[7]
senders <- strsplit(args[8], ",", fixed = TRUE)[[1]]
top_ligands <- as.integer(args[9])
expression_pct <- as.numeric(args[10])

suppressPackageStartupMessages({
  library(zellkonverter)
  library(SingleCellExperiment)
  library(Seurat)
  library(nichenetr)
  library(dplyr)
})

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

cache_dir <- file.path(path.expand("~"), ".cache", "omicsclaw", "nichenet")
dir.create(cache_dir, recursive = TRUE, showWarnings = FALSE)

download_if_missing <- function(url, dest) {
  if (!file.exists(dest)) {
    options(timeout = max(600, getOption("timeout")))
    download.file(url, destfile = dest, mode = "wb", quiet = FALSE)
  }
  dest
}

load_nichenet_resources <- function() {
  lr_network_path <- download_if_missing(
    "https://zenodo.org/record/7074291/files/lr_network_human_21122021.rds",
    file.path(cache_dir, "lr_network_human_21122021.rds")
  )
  weighted_networks_path <- download_if_missing(
    "https://zenodo.org/record/7074291/files/weighted_networks_nsga2r_final.rds",
    file.path(cache_dir, "weighted_networks_nsga2r_final.rds")
  )
  list(
    lr_network = readRDS(lr_network_path),
    weighted_networks = readRDS(weighted_networks_path)
  )
}

tryCatch({
  sce <- readH5AD(h5ad_file)
  expr <- SummarizedExperiment::assay(sce, "X")
  meta <- as.data.frame(SummarizedExperiment::colData(sce))

  if (!cell_type_key %in% colnames(meta)) {
    stop(sprintf("Cell type key '%s' not found in metadata.", cell_type_key))
  }
  if (!condition_key %in% colnames(meta)) {
    stop(sprintf("Condition key '%s' not found in metadata.", condition_key))
  }

  meta[[cell_type_key]] <- as.character(meta[[cell_type_key]])
  meta[[condition_key]] <- as.character(meta[[condition_key]])

  if (!receiver %in% meta[[cell_type_key]]) {
    stop(sprintf("Receiver '%s' not found in '%s'.", receiver, cell_type_key))
  }
  if (!(condition_oi %in% meta[[condition_key]])) {
    stop(sprintf("Condition of interest '%s' not found in '%s'.", condition_oi, condition_key))
  }
  if (!(condition_ref %in% meta[[condition_key]])) {
    stop(sprintf("Reference condition '%s' not found in '%s'.", condition_ref, condition_key))
  }

  missing_senders <- setdiff(senders, unique(meta[[cell_type_key]]))
  if (length(missing_senders) > 0) {
    stop(sprintf("Sender cell types not found in '%s': %s", cell_type_key, paste(missing_senders, collapse = ", ")))
  }

  seu <- CreateSeuratObject(counts = expr)
  meta <- meta[colnames(seu), , drop = FALSE]
  seu <- AddMetaData(seu, metadata = meta)
  Idents(seu) <- seu[[cell_type_key]][, 1]
  seu <- NormalizeData(seu, verbose = FALSE)

  resources <- load_nichenet_resources()
  resources$lr_network <- resources$lr_network %>% dplyr::distinct(from, to, .keep_all = TRUE)

  expressed_genes_receiver <- get_expressed_genes(receiver, seu, pct = expression_pct)
  sender_networks <- list()
  for (sender in senders) {
    expressed_genes_sender <- get_expressed_genes(sender, seu, pct = expression_pct)
    pairs <- resources$lr_network %>%
      dplyr::filter(from %in% expressed_genes_sender & to %in% expressed_genes_receiver) %>%
      dplyr::mutate(source = sender, target = receiver)
    if (nrow(pairs) > 0) {
      sender_networks[[length(sender_networks) + 1]] <- pairs
    }
  }
  if (length(sender_networks) == 0) {
    stop("No expressed ligand-receptor links were found for the requested sender and receiver cell types.")
  }
  lr_network_expressed <- dplyr::bind_rows(sender_networks) %>%
    dplyr::distinct(source, target, from, to, .keep_all = TRUE)
  potential_ligands <- lr_network_expressed %>%
    dplyr::pull(from) %>%
    unique()

  ligand_target_matrix <- construct_ligand_target_matrix(
    weighted_networks = resources$weighted_networks,
    lr_network = resources$lr_network,
    ligands = as.list(potential_ligands)
  )

  receiver_subset <- subset(seu, idents = receiver)
  Idents(receiver_subset) <- receiver_subset[[condition_key]][, 1]
  de_table <- FindMarkers(
    object = receiver_subset,
    ident.1 = condition_oi,
    ident.2 = condition_ref,
    logfc.threshold = 0.25,
    min.pct = expression_pct,
    verbose = FALSE
  ) %>%
    tibble::rownames_to_column("gene")

  fc_col <- if ("avg_log2FC" %in% colnames(de_table)) "avg_log2FC" else if ("avg_logFC" %in% colnames(de_table)) "avg_logFC" else NA_character_
  p_col <- if ("p_val_adj" %in% colnames(de_table)) "p_val_adj" else if ("p_val" %in% colnames(de_table)) "p_val" else NA_character_
  if (is.na(fc_col) || is.na(p_col)) {
    stop("Could not identify DE result columns from Seurat::FindMarkers output.")
  }
  geneset_oi <- de_table %>%
    dplyr::filter(.data[[fc_col]] > 0 & .data[[p_col]] <= 0.05) %>%
    dplyr::pull(gene) %>%
    unique()
  if (length(geneset_oi) == 0) {
    stop("No genes were differentially expressed in the receiver cell type.")
  }

  ligand_activities <- predict_ligand_activities(
    geneset = geneset_oi,
    background_expressed_genes = expressed_genes_receiver,
    ligand_target_matrix = ligand_target_matrix,
    potential_ligands = potential_ligands
  ) %>%
    dplyr::arrange(dplyr::desc(pearson))
  best_n_ligands <- min(top_ligands, nrow(ligand_activities))
  best_upstream_ligands <- utils::head(ligand_activities, best_n_ligands)

  ligand_target_links <- get_weighted_ligand_target_links(
    best_upstream_ligands$test_ligand,
    geneset = geneset_oi,
    ligand_target_matrix = ligand_target_matrix,
    n = 250
  )
  expressed_receptors <- intersect(expressed_genes_receiver, unique(resources$lr_network$to))
  ligand_receptor_df <- get_weighted_ligand_receptor_links(
    best_upstream_ligands = best_upstream_ligands,
    expressed_receptors = expressed_receptors,
    lr_network = resources$lr_network,
    weighted_networks_lr_sig = resources$weighted_networks$lr_sig
  )

  lr_network_top <- lr_network_expressed %>%
    dplyr::filter(from %in% best_upstream_ligands$test_ligand) %>%
    dplyr::left_join(
      best_upstream_ligands %>% dplyr::select(test_ligand, pearson),
      by = c("from" = "test_ligand")
    ) %>%
    dplyr::transmute(
      ligand = from,
      receptor = to,
      source = source,
      target = target,
      score = pearson
    ) %>%
    dplyr::arrange(dplyr::desc(score))

  write.csv(best_upstream_ligands, file.path(output_dir, "nichenet_ligand_activities.csv"), row.names = FALSE, quote = FALSE)
  write.csv(ligand_target_links, file.path(output_dir, "nichenet_ligand_target_links.csv"), row.names = FALSE, quote = FALSE)
  write.csv(lr_network_top, file.path(output_dir, "nichenet_lr_network.csv"), row.names = FALSE, quote = FALSE)
  write.csv(ligand_receptor_df, file.path(output_dir, "nichenet_ligand_receptors.csv"), row.names = FALSE, quote = FALSE)

  cat(sprintf(
    "Done. Receiver=%s, senders=%s, prioritized_ligands=%d, lr_rows=%d\n",
    receiver,
    paste(senders, collapse = ","),
    nrow(best_upstream_ligands),
    nrow(lr_network_top)
  ))
}, error = function(e) {
  cat(sprintf("ERROR: %s\n", e$message), file = stderr())
  quit(status = 1)
})
