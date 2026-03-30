# Functional Enrichment Analysis - Method Reference

Comprehensive code examples and workflow patterns for GSEA and ORA using clusterProfiler.

---

## Complete Standard Workflows

### Full GSEA Workflow with All Steps

Complete example showing all steps from loading DE results to exporting visualizations:

```r
# ============================================================================
# Complete GSEA Workflow
# ============================================================================

# Load required packages
library(clusterProfiler)
library(enrichplot)
library(msigdbr)
library(org.Hs.eg.db)  # or org.Mm.eg.db for mouse
library(ggplot2)
library(dplyr)

# Source helper scripts
source("scripts/load_de_results.R")
source("scripts/prepare_gene_lists.R")
source("scripts/get_msigdb_genesets.R")
source("scripts/run_gsea.R")
source("scripts/generate_plots.R")
source("scripts/export_results.R")

# Step 1: Load DE results
de_results <- load_de_results("path/to/de_results.csv")
cat("Loaded", nrow(de_results), "genes\n")

# Step 2: Create ranked gene list
ranked_genes <- create_ranked_list(de_results, method = "stat")
cat("Ranked gene list length:", length(ranked_genes), "\n")

# Step 3: Get gene set databases
term2gene <- get_msigdb_genesets(
    species = "human",
    categories = c("H", "KEGG")
)
cat("Gene sets retrieved:", length(unique(term2gene$gs_name)), "\n")

# Step 4: Run GSEA
gsea_result <- run_gsea(
    ranked_genes = ranked_genes,
    term2gene = term2gene,
    n_perm = 10000,
    min_size = 15,
    max_size = 500
)

# Check results
cat("Significant pathways (FDR < 0.05):",
    sum(gsea_result@result$p.adjust < 0.05), "\n")

# Step 5: Generate visualizations
p_dotplot <- generate_gsea_dotplot(gsea_result, top_n = 20)
p_running <- generate_gsea_running_plot(gsea_result, top_n = 4)

# Step 6: Export results
export_results(
    gsea_result = gsea_result,
    output_prefix = "enrichment"
)

# Step 7: Generate summary report
generate_summary(
    gsea_result = gsea_result,
    output_file = "enrichment_summary.md"
)

cat("\n✓ GSEA analysis complete!\n")
```

### Full GSEA + ORA Workflow

Complete example with both methods for cross-validation:

```r
# ============================================================================
# Complete GSEA + ORA Workflow
# ============================================================================

library(clusterProfiler)
library(enrichplot)
library(msigdbr)
library(org.Hs.eg.db)
library(ggplot2)
library(dplyr)

# Source scripts
source("scripts/load_de_results.R")
source("scripts/prepare_gene_lists.R")
source("scripts/get_msigdb_genesets.R")
source("scripts/run_gsea.R")
source("scripts/run_ora.R")
source("scripts/generate_plots.R")
source("scripts/export_results.R")

# Step 1: Load DE results
de_results <- load_de_results("path/to/de_results.csv")

# Step 2a: Create ranked gene list for GSEA
ranked_genes <- create_ranked_list(de_results, method = "stat")

# Step 2b: Filter significant genes for ORA
sig_genes <- filter_significant_genes(
    de_results,
    padj_thresh = 0.05,
    log2fc_thresh = 1.0
)

cat("Significant genes:\n")
cat("  Up-regulated:", length(sig_genes$up), "\n")
cat("  Down-regulated:", length(sig_genes$down), "\n")
cat("  Background:", length(sig_genes$background), "\n")

# Step 3: Get gene set databases
term2gene <- get_msigdb_genesets(
    species = "human",
    categories = c("H", "KEGG")
)

# Step 4a: Run GSEA
cat("\nRunning GSEA...\n")
gsea_result <- run_gsea(ranked_genes, term2gene, n_perm = 10000)
cat("GSEA significant pathways:",
    sum(gsea_result@result$p.adjust < 0.05), "\n")

# Step 4b: Run ORA for up-regulated genes
cat("\nRunning ORA (up-regulated)...\n")
ora_up <- run_ora(
    genes = sig_genes$up,
    term2gene = term2gene,
    background = sig_genes$background,
    direction = "upregulated"
)
cat("ORA up significant:",
    sum(ora_up@result$p.adjust < 0.05, na.rm = TRUE), "\n")

# Step 4c: Run ORA for down-regulated genes
cat("\nRunning ORA (down-regulated)...\n")
ora_down <- run_ora(
    genes = sig_genes$down,
    term2gene = term2gene,
    background = sig_genes$background,
    direction = "downregulated"
)
cat("ORA down significant:",
    sum(ora_down@result$p.adjust < 0.05, na.rm = TRUE), "\n")

# Step 5a: Generate GSEA plots
p_gsea_dot <- generate_gsea_dotplot(gsea_result, top_n = 20)
p_gsea_run <- generate_gsea_running_plot(gsea_result, top_n = 4)

# Step 5b: Generate ORA plots
p_ora_up <- generate_ora_barplot(ora_up, "Upregulated", top_n = 15)
p_ora_down <- generate_ora_barplot(ora_down, "Downregulated", top_n = 15)

# Step 6: Export all results
export_results(
    gsea_result = gsea_result,
    ora_up = ora_up,
    ora_down = ora_down,
    output_prefix = "enrichment"
)

# Step 7: Generate comprehensive summary
generate_summary(
    gsea_result = gsea_result,
    ora_up = ora_up,
    ora_down = ora_down,
    output_file = "enrichment_summary.md"
)

cat("\n✓ GSEA + ORA analysis complete!\n")
```

