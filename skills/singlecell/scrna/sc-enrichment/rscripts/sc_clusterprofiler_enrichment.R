args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 6) {
  stop(
    paste(
      "Usage: sc_clusterprofiler_enrichment.R",
      "<method: ora|gsea>",
      "<ranking_csv>",
      "<universe_txt>",
      "<gene_sets_gmt>",
      "<output_dir>",
      "<top_terms>",
      "[min_size max_size permutation_num seed]"
    )
  )
}

method <- args[[1]]
ranking_csv <- args[[2]]
universe_txt <- args[[3]]
gene_sets_gmt <- args[[4]]
output_dir <- args[[5]]
top_terms <- as.integer(args[[6]])
min_size <- if (length(args) >= 7) as.integer(args[[7]]) else 10L
max_size <- if (length(args) >= 8) as.integer(args[[8]]) else 500L
permutation_num <- if (length(args) >= 9) as.integer(args[[9]]) else 100L
seed <- if (length(args) >= 10) as.integer(args[[10]]) else 123L

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

suppressPackageStartupMessages({
  library(clusterProfiler)
  library(enrichplot)
  library(ggplot2)
})

ranking_df <- read.csv(ranking_csv, check.names = FALSE, stringsAsFactors = FALSE)
if (!all(c("group", "gene") %in% colnames(ranking_df))) {
  stop("ranking_csv must contain columns: group, gene")
}
universe <- readLines(universe_txt, warn = FALSE)
term2gene <- clusterProfiler::read.gmt(gene_sets_gmt)
if (!all(c("term", "gene") %in% tolower(colnames(term2gene)))) {
  colnames(term2gene)[1:2] <- c("term", "gene")
} else {
  colnames(term2gene)[1:2] <- c("term", "gene")
}
term2gene <- unique(term2gene[, c("term", "gene")])

groups <- unique(as.character(ranking_df$group))
results_list <- list()
result_objs <- list()

for (grp in groups) {
  df_sub <- subset(ranking_df, as.character(group) == grp)
  if (nrow(df_sub) == 0) {
    next
  }

  if (identical(method, "ora")) {
    genes <- unique(as.character(df_sub$gene))
    if (length(genes) == 0) {
      next
    }
    enr <- tryCatch(
      clusterProfiler::enricher(
        gene = genes,
        TERM2GENE = term2gene,
        universe = universe,
        minGSSize = min_size,
        maxGSSize = max_size,
        pvalueCutoff = 1,
        pAdjustMethod = "BH"
      ),
      error = function(e) NULL
    )
    if (is.null(enr) || nrow(as.data.frame(enr)) == 0) {
      next
    }
    res <- as.data.frame(enr)
    res$group <- grp
    results_list[[grp]] <- res
    result_objs[[grp]] <- enr
  } else {
    score_col <- if ("score" %in% colnames(df_sub)) "score" else if ("scores" %in% colnames(df_sub)) "scores" else stop("GSEA ranking needs a score column")
    gene_list <- df_sub[[score_col]]
    names(gene_list) <- as.character(df_sub$gene)
    gene_list <- sort(gene_list, decreasing = TRUE)
    gene_list <- gene_list[!duplicated(names(gene_list))]
    gsea_res <- tryCatch(
      clusterProfiler::GSEA(
        geneList = gene_list,
        TERM2GENE = term2gene,
        minGSSize = min_size,
        maxGSSize = max_size,
        pvalueCutoff = 1,
        pAdjustMethod = "BH",
        seed = TRUE,
        by = "fgsea",
        verbose = FALSE,
        eps = 0
      ),
      error = function(e) NULL
    )
    if (is.null(gsea_res) || nrow(as.data.frame(gsea_res)) == 0) {
      next
    }
    res <- as.data.frame(gsea_res)
    res$group <- grp
    results_list[[grp]] <- res
    result_objs[[grp]] <- gsea_res
  }
}

