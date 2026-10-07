args <- commandArgs(trailingOnly=TRUE)
input <- args[1]
output <- args[2]
parametric <- as.logical(args[3])
suppressPackageStartupMessages(library(sva))
data <- as.matrix(Matrix::readMM(file.path(input, "matrix.mtx")))
rownames(data) <- readLines(file.path(input, "features.tsv"))
colnames(data) <- readLines(file.path(input, "barcodes.tsv"))
metadata <- read.csv(file.path(input, "obs.csv"), check.names=FALSE, stringsAsFactors=FALSE)
metadata <- metadata[match(colnames(data), metadata$sample), , drop=FALSE]
model <- if ("condition" %in% colnames(metadata)) model.matrix(~condition, data=metadata) else NULL
corrected <- ComBat(data, batch=metadata$batch, mod=model, par.prior=parametric)
write.csv(corrected, file.path(output, "corrected.csv"))