---

## Common Usage Patterns

### Pattern 1: Quick GSEA with Default Settings

Minimal code for standard GSEA analysis:

```r
library(clusterProfiler)
source("scripts/load_de_results.R")
source("scripts/prepare_gene_lists.R")
source("scripts/get_msigdb_genesets.R")
source("scripts/run_gsea.R")
source("scripts/export_results.R")

# Load and prepare
de_results <- load_de_results("de_results.csv")
ranked_genes <- create_ranked_list(de_results)

# Get gene sets and run GSEA
term2gene <- get_msigdb_genesets("human", c("H", "KEGG"))
gsea_result <- run_gsea(ranked_genes, term2gene)

# Export
export_results(gsea_result, output_prefix = "enrichment")

# View top results
head(gsea_result@result, 10)
```

### Pattern 2: GSEA + ORA for Validation

Cross-validate findings with both methods:

```r
# Prepare both ranked list and filtered genes
ranked_genes <- create_ranked_list(de_results)
sig_genes <- filter_significant_genes(
    de_results,
    padj_thresh = 0.05,
    log2fc_thresh = 1.0
)

# Get gene sets
term2gene <- get_msigdb_genesets("human", c("H", "KEGG"))

# Run GSEA
gsea_result <- run_gsea(ranked_genes, term2gene)

# Run ORA
ora_up <- run_ora(
    sig_genes$up,
    term2gene,
    sig_genes$background,
    direction = "upregulated"
)
ora_down <- run_ora(
    sig_genes$down,
    term2gene,
    sig_genes$background,
    direction = "downregulated"
)

# Export both
export_results(gsea_result, ora_up, ora_down, output_prefix = "enrichment")

# Compare results
common_pathways <- intersect(
    gsea_result@result$ID[gsea_result@result$p.adjust < 0.05],
    ora_up@result$ID[ora_up@result$p.adjust < 0.05]
)
cat("Pathways significant in both methods:", length(common_pathways), "\n")
```

### Pattern 3: GO Biological Processes Analysis

Comprehensive analysis with Gene Ontology:

```r
# Use GO:BP for detailed biological processes
term2gene <- get_msigdb_genesets("human", categories = "GO:BP")

# Run GSEA (may take longer with many gene sets)
gsea_result <- run_gsea(
    ranked_genes,
    term2gene,
    n_perm = 10000,
    min_size = 15,
    max_size = 500
)

# Filter to significant results
gsea_significant <- gsea_result@result %>%
    filter(p.adjust < 0.05) %>%
    arrange(p.adjust) %>%
    head(50)  # Top 50 most significant

# Simplify redundant GO terms
gsea_simplified <- clusterProfiler::simplify(
    gsea_result,
    cutoff = 0.7,
    by = "p.adjust",
    select_fun = min
)

# Export simplified results
write.csv(
    gsea_simplified@result,
    "enrichment_gsea_gobp_simplified.csv",
    row.names = FALSE
)
```

### Pattern 4: Cancer-Specific Enrichment

Specialized analysis for cancer research:

