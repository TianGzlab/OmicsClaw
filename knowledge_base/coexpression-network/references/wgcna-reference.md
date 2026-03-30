# WGCNA Complete Reference

This document provides detailed code examples and explanations for each step of the WGCNA workflow. Use these examples to understand the underlying code and adapt workflows to your specific needs.

**For standard workflows:** Use the scripts in `scripts/` directory via `source()` (recommended).

**For custom workflows:** Read this guide to understand parameters and adapt code to your specific requirements.

---

## Table of Contents

1. [Data Preparation](#data-preparation)
2. [Soft Power Selection](#soft-power-selection)
3. [Network Construction](#network-construction)
4. [Module-Trait Correlation](#module-trait-correlation)
5. [Hub Gene Identification](#hub-gene-identification)
6. [Functional Enrichment](#functional-enrichment)
7. [Visualization](#visualization)
8. [Complete Workflow Example](#complete-workflow-example)

---

## Data Preparation

### Loading and Filtering Expression Data

```r
library(WGCNA)
allowWGCNAThreads()

# Load expression data (genes × samples)
expr_data <- read.csv("normalized_expression.csv", row.names = 1)

# Load metadata
meta_data <- read.csv("sample_metadata.csv", row.names = 1)

# Transpose to WGCNA format (samples × genes)
datExpr0 <- as.data.frame(t(expr_data))

# Check data quality
gsg <- goodSamplesGenes(datExpr0, verbose = 3)

if (!gsg$allOK) {
  # Remove problematic genes/samples
  if (sum(!gsg$goodGenes) > 0)
    cat("Removing", sum(!gsg$goodGenes), "genes\n")
  if (sum(!gsg$goodSamples) > 0)
    cat("Removing", sum(!gsg$goodSamples), "samples\n")

  datExpr0 <- datExpr0[gsg$goodSamples, gsg$goodGenes]
}
```

### Selecting Variable Genes

```r
# Calculate coefficient of variation for each gene
gene_cv <- apply(datExpr0, 2, function(x) sd(x) / mean(x))

# Select top N most variable genes
top_n <- 5000
top_genes <- names(sort(gene_cv, decreasing = TRUE))[1:top_n]
datExpr <- datExpr0[, top_genes]

cat("Retained", ncol(datExpr), "most variable genes\n")
```

### Sample Outlier Detection

```r
# Hierarchical clustering to detect outliers
sampleTree <- hclust(dist(datExpr), method = "average")

# Plot sample dendrogram
plot(sampleTree, main = "Sample Clustering", sub = "", xlab = "",
     cex.lab = 1.5, cex.axis = 1.5, cex.main = 2)

# Optional: Cut tree to remove outliers
# Adjust cutHeight based on your dendrogram
cutHeight <- 15000
abline(h = cutHeight, col = "red")
clust <- cutreeStatic(sampleTree, cutHeight = cutHeight, minSize = 10)
keepSamples <- (clust == 1)
datExpr <- datExpr[keepSamples, ]
meta <- meta[keepSamples, ]
```

---

## Soft Power Selection

### Testing Multiple Powers

```r
# Choose a set of soft-thresholding powers
powers <- c(1:20)

# Call the network topology analysis function
sft <- pickSoftThreshold(datExpr, powerVector = powers, verbose = 5)

# Plot the results
par(mfrow = c(1, 2))

# Scale-free topology fit index as a function of the soft-thresholding power
plot(sft$fitIndices[, 1], -sign(sft$fitIndices[, 3]) * sft$fitIndices[, 2],
     xlab = "Soft Threshold (power)",
     ylab = "Scale Free Topology Model Fit, signed R^2",
     type = "n", main = "Scale Independence")

text(sft$fitIndices[, 1], -sign(sft$fitIndices[, 3]) * sft$fitIndices[, 2],
     labels = powers, cex = 0.9, col = "red")

# Horizontal line at R^2 = 0.85
abline(h = 0.85, col = "blue")

# Mean connectivity as a function of the soft-thresholding power
plot(sft$fitIndices[, 1], sft$fitIndices[, 5],
     xlab = "Soft Threshold (power)",
     ylab = "Mean Connectivity",
     type = "n", main = "Mean Connectivity")

text(sft$fitIndices[, 1], sft$fitIndices[, 5],
     labels = powers, cex = 0.9, col = "red")
```

### Choosing Power

```r
# Select power where R² first exceeds 0.85
power_threshold <- 0.85
selected_power <- min(sft$fitIndices$Power[sft$fitIndices$SFT.R.sq > power_threshold])

# If no power reaches threshold, use power with highest R²
if (is.infinite(selected_power)) {
  selected_power <- sft$fitIndices$Power[which.max(sft$fitIndices$SFT.R.sq)]
  cat("No power reached R² >", power_threshold, ". Using power", selected_power,
      "with R² =", max(sft$fitIndices$SFT.R.sq), "\n")
} else {
  cat("Selected power:", selected_power,
      "with R² =", sft$fitIndices$SFT.R.sq[selected_power], "\n")
}
```

---

## Network Construction

### One-Step Network Construction

```r
# One-step network construction and module detection
net <- blockwiseModules(
  datExpr,
  power = selected_power,
  TOMType = "signed",              # or "unsigned"
  minModuleSize = 30,              # minimum genes per module
  reassignThreshold = 0,           # don't reassign genes
  mergeCutHeight = 0.25,           # merge similar modules (lower = more merging)
  numericLabels = FALSE,            # use color labels
  pamRespectsDendro = FALSE,
  saveTOMs = FALSE,                # set TRUE to save TOM matrix (large file)
  verbose = 3
)

# Extract module colors
moduleColors <- net$colors

# Count modules
table(moduleColors)
```

### Network Type Comparison

```r
# Signed network (default, recommended)
# - Distinguishes positive and negative correlations
# - More biologically meaningful
net_signed <- blockwiseModules(datExpr, power = power, TOMType = "signed")

# Unsigned network
# - Treats positive and negative correlations the same
# - May be useful for some data types
net_unsigned <- blockwiseModules(datExpr, power = power, TOMType = "unsigned")

# Signed hybrid (middle ground)
# - Keeps negative correlations but weighs them less
net_hybrid <- blockwiseModules(datExpr, power = power, TOMType = "signed hybrid")
```

### Manual Two-Step Construction (Advanced)

```r
# Step 1: Calculate adjacency matrix
adjacency <- adjacency(datExpr, power = selected_power, type = "signed")

# Step 2: Transform adjacency to TOM
TOM <- TOMsimilarity(adjacency, TOMType = "signed")
dissTOM <- 1 - TOM

# Step 3: Hierarchical clustering
geneTree <- hclust(as.dist(dissTOM), method = "average")

# Step 4: Module identification
dynamicMods <- cutreeDynamic(dendro = geneTree, distM = dissTOM,
                              deepSplit = 2, pamRespectsDendro = FALSE,
                              minClusterSize = 30)

dynamicColors <- labels2colors(dynamicMods)

# Step 5: Merge similar modules
MEList <- moduleEigengenes(datExpr, colors = dynamicColors)
MEs <- MEList$eigengenes
MEDiss <- 1 - cor(MEs)
METree <- hclust(as.dist(MEDiss), method = "average")

# Choose merge height (0.25 = 75% similarity)
mergeHeight <- 0.25
abline(h = mergeHeight, col = "red")

merge <- mergeCloseModules(datExpr, dynamicColors, cutHeight = mergeHeight)
mergedColors <- merge$colors
mergedMEs <- merge$newMEs
```

---

## Module-Trait Correlation

### Calculating Correlations

```r
# Define module eigengenes
MEs <- moduleEigengenes(datExpr, moduleColors)$eigengenes

# Order modules by hierarchical clustering
MEs <- orderMEs(MEs)

# Prepare trait data (numeric matrix)
# For binary traits: 0/1 coding
# For continuous traits: use as-is
traits <- meta[, c("weight_g", "Glucose_mg_dl", "Triglycerides_mg_dl")]

# Calculate correlations
moduleTraitCor <- cor(MEs, traits, use = "p")
moduleTraitPvalue <- corPvalueStudent(moduleTraitCor, nrow(datExpr))

# Display correlations with p-values
textMatrix <- paste(signif(moduleTraitCor, 2), "\n(",
                    signif(moduleTraitPvalue, 1), ")", sep = "")
dim(textMatrix) <- dim(moduleTraitCor)

# Heatmap using ComplexHeatmap
library(ComplexHeatmap)
library(circlize)

# Color scale
col_fun <- colorRamp2(c(-1, 0, 1), c("blue", "white", "red"))

# Create heatmap
Heatmap(moduleTraitCor,
        name = "Correlation",
        col = col_fun,
        cell_fun = function(j, i, x, y, width, height, fill) {
          grid.text(textMatrix[i, j], x, y, gp = gpar(fontsize = 10))
        },
        cluster_rows = FALSE,
        cluster_columns = FALSE,
        row_names_side = "left",
        column_title = "Module-Trait Relationships")
```

### Gene Significance

```r
# Calculate gene significance for a specific trait
trait_of_interest <- traits$weight_g

geneModuleMembership <- as.data.frame(cor(datExpr, MEs, use = "p"))
MMPvalue <- as.data.frame(corPvalueStudent(
  as.matrix(geneModuleMembership), nrow(datExpr)))

geneTraitSignificance <- as.data.frame(cor(datExpr, trait_of_interest, use = "p"))
GSPvalue <- as.data.frame(corPvalueStudent(
  as.matrix(geneTraitSignificance), nrow(datExpr)))

# Focus on specific module
module <- "turquoise"
column <- match(module, gsub("ME", "", names(MEs)))
moduleGenes <- (moduleColors == module)

# Plot MM vs GS for this module
par(mfrow = c(1, 1))
verboseScatterplot(abs(geneModuleMembership[moduleGenes, column]),
                   abs(geneTraitSignificance[moduleGenes, 1]),
                   xlab = paste("Module Membership in", module, "module"),
                   ylab = "Gene significance for weight",
                   main = paste("Module membership vs. gene significance\n"),
                   cex.main = 1.2, cex.lab = 1.2, cex.axis = 1.2,
                   col = module)
```

---

## Hub Gene Identification

### Intramodular Connectivity

```r
# Calculate intramodular connectivity
Alldegrees <- intramodularConnectivity(adjacency, moduleColors)

# For each module, rank genes by connectivity
modules <- unique(moduleColors)
modules <- modules[modules != "grey"]

hub_genes_list <- list()

for (mod in modules) {
  # Get genes in this module
  inModule <- (moduleColors == mod)
  modGenes <- colnames(datExpr)[inModule]

  # Get connectivity for these genes
  modConnectivity <- Alldegrees[inModule, "kWithin"]
  names(modConnectivity) <- modGenes

  # Rank by connectivity
  modConnectivity_sorted <- sort(modConnectivity, decreasing = TRUE)

  # Top 10 hub genes
  hub_genes_list[[mod]] <- data.frame(
    gene = names(modConnectivity_sorted)[1:10],
    kWithin = modConnectivity_sorted[1:10],
    module = mod
  )
}

# Combine all hub genes
all_hubs <- do.call(rbind, hub_genes_list)
```

### Module Membership

```r
# Calculate module membership (MM)
geneModuleMembership <- as.data.frame(cor(datExpr, MEs, use = "p"))

# For a specific module
module <- "turquoise"
ME_col <- paste("ME", module, sep = "")
MM <- abs(geneModuleMembership[, ME_col])
names(MM) <- colnames(datExpr)

# Genes with high MM are hub genes
hub_threshold <- 0.8
hub_genes <- names(MM)[MM > hub_threshold]
cat("Module", module, "has", length(hub_genes), "hub genes (MM >", hub_threshold, ")\n")
```

---

## Functional Enrichment

### GO Enrichment

```r
library(clusterProfiler)
library(org.Hs.eg.db)  # or appropriate organism

# For a specific module
module <- "turquoise"
module_genes <- colnames(datExpr)[moduleColors == module]

# GO enrichment
ego <- enrichGO(
  gene = module_genes,
  OrgDb = org.Hs.eg.db,
  keyType = "SYMBOL",
  ont = "BP",              # or "MF", "CC", "ALL"
  pAdjustMethod = "BH",
  pvalueCutoff = 0.05,
  qvalueCutoff = 0.1,
  readable = TRUE
)

# View results
head(ego@result, 10)

# Plot
dotplot(ego, showCategory = 20)
barplot(ego, showCategory = 20)
```

### KEGG Pathway Enrichment

```r
# Convert symbols to Entrez IDs
gene_entrez <- bitr(module_genes, fromType = "SYMBOL",
                    toType = "ENTREZID", OrgDb = org.Hs.eg.db)

# KEGG enrichment
kk <- enrichKEGG(
  gene = gene_entrez$ENTREZID,
  organism = "hsa",        # hsa = human, mmu = mouse
  pvalueCutoff = 0.05,
  qvalueCutoff = 0.1
)

# View results
head(kk@result, 10)
```

---

## Visualization

All plots are saved as PNG and SVG for publication quality.

### Module Dendrogram

```r
# Plot dendrogram with module colors
plotDendroAndColors(geneTree, moduleColors,
                    "Module colors",
                    dendroLabels = FALSE,
                    hang = 0.03,
                    addGuide = TRUE,
                    guideHang = 0.05,
                    main = "Gene Dendrogram and Module Colors")
```

### Eigengene Heatmap with ComplexHeatmap

```r
library(ComplexHeatmap)
library(circlize)

# Scale eigengenes for visualization
MEs_scaled <- t(scale(t(MEs)))

# Sample annotation
ha_sample <- HeatmapAnnotation(
  Condition = meta$condition,
  col = list(Condition = c("control" = "gray", "treatment" = "red"))
)

# Create heatmap
Heatmap(MEs_scaled,
        name = "Eigengene",
        col = colorRamp2(c(-2, 0, 2), c("blue", "white", "red")),
        top_annotation = ha_sample,
        cluster_rows = TRUE,
        cluster_columns = TRUE,
        show_column_names = TRUE,
        show_row_names = TRUE,
        column_title = "Module Eigengene Expression",
        row_names_side = "left")
```

---

## Complete Workflow Example

```r
# Complete WGCNA workflow from start to finish

# 1. Setup
library(WGCNA)
allowWGCNAThreads()

# 2. Load data
expr_data <- read.csv("normalized_expression.csv", row.names = 1)
meta_data <- read.csv("sample_metadata.csv", row.names = 1)

# 3. Prepare data
datExpr0 <- as.data.frame(t(expr_data))
gsg <- goodSamplesGenes(datExpr0, verbose = 3)
datExpr0 <- datExpr0[gsg$goodSamples, gsg$goodGenes]

# Select top 5000 variable genes
gene_cv <- apply(datExpr0, 2, function(x) sd(x) / mean(x))
top_genes <- names(sort(gene_cv, decreasing = TRUE))[1:5000]
datExpr <- datExpr0[, top_genes]

# 4. Choose soft-thresholding power
powers <- c(1:20)
sft <- pickSoftThreshold(datExpr, powerVector = powers, verbose = 5)
softPower <- min(sft$fitIndices$Power[sft$fitIndices$SFT.R.sq > 0.85])

# 5. Build network
net <- blockwiseModules(datExpr, power = softPower,
                        TOMType = "signed", minModuleSize = 30,
                        reassignThreshold = 0, mergeCutHeight = 0.25,
                        numericLabels = FALSE, verbose = 3)

moduleColors <- net$colors

# 6. Calculate module eigengenes
MEs <- moduleEigengenes(datExpr, moduleColors)$eigengenes
MEs <- orderMEs(MEs)

# 7. Correlate with traits
traits <- meta_data[, c("weight", "glucose")]
moduleTraitCor <- cor(MEs, traits, use = "p")
moduleTraitPvalue <- corPvalueStudent(moduleTraitCor, nrow(datExpr))

# 8. Identify hub genes
Alldegrees <- intramodularConnectivity(adjacency(datExpr, power = softPower),
                                       moduleColors)

# 9. Export results
write.csv(data.frame(gene = colnames(datExpr), module = moduleColors, Alldegrees),
          "gene_modules.csv", row.names = FALSE)
write.csv(moduleTraitCor, "module_trait_correlations.csv")

cat("WGCNA analysis complete!\n")
```

---

## Additional Resources

- [WGCNA Best Practices](wgcna-best-practices.md) - Data preparation and QC guidelines
- [Parameter Tuning Guide](parameter-tuning-guide.md) - How to choose optimal parameters
- [Troubleshooting Guide](troubleshooting.md) - Common errors and solutions

**Official WGCNA Resources:**
- [WGCNA website](https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/)
- [WGCNA tutorials](https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/Tutorials/)
- [WGCNA FAQs](https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/faq.html)


---
