# DESeq2 Comprehensive Reference

Complete code patterns for DESeq2 differential expression analysis. Adapt these examples to your experimental design.

**Decision-making:** See [decision-guide.md](decision-guide.md) | **Errors:** See [troubleshooting.md](troubleshooting.md)

---

## Complete Standard Workflow

```r
library(DESeq2)
library(apeglm)

# 1. Create DESeqDataSet
dds <- DESeqDataSetFromMatrix(countData = counts, colData = coldata, design = ~ condition)

# 2. Pre-filter low counts
keep <- rowSums(counts(dds)) >= 10
dds <- dds[keep,]

# 3. Set reference level
dds$condition <- relevel(dds$condition, ref = 'control')

# 4. Run DESeq2 pipeline
dds <- DESeq(dds)

# 5. Extract results
res <- results(dds)

# 6. Apply LFC shrinkage
resLFC <- lfcShrink(dds, coef = 'condition_treated_vs_control', type = 'apeglm')

# 7. Get significant genes
sig <- subset(res, padj < 0.05 & abs(log2FoldChange) > 1)
```

---

## Design Formulas

### Simple Two-Group

```r
design = ~ condition
```
**Use:** Single factor, no batch effects, most common starting point

### Batch Correction

```r
design = ~ batch + condition
```
**Use:** Multiple sequencing runs, PCA shows batch clustering
**Requirement:** Each condition must have samples in each batch (not confounded)

### Paired Samples

```r
design = ~ individual + condition
```
**Use:** Before/after treatment, tumor vs normal from same patient
**Benefit:** Controls individual variation, increases power

### Interaction

```r
design = ~ genotype * treatment
# Expands to: ~ genotype + treatment + genotype:treatment
```
**Use:** Test if treatment effect differs by genotype/sex/age

**Extract results:**
```r
res_interaction <- results(dds, name = "genotypeMutant.treatmentdrug")
res_treatment_WT <- results(dds, name = "treatment_drug_vs_control")
```

### Multi-Factor

```r
design = ~ sex + age_group + treatment
```
**Use:** Multiple confounders to adjust for
**Requirement:** ≥3 samples per coefficient, variables not confounded

### No-Intercept

```r
design = ~ 0 + group
```
**Use:** Direct comparisons between any groups

### Changing Design

```r
design(dds) <- ~ batch + condition
dds <- DESeq(dds)
```

**Best practices:**
- Put condition of interest last
- Check confounding: `table(coldata$batch, coldata$condition)`
- Use PCA first to identify batch effects
- Keep simple - only include factors explaining substantial variation

---

## Extracting Results

### By Coefficient Name

```r
resultsNames(dds)  # See available coefficients
res <- results(dds, name = 'condition_treated_vs_control')
```
**Format:** `factor_level_vs_reference`

### By Contrast

```r
res <- results(dds, contrast = c('condition', 'treated', 'control'))
# Format: c(factor_name, numerator, denominator)
```
**Advantages:** Explicit comparison, any two levels, works for complex designs

### By Numeric Vector (Advanced)

```r
resultsNames(dds)
contrast_vector <- c(0, 0, 1, 0.5)
res <- results(dds, contrast = contrast_vector)
```

### Setting Reference Level

```r
dds$condition <- relevel(dds$condition, ref = "control")
dds <- DESeq(dds)
```
**Critical:** Always set explicitly before `DESeq()`

---

## Log Fold Change Shrinkage

**When to use:**

| Use Case | Shrunk | Unshrunk |
|----------|--------|----------|
| MA/volcano plots | ✅ | ❌ |
| Gene ranking | ✅ | ❌ |
| GSEA input | ✅ | ❌ |
| Hypothesis testing | ❌ | ✅ |

### apeglm (Recommended)

```r
library(apeglm)
coef_name <- resultsNames(dds)[2]
resLFC <- lfcShrink(dds, coef = coef_name, type = 'apeglm')
```
**Pros:** Best performance, preserves large LFC
**Cons:** Requires `coef` (not `contrast`), needs apeglm package

### ashr

```r
resLFC <- lfcShrink(dds, coef = 'condition_treated_vs_control', type = 'ashr')
```
**Use:** Large datasets, works with contrasts

### normal (Legacy)

```r
resLFC <- lfcShrink(dds, coef = 'condition_treated_vs_control', type = 'normal')
```
**Use:** Only if apeglm/ashr unavailable

### Ranking Genes

```r
# Top genes by shrunk LFC
ranked <- resLFC[order(abs(resLFC$log2FoldChange), decreasing = TRUE), ]
```

### GSEA Export

```r
gene_list <- resLFC$log2FoldChange
names(gene_list) <- rownames(resLFC)
gene_list <- gene_list[!is.na(gene_list)]
gene_list <- sort(gene_list, decreasing = TRUE)

write.table(
  data.frame(gene = names(gene_list), rank = gene_list),
  file = "gsea_ranked_list.rnk",
  quote = FALSE, sep = "\t", row.names = FALSE, col.names = FALSE
)
```

---

## Transformations

### Variance Stabilizing Transformation

```r
vsd <- vst(dds, blind = FALSE)  # Uses design
vsd_mat <- assay(vsd)
```
**Use:** Large datasets (>30 samples), fast

### Regularized Log