```r
# Use Hallmark + Oncogenic signatures
term2gene <- get_msigdb_genesets("human", categories = c("H", "C6"))

# Run GSEA
gsea_result <- run_gsea(ranked_genes, term2gene)

# Focus on cancer pathways
cancer_pathways <- gsea_result@result %>%
    filter(grepl("HALLMARK_|^C6_", ID)) %>%
    filter(p.adjust < 0.05) %>%
    arrange(NES)

# Separate activated vs suppressed
activated <- cancer_pathways %>% filter(NES > 0)
suppressed <- cancer_pathways %>% filter(NES < 0)

cat("Activated cancer pathways:", nrow(activated), "\n")
cat("Suppressed cancer pathways:", nrow(suppressed), "\n")

# Export cancer-specific results
write.csv(
    cancer_pathways,
    "enrichment_cancer_specific.csv",
    row.names = FALSE
)
```

### Pattern 5: Immunology-Focused Analysis

Specialized for immune cell analysis:

```r
# Use Hallmark + Immunologic signatures
term2gene <- get_msigdb_genesets("human", categories = c("H", "C7"))

# Run GSEA
gsea_result <- run_gsea(ranked_genes, term2gene)

# Filter to immune-related results
immune_pathways <- gsea_result@result %>%
    filter(p.adjust < 0.05) %>%
    arrange(NES)

# Identify cell type signatures
cell_types <- immune_pathways %>%
    filter(grepl("GSE", ID))  # Many C7 signatures from GEO

# Generate immune-focused plot
p_immune <- enrichplot::dotplot(
    gsea_result,
    showCategory = 30,
    title = "Immune Pathway Enrichment"
) +
    theme(axis.text.y = element_text(size = 8))

ggsave("enrichment_immune_dotplot.png", p_immune,
       width = 10, height = 12, dpi = 300)
ggsave("enrichment_immune_dotplot.svg", p_immune,
       width = 10, height = 12)
```

### Pattern 6: Mouse Data Analysis

Identical workflow for mouse data:

```r
# All functions work with mouse - just specify species
library(org.Mm.eg.db)  # Mouse annotation

# Load mouse DE results
de_results <- load_de_results("mouse_de_results.csv")

# Create ranked list
ranked_genes <- create_ranked_list(de_results)

# Get mouse gene sets
term2gene <- get_msigdb_genesets(
    species = "mouse",
    categories = c("H", "KEGG")
)

# Run GSEA
gsea_result <- run_gsea(ranked_genes, term2gene)

# Export
export_results(gsea_result, output_prefix = "mouse_enrichment")
```

### Pattern 7: Custom Gene Set Analysis

Use custom gene sets from literature or databases:

```r
# Create custom term2gene data frame
# Format: gs_name, gene_symbol
custom_genesets <- data.frame(
    gs_name = c(
        rep("MyPathway1", 10),
        rep("MyPathway2", 15),
        rep("MyPathway3", 20)
    ),
    gene_symbol = c(
        # MyPathway1 genes
        "TP53", "BRCA1", "BRCA2", "ATM", "CHEK2",
        "PTEN", "RB1", "MLH1", "MSH2", "APC",
        # MyPathway2 genes
        "MYC", "KRAS", "NRAS", "BRAF", "PIK3CA",
        "AKT1", "MTOR", "EGFR", "ERBB2", "MET",
        "FGFR1", "FGFR2", "CDK4", "CCND1", "MDM2",
        # MyPathway3 genes
        "TNF", "IL6", "IL1B", "IFNG", "TGFB1",
        "CCL2", "CCL5", "CXCL8", "CXCL10", "IL10",
        "STAT3", "STAT1", "NFKB1", "JUN", "FOS",
        "MAPK1", "MAPK3", "JAK2", "TLR4", "CD44"
    )
)

# Run GSEA with custom gene sets
gsea_custom <- run_gsea(ranked_genes, custom_genesets)

# Examine results
print(gsea_custom@result)
```

### Pattern 8: Comparing Multiple Contrasts

Analyze enrichment across multiple DE comparisons:

