#!/usr/bin/env Rscript
#
# check_packages.R — Check whether R packages are installed.
#
# Usage:
#   Rscript check_packages.R pkg1 pkg2 pkg3 ...
#
# Output (stdout):
#   JSON object mapping package name -> true/false
#   e.g. {"DESeq2": true, "Seurat": true, "SPARK": false}
#

args <- commandArgs(trailingOnly = TRUE)

if (length(args) == 0) {
    cat("Usage: Rscript check_packages.R <pkg1> [pkg2] ...\n", file = stderr())
    quit(status = 1)
}

results <- list()
for (pkg in args) {
    results[[pkg]] <- requireNamespace(pkg, quietly = TRUE)
}

# Output as JSON (without external dependency)
entries <- vapply(names(results), function(k) {
    sprintf('"%s": %s', k, tolower(as.character(results[[k]])))
}, character(1))

cat("{", paste(entries, collapse = ", "), "}\n", sep = "")
