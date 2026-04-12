# correlation.R -- Feature correlation scatter renderer for OmicsClaw R Enhanced
# Reads: figure_data/gene_expression.csv
# Provides: plot_feature_cor
# Registered in: registry.R

# ---- Function: plot_feature_cor ----

#' Two-feature correlation scatter plot with regression line and annotation.
#'
#' Reads gene_expression.csv (long format: cell_id, gene, expression), pivots
#' to wide format for 2 selected genes, and produces a scatter plot with linear
#' regression line and correlation coefficient + p-value annotation.
#'
#' @param data_dir Character. Directory containing CSV files.
#' @param out_path Character. Output PNG path.
#' @param params Named list. Optional: features (comma-separated gene pair,
#'   default first 2 genes in CSV), cor_method ("pearson" or "spearman",
#'   default "pearson").
plot_feature_cor <- function(data_dir, out_path, params) {
  tryCatch({
    csv_path <- file.path(data_dir, "gene_expression.csv")
    if (!file.exists(csv_path)) {
      stop("gene_expression.csv not found in ", data_dir)
    }

    df <- read.csv(csv_path, stringsAsFactors = FALSE)
    if (nrow(df) == 0) stop("Empty gene_expression.csv")

    # Parse parameters
    cor_method <- params[["cor_method"]] %||% "pearson"
    if (!cor_method %in% c("pearson", "spearman")) cor_method <- "pearson"

    features_str <- params[["features"]] %||% NULL
    all_genes <- unique(df$gene)

    if (!is.null(features_str)) {
      features <- trimws(unlist(strsplit(features_str, ",")))
      # Use only first 2 genes
      if (length(features) > 2) features <- features[1:2]
    } else {
      features <- all_genes
    }

    if (length(features) < 2) {
      stop("Need at least 2 genes for correlation plot. Found: ",
           paste(features, collapse = ", "))
    }

    gene1 <- features[1]
    gene2 <- features[2]

    # Filter to the 2 genes of interest
    df_sub <- df[df$gene %in% c(gene1, gene2), ]
    if (nrow(df_sub) == 0) {
      stop("No data for genes: ", gene1, ", ", gene2)
    }

    # Pivot to wide format: one column per gene, rows = cell_id
    wide_df <- reshape(
      df_sub,
      idvar = "cell_id",
      timevar = "gene",
      direction = "wide"
    )
    # reshape names columns as expression.GeneA, expression.GeneB
    col1 <- paste0("expression.", gene1)
    col2 <- paste0("expression.", gene2)

    if (!col1 %in% colnames(wide_df) || !col2 %in% colnames(wide_df)) {
      stop("Pivot failed: expected columns ", col1, " and ", col2)
    }

    # Remove rows with NA in either gene
    complete_rows <- complete.cases(wide_df[, c(col1, col2)])
    wide_df <- wide_df[complete_rows, ]

    if (nrow(wide_df) < 3) {
      stop("Fewer than 3 cells have values for both ", gene1, " and ", gene2)
    }

    # Compute correlation
    x_vals <- wide_df[[col1]]
    y_vals <- wide_df[[col2]]
    cor_val <- cor(x_vals, y_vals, method = cor_method, use = "complete.obs")
    cor_test <- cor.test(x_vals, y_vals, method = cor_method)
    p_val <- cor_test$p.value

    # Build scatter plot
    p <- ggplot(wide_df, aes(x = .data[[col1]], y = .data[[col2]])) +
      geom_point(alpha = 0.3, size = 1, color = "#377EB8") +
      geom_smooth(method = "lm", se = TRUE, color = "#E41A1C",
                  linewidth = 0.8, formula = y ~ x) +
      annotate(
        "text",
        x = min(x_vals, na.rm = TRUE),
        y = max(y_vals, na.rm = TRUE),
        label = sprintf("r = %.3f\np = %.2e", cor_val, p_val),
        hjust = 0, vjust = 1, size = 4, fontface = "italic"
      ) +
      labs(
        x = paste0(gene1, " expression"),
        y = paste0(gene2, " expression"),
        title = paste0(gene1, " vs ", gene2, " correlation")
      ) +
      theme_omics()

    ggsave_standard(p, out_path, width = 7, height = 6)

  }, error = function(e) {
    cat("ERROR:", conditionMessage(e), "\n", file = stderr())
    quit(status = 1)
  })
}