```r
# Load multiple DE results
contrasts <- list(
    TreatmentVsControl = load_de_results("treatment_vs_control.csv"),
    TimePoint2Vs1 = load_de_results("timepoint2_vs_1.csv"),
    TimePoint3Vs1 = load_de_results("timepoint3_vs_1.csv")
)

# Create ranked lists for each
ranked_lists <- lapply(contrasts, create_ranked_list)

# Get gene sets once
term2gene <- get_msigdb_genesets("human", c("H", "KEGG"))

# Run GSEA for each contrast
gsea_results <- lapply(ranked_lists, function(ranked_genes) {
    run_gsea(ranked_genes, term2gene, n_perm = 10000)
})

# Compare significant pathways across contrasts
sig_pathways <- lapply(gsea_results, function(res) {
    res@result %>%
        filter(p.adjust < 0.05) %>%
        pull(ID)
})

# Find common pathways
common <- Reduce(intersect, sig_pathways)
cat("Pathways significant in all contrasts:", length(common), "\n")

# Export each
for (name in names(gsea_results)) {
    export_results(
        gsea_results[[name]],
        output_prefix = paste0("enrichment_", name)
    )
}
```

### Pattern 9: Advanced Visualization

Create publication-quality enrichment figures:

```r
# Generate all standard plots
p_dotplot <- generate_gsea_dotplot(gsea_result, top_n = 20)
p_running <- generate_gsea_running_plot(gsea_result, top_n = 4)

# Create enrichment map (pathway similarity network)
p_emap <- generate_emap(gsea_result, top_n = 30)

# Create concept network (gene-pathway connections)
p_cnet <- generate_cnetplot(gsea_result, ranked_genes, top_n = 5)

# Create ridge plot (expression distribution)
p_ridge <- generate_ridgeplot(gsea_result, top_n = 15)

# Save all plots
plots <- list(
    dotplot = p_dotplot,
    running = p_running,
    emap = p_emap,
    cnet = p_cnet,
    ridge = p_ridge
)

for (name in names(plots)) {
    ggsave(
        paste0("enrichment_", name, ".png"),
        plots[[name]],
        width = 10,
        height = 8,
        dpi = 300
    )
    ggsave(
        paste0("enrichment_", name, ".svg"),
        plots[[name]],
        width = 10,
        height = 8
    )
}
```

### Pattern 10: Filtering and Subsetting Results

Extract specific results of interest:

```r
# Get GSEA results
gsea_result <- run_gsea(ranked_genes, term2gene)

# Filter to significant only
significant <- gsea_result@result %>%
    filter(p.adjust < 0.05)

# Separate by activation status
activated <- significant %>%
    filter(NES > 0) %>%
    arrange(desc(NES))

suppressed <- significant %>%
    filter(NES < 0) %>%
    arrange(NES)

# Filter by keyword
metabolism <- significant %>%
    filter(grepl("METABOLISM|GLYCOLYSIS|OXIDATIVE", Description))

signaling <- significant %>%
    filter(grepl("SIGNALING|PATHWAY", Description))

# Export filtered results
write.csv(activated, "enrichment_activated_pathways.csv", row.names = FALSE)
write.csv(suppressed, "enrichment_suppressed_pathways.csv", row.names = FALSE)
write.csv(metabolism, "enrichment_metabolism.csv", row.names = FALSE)
write.csv(signaling, "enrichment_signaling.csv", row.names = FALSE)

# Get leading edge genes for top pathway
top_pathway <- gsea_result@result[1, ]
leading_edge_genes <- strsplit(top_pathway$core_enrichment, "/")[[1]]

# Extract expression data for leading edge genes
leading_edge_de <- de_results %>%
    filter(gene %in% leading_edge_genes)

write.csv(
    leading_edge_de,
    paste0("leading_edge_", gsub("HALLMARK_|KEGG_", "", top_pathway$ID), ".csv"),
    row.names = FALSE
)
```

---

## Alternative Ranking Methods

### Using Different Ranking Metrics

```r
# Method 1: Test statistic (best, default for DESeq2)
ranked_stat <- create_ranked_list(de_results, method = "stat")

# Method 2: Signed -log10(pvalue)
ranked_pval <- create_ranked_list(de_results, method = "pvalue")

# Method 3: Signed -log10(padj)
ranked_padj <- create_ranked_list(de_results, method = "padj")

# Method 4: log2FC only (not recommended)
ranked_fc <- create_ranked_list(de_results, method = "log2fc")

# Compare ranking methods
term2gene <- get_msigdb_genesets("human", c("H"))

gsea_stat <- run_gsea(ranked_stat, term2gene, n_perm = 1000)
gsea_pval <- run_gsea(ranked_pval, term2gene, n_perm = 1000)
gsea_padj <- run_gsea(ranked_padj, term2gene, n_perm = 1000)

cat("Significant pathways:\n")
cat("  Test statistic:", sum(gsea_stat@result$p.adjust < 0.05), "\n")
cat("  -log10(pvalue):", sum(gsea_pval@result$p.adjust < 0.05), "\n")
cat("  -log10(padj):", sum(gsea_padj@result$p.adjust < 0.05), "\n")
```