```r
rld <- rlog(dds, blind = FALSE)
```
**Use:** Small datasets (<30 samples), better stabilization but slower

### Normalized Counts

```r
normalized_counts <- counts(dds, normalized = TRUE)
sizeFactors(dds)  # View size factors
```

---

## Pre-Filtering

### Standard

```r
keep <- rowSums(counts(dds)) >= 10
dds <- dds[keep,]
```

### By Sample Count

```r
keep <- rowSums(counts(dds) >= 10) >= 3  # ≥3 samples with 10+ counts
dds <- dds[keep,]
```

### By Mean Expression

```r
keep <- rowMeans(counts(dds)) >= 10
dds <- dds[keep,]
```

**Why filter:** Reduces memory, speeds computation, increases power

---

## Significance Thresholds

```r
# Default
res <- results(dds)  # alpha = 0.1

# Custom
res <- results(dds, alpha = 0.05)

# LFC threshold
res <- results(dds, lfcThreshold = 1, altHypothesis = 'greaterAbs')

# Filter after
sig <- subset(res, padj < 0.05 & abs(log2FoldChange) > 1)
```

---

## Alternative Inputs

### SummarizedExperiment

```r
library(SummarizedExperiment)
dds <- DESeqDataSet(se, design = ~ condition)
```

### tximport (Salmon/Kallisto)

```r
library(tximport)
files <- file.path('salmon_output', samples$sample_id, 'quant.sf')
names(files) <- samples$sample_id
txi <- tximport(files, type = 'salmon', tx2gene = tx2gene)
dds <- DESeqDataSetFromTximport(txi, colData = samples, design = ~ condition)
```

### featureCounts

```r
library(Rsubread)
fc <- featureCounts(files = bam_files, annot.ext = gtf_file,
                    isGTFAnnotationFile = TRUE, GTF.featureType = 'exon')
dds <- DESeqDataSetFromMatrix(fc$counts, coldata, design = ~ condition)
```

---

## Likelihood Ratio Test

```r
# Test multiple conditions
dds_lrt <- DESeq(dds, test = 'LRT', reduced = ~ 1)
res_lrt <- results(dds_lrt)

# Test specific term
# Full: ~ batch + genotype + treatment
# Reduced: ~ batch + genotype
dds_lrt <- DESeq(dds, test = 'LRT', reduced = ~ batch + genotype)
```

---

## Working with Objects

### Update Design

```r
design(dds) <- ~ batch + condition
dds <- DESeq(dds)
```

### Subset Samples

```r
dds_subset <- dds[, dds$treatment == 'drug_A']
dds_subset <- DESeq(dds_subset)
```

### Subset Genes

```r
dds_genes <- dds[rownames(dds) %in% gene_list,]
```

---

## Accessing Results

```r
# Summary
summary(res)

# Order by significance
resOrdered <- res[order(res$padj),]

# Order by fold change
resOrdered <- res[order(abs(res$log2FoldChange), decreasing = TRUE),]

# Convert to data frame
res_df <- as.data.frame(res)
res_df$gene <- rownames(res_df)

# Count significant
sum(res$padj < 0.05, na.rm = TRUE)
sum(res$padj < 0.05 & res$log2FoldChange > 0, na.rm = TRUE)  # Up
sum(res$padj < 0.05 & res$log2FoldChange < 0, na.rm = TRUE)  # Down
```

---

## Exporting Results

```r
# Results tables
write.csv(as.data.frame(res), file = 'deseq2_results.csv')
sig <- subset(res, padj < 0.05)
write.csv(as.data.frame(sig), file = 'deseq2_significant.csv')

# Normalized counts
write.csv(counts(dds, normalized = TRUE), file = 'normalized_counts.csv')

# Transformed data
vsd <- vst(dds, blind = FALSE)
write.csv(assay(vsd), file = 'vst_transformed_counts.csv')

# Save object
saveRDS(dds, "dds_object.rds")
dds <- readRDS("dds_object.rds")
```

---

## Common Errors (Brief)

| Error | Cause | Solution |
|-------|-------|----------|
| "design matrix not full rank" | Confounded variables | Remove confounded variable or collapse |
| "counts matrix should be integers" | Non-integer counts | Use raw counts; for tximport use `DESeqDataSetFromTximport()` |
| "every gene contains at least one zero" | Wrong orientation | Transpose: `t(counts)` |
| "factor levels not in colData" | Typo in design | Check `colnames(colData(dds))` |
| "subscript out of bounds" | Sample name mismatch | Reorder: `coldata <- coldata[colnames(counts), ]` |

**Detailed solutions:** [troubleshooting.md](troubleshooting.md)

---

## Best Practices

1. Pre-filter low count genes before `DESeq()`
2. Set reference level explicitly with `relevel()`
3. Use shrinkage for visualization/ranking, not for testing
4. Use `padj` (adjusted p-value), never pvalue alone
5. Check QC plots before interpreting (PCA, dispersion)
6. Use `vst()` for large datasets, `rlog()` for small
7. Document design formula and contrasts
8. Report DESeq2 version: `packageVersion('DESeq2')`
9. Save session info: `sessionInfo()`

---

## Related Documentation

- [decision-guide.md](decision-guide.md) - Method selection decision trees
- [troubleshooting.md](troubleshooting.md) - Detailed error solutions
- [usage-guide.md](usage-guide.md) - Quick prompts and examples
