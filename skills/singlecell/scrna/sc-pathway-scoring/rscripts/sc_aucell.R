args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 4) {
  stop("Usage: sc_aucell.R <expression_matrix.tsv> <gene_sets.gmt> <output_dir> <auc_max_rank>")
}

expression_matrix_tsv <- args[[1]]
gene_sets_gmt <- args[[2]]
output_dir <- args[[3]]
auc_max_rank <- as.integer(args[[4]])

dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)

suppressPackageStartupMessages({
  library(AUCell)
  library(GSEABase)
})

expr_df <- read.delim(expression_matrix_tsv, row.names = 1, check.names = FALSE)
expr_matrix <- as.matrix(expr_df)
storage.mode(expr_matrix) <- "numeric"

if (is.null(rownames(expr_matrix)) || is.null(colnames(expr_matrix))) {
  stop("AUCell input matrix must have gene and cell names")
}

gene_sets <- GSEABase::geneIds(GSEABase::getGmt(gene_sets_gmt))
rankings <- AUCell::AUCell_buildRankings(expr_matrix, plotStats = FALSE, verbose = FALSE)
cells_auc <- AUCell::AUCell_calcAUC(gene_sets, rankings, aucMaxRank = auc_max_rank)
auc_matrix <- t(as.matrix(getAUC(cells_auc)))

scores_df <- data.frame(Cell = rownames(auc_matrix), auc_matrix, check.names = FALSE)
write.csv(scores_df, file.path(output_dir, "aucell_scores.csv"), row.names = FALSE)