if (length(results_list) == 0) {
  write.csv(data.frame(), file.path(output_dir, "clusterprofiler_results.csv"), row.names = FALSE)
  quit(status = 0)
}

all_results <- do.call(rbind, results_list)
write.csv(all_results, file.path(output_dir, "clusterprofiler_results.csv"), row.names = FALSE)

signif_col <- if ("p.adjust" %in% colnames(all_results)) "p.adjust" else if ("qvalues" %in% colnames(all_results)) "qvalues" else NULL
score_col <- if ("NES" %in% colnames(all_results)) "NES" else if ("Count" %in% colnames(all_results)) "Count" else "p.adjust"

if (!is.null(signif_col)) {
  all_results <- all_results[order(all_results[[signif_col]], decreasing = FALSE), , drop = FALSE]
}

best_group <- names(result_objs)[1]
best_obj <- result_objs[[best_group]]
if (!is.null(signif_col)) {
  sig_by_group <- sapply(results_list, function(df) sum(df[[signif_col]] <= 0.05, na.rm = TRUE))
  if (length(sig_by_group) > 0) {
    best_group <- names(sig_by_group)[which.max(sig_by_group)]
    best_obj <- result_objs[[best_group]]
  }
}

fig_dir <- file.path(output_dir, "r_figures")
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)

safe_plot <- function(expr, filename, width = 10, height = 8) {
  tryCatch({
    png(file.path(fig_dir, filename), width = width, height = height, units = "in", res = 180)
    print(expr)
    dev.off()
  }, error = function(e) {
    try(dev.off(), silent = TRUE)
  })
}

safe_plot(barplot(best_obj, showCategory = min(top_terms, 15)) + ggtitle(sprintf("%s (%s)", toupper(method), best_group)), paste0(method, "_barplot_r.png"))
safe_plot(dotplot(best_obj, showCategory = min(top_terms, 15)) + ggtitle(sprintf("%s (%s)", toupper(method), best_group)), paste0(method, "_dotplot_r.png"))

if (identical(method, "gsea")) {
  safe_plot(ridgeplot(best_obj, showCategory = min(top_terms, 15)) + ggtitle(sprintf("Ridgeplot (%s)", best_group)), "gsea_ridgeplot.png", width = 11, height = 8)
  if (nrow(as.data.frame(best_obj)) >= 3) {
    sim_obj <- tryCatch(pairwise_termsim(best_obj), error = function(e) NULL)
    if (!is.null(sim_obj)) {
      safe_plot(emapplot(sim_obj, showCategory = min(top_terms, 25)) + ggtitle(sprintf("Enrichmap (%s)", best_group)), "gsea_enrichmap.png", width = 11, height = 9)
    }
  }
  best_term <- tryCatch(as.data.frame(best_obj)$ID[[1]], error = function(e) NULL)
  if (!is.null(best_term)) {
    safe_plot(gseaplot2(best_obj, geneSetID = best_term, title = sprintf("%s (%s)", best_term, best_group)), "gsea_running_score_r.png", width = 10, height = 8)
  }
} else {
  if (nrow(as.data.frame(best_obj)) >= 3) {
    sim_obj <- tryCatch(pairwise_termsim(best_obj), error = function(e) NULL)
    if (!is.null(sim_obj)) {
      safe_plot(emapplot(sim_obj, showCategory = min(top_terms, 25)) + ggtitle(sprintf("Enrichmap (%s)", best_group)), "ora_enrichmap.png", width = 11, height = 9)
    }
  }
}

figures <- list.files(fig_dir, pattern = "\\.png$", full.names = FALSE)
metadata_lines <- c(
  "{",
  sprintf('  "method": "%s",', method),
  sprintf('  "best_group": "%s",', best_group),
  paste0('  "figures": ["', paste(figures, collapse = '", "'), '"]'),
  "}"
)
writeLines(metadata_lines, file.path(output_dir, "r_plot_metadata.json"))
