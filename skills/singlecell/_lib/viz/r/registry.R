# registry.R -- CLI entry point for all OmicsClaw R Enhanced plots
#
# Invocation from Python:
#   Rscript registry.R <renderer_name> <data_dir> <output_png_path> [key=value ...]
#
# All renderers are registered in R_PLOT_REGISTRY (named list).
# Python always calls this single entry point via RScriptRunner.

# ---- Script-directory resolution ----
# Must work when called as: Rscript /abs/path/to/registry.R
.get_script_dir <- function() {
  args <- commandArgs(FALSE)
  file_flag <- grep("--file=", args, value = TRUE)
  if (length(file_flag) > 0) {
    return(dirname(normalizePath(sub("--file=", "", file_flag[1]))))
  }
  # Fallback: use current working directory
  getwd()
}
script_dir <- .get_script_dir()

# ---- Source common.R first (absolute path) ----
source(file.path(script_dir, "common.R"))
source(file.path(script_dir, "embedding.R"))
source(file.path(script_dir, "markers.R"))
source(file.path(script_dir, "pseudotime.R"))
source(file.path(script_dir, "enrichment.R"))
source(file.path(script_dir, "velocity.R"))
source(file.path(script_dir, "communication.R"))
source(file.path(script_dir, "de.R"))
source(file.path(script_dir, "stat.R"))
source(file.path(script_dir, "density.R"))
source(file.path(script_dir, "sankey.R"))
source(file.path(script_dir, "correlation.R"))
source(file.path(script_dir, "cytotrace.R"))

# ---- Test stub renderer ----
# Minimal ggplot2 scatter that proves the Python -> R round-trip works.
# Does NOT read any CSV -- generates synthetic data.
plot_test_scatter <- function(data_dir, out_path, params) {
  set.seed(42)
  df <- data.frame(
    x     = rnorm(50),
    y     = rnorm(50),
    group = sample(letters[1:3], 50, replace = TRUE)
  )
  p <- ggplot(df, aes(x = x, y = y, color = group)) +
    geom_point(size = 2, alpha = 0.8) +
    scale_color_manual(values = omics_palette(3)) +
    theme_omics() +
    labs(
      title = "R Enhanced round-trip test",
      x     = "X",
      y     = "Y",
      color = "Group"
    )
  ggsave_standard(p, out_path)
}

# ---- Registry ----
R_PLOT_REGISTRY <- list(
  plot_test_scatter       = plot_test_scatter,
  plot_embedding_discrete = plot_embedding_discrete,
  plot_embedding_feature  = plot_embedding_feature,
  plot_marker_heatmap     = plot_marker_heatmap,
  plot_pseudotime_lineage = plot_pseudotime_lineage,
  plot_pseudotime_dynamic = plot_pseudotime_dynamic,
  plot_enrichment_bar     = plot_enrichment_bar,
  plot_gsea_mountain      = plot_gsea_mountain,
  plot_gsea_nes_heatmap   = plot_gsea_nes_heatmap,
  plot_velocity           = plot_velocity,
  plot_de_volcano         = plot_de_volcano,
  plot_de_heatmap         = plot_de_heatmap,
  plot_ccc_heatmap           = plot_ccc_heatmap,
  plot_ccc_network           = plot_ccc_network,
  plot_feature_violin        = plot_feature_violin,
  plot_feature_boxplot       = plot_feature_boxplot,
  plot_cell_barplot          = plot_cell_barplot,
  plot_cell_proportion       = plot_cell_proportion,
  plot_enrichment_dotplot    = plot_enrichment_dotplot,
  plot_enrichment_lollipop   = plot_enrichment_lollipop,
  plot_pseudotime_heatmap    = plot_pseudotime_heatmap,
  plot_ccc_bubble            = plot_ccc_bubble,
  plot_cell_density          = plot_cell_density,
  plot_proportion_test       = plot_proportion_test,
  plot_cell_sankey           = plot_cell_sankey,
  plot_ccc_stat_bar          = plot_ccc_stat_bar,
  plot_ccc_stat_violin       = plot_ccc_stat_violin,
  plot_ccc_stat_scatter      = plot_ccc_stat_scatter,
  plot_feature_cor           = plot_feature_cor,
  plot_cytotrace_boxplot     = plot_cytotrace_boxplot
)

# ---- CLI dispatcher (runs only when script is invoked directly) ----
if (!interactive()) {
  args <- commandArgs(trailingOnly = TRUE)
  if (length(args) < 3) {
    cat("Usage: Rscript registry.R <renderer> <data_dir> <out_path> [key=value ...]\n",
        file = stderr())
    quit(status = 1)
  }
  renderer_name <- args[1]
  data_dir      <- args[2]
  out_path      <- args[3]
  params        <- if (length(args) >= 4) parse_kv(args[4:length(args)]) else list()

  fn <- R_PLOT_REGISTRY[[renderer_name]]
  if (is.null(fn)) {
    cat("ERROR: Unknown renderer '", renderer_name, "'. Available: ",
        paste(names(R_PLOT_REGISTRY), collapse = ", "), "\n",
        sep = "", file = stderr())
    quit(status = 1)
  }

  tryCatch({
    fn(data_dir, out_path, params)
    cat("SUCCESS:", renderer_name, "->", out_path, "\n")
  }, error = function(e) {
    cat("ERROR in ", renderer_name, ": ", conditionMessage(e), "\n",
        sep = "", file = stderr())
    quit(status = 1)
  })
}
