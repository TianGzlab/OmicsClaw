args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 14L) stop("Expected matrix CSV, output CSV, KO gene and 11 method arguments")
suppressPackageStartupMessages(library(scTenifoldKnk))
mat <- as.matrix(read.csv(args[1], row.names = 1, check.names = FALSE))
set.seed(as.integer(args[14]))
out <- scTenifoldKnk(
  countMatrix = mat, gKO = args[3], qc = as.logical(args[4]),
  qc_minLSize = as.integer(args[5]), qc_minCells = as.integer(args[6]),
  nc_nNet = as.integer(args[7]), nc_nCells = as.integer(args[8]),
  nc_nComp = as.integer(args[9]), nc_q = as.numeric(args[10]),
  td_K = as.integer(args[11]), ma_nDim = as.integer(args[12]),
  nCores = as.integer(args[13])
)
write.csv(out$diffRegulation, args[2], row.names = FALSE, quote = FALSE)