### Custom Ranking Function

```r
# Create custom ranking based on combined criteria
create_custom_ranking <- function(de_results) {
    de_results %>%
        mutate(
            # Custom score: combines fold change and significance
            rank_score = log2FoldChange * -log10(pvalue)
        ) %>%
        arrange(desc(rank_score)) %>%
        pull(rank_score, name = gene)
}

# Use custom ranking
custom_ranked <- create_custom_ranking(de_results)
gsea_custom <- run_gsea(custom_ranked, term2gene)
```

---

## Troubleshooting Workflows

### Handling No Significant Results

```r
# If GSEA returns no significant results, try:

# 1. Relax FDR threshold
relaxed <- gsea_result@result %>%
    filter(p.adjust < 0.1)  # Instead of 0.05

# 2. Use larger gene set databases
term2gene_go <- get_msigdb_genesets("human", "GO:BP")
gsea_go <- run_gsea(ranked_genes, term2gene_go)

# 3. Check if ranking is appropriate
summary(ranked_genes)  # Should have wide range of values

# 4. Try different ranking method
ranked_pval <- create_ranked_list(de_results, method = "pvalue")
gsea_pval <- run_gsea(ranked_pval, term2gene)

# 5. Reduce minimum gene set size
gsea_smaller <- run_gsea(ranked_genes, term2gene, min_size = 10)
```

### Handling Gene Symbol Mismatches

```r
# Check which genes are recognized
genes_in_db <- unique(term2gene$gene_symbol)
genes_in_data <- names(ranked_genes)

# Find unmatched genes
unmatched <- setdiff(genes_in_data, genes_in_db)
cat("Unmatched genes:", length(unmatched), "\n")

# Show examples
head(unmatched, 20)

# If many mismatches, may need ID conversion
# Use org.Hs.eg.db for conversion if needed
library(org.Hs.eg.db)

# Convert from Ensembl to Symbol (example)
converted <- AnnotationDbi::mapIds(
    org.Hs.eg.db,
    keys = genes_in_data,
    keytype = "ENSEMBL",
    column = "SYMBOL",
    multiVals = "first"
)
```

---

## Performance Optimization

### Speed Up GSEA

```r
# For faster iteration during development:

# 1. Use fewer permutations for testing
gsea_test <- run_gsea(ranked_genes, term2gene, n_perm = 1000)

# 2. Use smaller gene set collection
term2gene_small <- get_msigdb_genesets("human", "H")  # Only Hallmark

# 3. Filter gene sets by size
term2gene_filtered <- term2gene %>%
    group_by(gs_name) %>%
    filter(n() >= 15, n() <= 200) %>%
    ungroup()

# 4. Use parallel processing (if available in your implementation)
# This depends on your run_gsea() implementation
```

---

## Integration with Other Tools

### Export for Cytoscape

```r
# Create enrichment map for Cytoscape
enrichment_map_data <- gsea_result@result %>%
    filter(p.adjust < 0.05) %>%
    select(ID, Description, NES, p.adjust, core_enrichment)

write.table(
    enrichment_map_data,
    "cytoscape_enrichment_map.txt",
    sep = "\t",
    quote = FALSE,
    row.names = FALSE
)
```

### Export for IPA or Other Tools

```r
# Format for Ingenuity Pathway Analysis
ipa_format <- significant %>%
    select(
        `Pathway Name` = Description,
        `p-value` = pvalue,
        `Adjusted p-value` = p.adjust,
        `NES` = NES,
        `Leading Edge Genes` = core_enrichment
    )

write.csv(ipa_format, "enrichment_for_ipa.csv", row.names = FALSE)
```

---

## References

- Yu et al. (2012) OMICS - clusterProfiler package
- Subramanian et al. (2005) PNAS - GSEA method
- Liberzon et al. (2015) Cell Systems - MSigDB
- Korotkevich et al. (2016) bioRxiv - Fast GSEA (fgsea)


---
