# R Enhanced Plotting Dependencies

## 1. Overview

OmicsClaw R Enhanced plotting requires specific R packages to generate
publication-quality figures via ggplot2 and ComplexHeatmap. The
`OMICSCLAW_R_LIBS` environment variable points to a dedicated library
directory (under `$CONDA_PREFIX/lib/R/omicsclaw-library`) that is
searched first, allowing version pinning that shadows conda-managed R
packages.

## 2. Prerequisites

- R must be installed (4.x). Check: `Rscript --version`
- Active conda environment: `conda activate <your_env>`
- `OMICSCLAW_R_LIBS` is set automatically by `RScriptRunner` when conda is active

## 3. Core Packages (required for all R Enhanced plots)

```r
# Run in R or Rscript -e "..."
r_libs <- Sys.getenv("OMICSCLAW_R_LIBS")
if (nchar(r_libs) == 0) stop("OMICSCLAW_R_LIBS not set -- activate conda env first")

# ggplot2 MUST be pinned to 3.5.2 -- 4.0.2 breaks the + operator (S7 migration)
# Do NOT use install.packages("ggplot2") -- that installs 4.0.x
install.packages(
  "https://cran.r-project.org/src/contrib/Archive/ggplot2/ggplot2_3.5.2.tar.gz",
  repos = NULL, type = "source", lib = r_libs
)

# Other core dependencies
install.packages(c("scales", "RColorBrewer", "viridis", "ggrepel"), lib = r_libs)

# Verify pin worked:
# Rscript -e '.libPaths(c(Sys.getenv("OMICSCLAW_R_LIBS"), .libPaths())); packageVersion("ggplot2")'
# Must print: [1] '3.5.2'   -- NOT 4.0.x
```

## 4. ComplexHeatmap (for marker heatmaps and DE heatmaps)

```r
r_libs <- Sys.getenv("OMICSCLAW_R_LIBS")
if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager", lib = r_libs)
BiocManager::install("ComplexHeatmap", lib = r_libs, update = FALSE, ask = FALSE)
```

## 5. magick (for image processing -- required by some renderers)

magick requires system library libmagick++-dev. If you see linker errors:

```bash
# Ubuntu/Debian
sudo apt-get install -y libmagick++-dev

# Then install from source with the linker flag:
LIBRARY_PATH=/usr/lib/x86_64-linux-gnu Rscript -e 'install.packages("magick", lib=Sys.getenv("OMICSCLAW_R_LIBS"), type="source")'
```

If system install is not possible, magick-dependent renderers will warn and skip --
other renderers continue normally.

## 6. monocle3 (for sc-pseudotime --method monocle3_r)

monocle3 is on GitHub (not CRAN). Required for LineagePlot/DynamicPlot renderers.

```r
r_libs <- Sys.getenv("OMICSCLAW_R_LIBS")
# Dependencies
if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager", lib = r_libs)
BiocManager::install(c("BiocGenerics", "DelayedArray", "DelayedMatrixStats",
                        "limma", "lme4", "S4Vectors", "SingleCellExperiment",
                        "SummarizedExperiment", "batchelor", "HDF5Array",
                        "terra", "ggrastr"), lib = r_libs, update = FALSE, ask = FALSE)
# leidenbase from CRAN
install.packages("leidenbase", lib = r_libs)
# monocle3 from GitHub
if (!requireNamespace("remotes", quietly = TRUE))
    install.packages("remotes", lib = r_libs)
remotes::install_github("cole-trapnell-lab/monocle3", lib = r_libs)
```

## 7. GSVA (for sc-enrichment --method gsva_r)

```r
r_libs <- Sys.getenv("OMICSCLAW_R_LIBS")
if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager", lib = r_libs)
BiocManager::install("GSVA", lib = r_libs, update = FALSE, ask = FALSE)
```

## 8. clusterProfiler / fgsea (for sc-enrichment --method gsea_r)

Already installed as part of Phase 15. Verify:

```r
Rscript -e 'library(clusterProfiler); library(fgsea); cat("OK\n")'
```

If missing:

```r
r_libs <- Sys.getenv("OMICSCLAW_R_LIBS")
BiocManager::install(c("clusterProfiler", "fgsea"), lib = r_libs, update = FALSE, ask = FALSE)
```

## 9. Troubleshooting

### ggplot2 + operator error: "non-numeric argument to binary operator"

Cause: ggplot2 4.0.x S7 migration broke ggproto + operator.
Fix: Pin 3.5.2 per Section 3 above.
Verify: `packageVersion("ggplot2")` must return `3.5.2`.

### "there is no package called 'X'"

Cause: OMICSCLAW_R_LIBS not in .libPaths() when R script runs.
Fix: Ensure conda env is active. RScriptRunner sets R_LIBS_USER automatically.
Manual check: `Rscript -e 'cat(.libPaths(), sep="\n")'` -- first entry should be omicsclaw-library.

### R Enhanced plots produce warnings but no PNG

Expected for skills that do not export embedding CSVs to figure_data/. The R renderer
gracefully warns and skips -- Python figures are unaffected.

### monocle3 install fails on BiocGenerics version conflict

Use `ask = FALSE, force = TRUE` in BiocManager::install() to allow updates.

## 10. Minimal install (just ggplot2 + ComplexHeatmap for most plots)

```bash
# One-liner for CI or fresh machines:
Rscript -e '
r_libs <- Sys.getenv("OMICSCLAW_R_LIBS")
if (nchar(r_libs) == 0) stop("Set OMICSCLAW_R_LIBS or activate conda env")
install.packages("https://cran.r-project.org/src/contrib/Archive/ggplot2/ggplot2_3.5.2.tar.gz",
  repos=NULL, type="source", lib=r_libs)
install.packages(c("scales","RColorBrewer","viridis","ggrepel"), lib=r_libs)
if (!requireNamespace("BiocManager",quietly=TRUE)) install.packages("BiocManager",lib=r_libs)
BiocManager::install("ComplexHeatmap", lib=r_libs, update=FALSE, ask=FALSE)
cat("Core R Enhanced packages installed\n")
'
```

---
*Last updated: Phase 18 (2026-04-11). Based on real install experience from Phases 13-17.*
