# DESeq2 Troubleshooting Guide

Solutions to common DESeq2 errors and issues.

---

## Error Messages

### "the model matrix is not full rank"

**Error:**
```
Error in checkFullRank(modelMatrix): the model matrix is not full rank
```

**Cause:** Confounded variables (one variable perfectly predicts another)

**Common example:**
```r
# ❌ All treated in batch B, all control in batch A
coldata <- data.frame(
  condition = c('control', 'control', 'treated', 'treated'),
  batch = c('A', 'A', 'B', 'B')
)
design = ~ batch + condition  # Confounded!
```

**Solutions:**

1. **Remove confounded variable:**
```r
design = ~ condition  # Remove batch
```

2. **Combine into single factor:**
```r
coldata$group <- factor(paste(coldata$batch, coldata$condition, sep = '_'))
design = ~ 0 + group
```

3. **Check design rank:**
```r
design_matrix <- model.matrix(~ batch + condition, coldata)
Matrix::rankMatrix(design_matrix) == ncol(design_matrix)  # Should be TRUE
```

---

### "counts matrix should contain integer values"

**Error:**
```
Error: some values in assay are not integers
```

**Cause:** Using normalized data (TPM/FPKM/RPKM) or tximport without proper function

**Solutions:**

1. **Use raw counts** - DESeq2 requires integers, not normalized data

2. **For tximport data:**
```r
library(tximport)
txi <- tximport(files, type = 'salmon', tx2gene = tx2gene)
dds <- DESeqDataSetFromTximport(txi, colData = coldata, design = ~ condition)
# NOT DESeqDataSetFromMatrix
```

3. **Round if needed** (only if counts have minor decimals from artifacts):
```r
counts <- round(counts)
dds <- DESeqDataSetFromMatrix(counts, coldata, design)
```

---

### "every gene contains at least one zero"

**Error:**
```
Error in estimateDispersionsGeneEst: every gene contains at least one zero
```

**Cause:** Usually transposed matrix (samples as rows instead of columns)

**Solutions:**

1. **Check orientation:**
```r
dim(counts)  # Should be genes × samples
head(counts)

# If samples are rows, transpose:
counts <- t(counts)
```

2. **Verify data loaded correctly:**
```r
sum(counts)  # Should be > 0
colSums(counts)  # Check sample totals
rowSums(counts)  # Check gene totals
```

---

### "factor levels not in colData" / "subscript out of bounds"

**Cause:** Sample name mismatch or typo in design formula

**Solutions:**

1. **Check names match:**
```r
colnames(counts)  # Column names in counts
rownames(coldata)  # Row names in colData
all(colnames(counts) == rownames(coldata))  # Should be TRUE
```

2. **Fix mismatch:**
```r
# Reorder coldata to match counts
coldata <- coldata[colnames(counts), ]
```

3. **Check design formula:**
```r
colnames(colData(dds))  # See available columns
design = ~ condition  # Check spelling matches
```

---

## Results Issues

### Too many NA values in padj

**Observation:** Many genes have padj = NA

**Cause:** Normal DESeq2 behavior - independent filtering and Cook's distance outlier detection

**Solutions:**

1. **This is expected** - DESeq2 sets NA for:
   - Low count genes (independent filtering)
   - Outlier samples (Cook's distance)
   - Genes with extreme outliers

2. **Adjust filtering:**
```r
res <- results(dds, alpha = 0.1)  # More lenient
# Or disable
res <- results(dds, independentFiltering = FALSE)
```

3. **Check specific genes:**
```r
mcols(res)$filterThreshold
which(is.na(res$padj))
```

---

### No significant genes found

**Observation:** `summary(res)` shows 0 genes with padj < 0.1

**Possible causes:** No real DE, high variability, small sample size, batch effects, wrong reference

**Solutions:**

1. **Check PCA:**
```r
vsd <- vst(dds, blind = FALSE)
plotPCA(vsd, intgroup = 'condition')
# Samples cluster by condition? If not, may not have DE
```

2. **Check batch effects:**
```r
plotPCA(vsd, intgroup = c('condition', 'batch'))
# If clustered by batch, add to design:
design = ~ batch + condition
```

3. **Verify reference level:**
```r
levels(dds$condition)  # First is reference
dds$condition <- relevel(dds$condition, ref = 'control')
```

4. **Check dispersion:**
```r
plotDispEsts(dds)
# High dispersion = high variability = low power
```

5. **Relax threshold:**
```r
sig <- subset(res, padj < 0.1 & abs(log2FoldChange) > 0.5)
```

6. **Increase sample size** - n ≥ 4 per group recommended

---

### Extremely large fold changes (log2FC > 10)

**Observation:** Some genes show >1000-fold change

**Cause:** Low count genes (dividing by near-zero creates large FC)

**Solutions:**

1. **Use LFC shrinkage:**
```r
resLFC <- lfcShrink(dds, coef = 'condition_treated_vs_control', type = 'apeglm')
```

2. **Filter low counts:**
```r
keep <- rowMeans(counts(dds)) >= 10
dds <- dds[keep,]
```

3. **Check specific genes:**
```r
plotCounts(dds, gene = 'gene_with_high_fc', intgroup = 'condition')
# If counts are 0 vs 1, not reliable
```

---

### Unexpected up/downregulation direction

**Observation:** Expected treated > control, but log2FC is negative

**Cause:** Wrong reference level or contrast direction reversed

**Solutions:**

1. **Check reference:**
```r
levels(dds$condition)  # First is reference (denominator)
dds$condition <- relevel(dds$condition, ref = 'control')
dds <- DESeq(dds)
```

2. **Understand direction:**
```r
# log2FC = log2(numerator / denominator)
# For condition_treated_vs_control:
# log2FC > 0: treated > control (upregulated in treated)
# log2FC < 0: treated < control (downregulated in treated)
```

3. **Flip contrast if needed:**
```r
res <- results(dds, contrast = c('condition', 'control', 'treated'))
```

---

## Performance Issues

### DESeq() is very slow

**Cause:** Large dataset (>50K genes, >100 samples)

**Solutions:**

1. **Pre-filter more aggressively:**
```r
keep <- rowSums(counts(dds) >= 10) >= 3
dds <- dds[keep,]
```

2. **Use parallel processing:**
```r
library(BiocParallel)
register(MulticoreParam(4))  # Use 4 cores
dds <- DESeq(dds, parallel = TRUE)
```

3. **Simplify design:**
```r
design = ~ condition  # Instead of complex interaction
```

---

### rlog() takes forever

**Cause:** rlog() is slow for large datasets

**Solution:** Use vst() instead
```r
vsd <- vst(dds, blind = FALSE)  # Much faster, similar results
```

---

## Interpretation Issues

### High dispersion estimates

**Observation:** plotDispEsts() shows points scattered far from fitted line

**Cause:** High biological variability, batch effects, or outlier samples

**Solutions:**

1. **Check for outliers:**
```r
vsd <- vst(dds, blind = TRUE)
plotPCA(vsd, intgroup = 'condition')
# Remove clear outliers if present
```

2. **Add batch to design:**
```r
design = ~ batch + condition
```

3. **Accept high variability** - Some systems naturally have high variance; results still valid, just lower power

---

### Cook's distance outliers

**Observation:** Many genes filtered due to Cook's distance

**Cause:** Outlier samples with extreme counts

**Solutions:**

1. **Inspect outliers:**
```r
W <- res$stat
outliers <- apply(W, 1, function(x) any(abs(x) > 3))
```

2. **Remove problem samples:**
```r
dds <- dds[, !colData(dds)$sample == 'outlier_sample']
dds <- DESeq(dds)
```

3. **Disable filtering** (use with caution):
```r
res <- results(dds, cooksCutoff = FALSE)
```

---

## Best Practices to Avoid Issues

1. **Check data structure:**
   - Verify counts are integers
   - Check sample/gene names match
   - Confirm orientation (genes × samples)

2. **Run QC first:**
   - PCA to check clustering
   - Identify batch effects
   - Find outlier samples

3. **Set reference explicitly:**
   - Use `relevel()` before DESeq()
   - Don't rely on alphabetical order

4. **Document design:**
   - Comment why you chose design formula
   - Record batch corrections

5. **Start simple:**
   - Begin with ~ condition
   - Add complexity only if needed

6. **Report versions:**
```r
packageVersion('DESeq2')
sessionInfo()
```

---

## Common Error Quick Reference

| Error | Likely Cause | Quick Fix |
|-------|--------------|-----------|
| "not full rank" | Confounded design | Remove confounded variable |
| "should be integers" | Normalized data | Use raw counts |
| "every gene zero" | Transposed matrix | `counts <- t(counts)` |
| "subscript out of bounds" | Name mismatch | `coldata <- coldata[colnames(counts), ]` |
| Many NA in padj | Normal filtering | Expected behavior |
| No significant genes | No DE / wrong ref | Check PCA, verify reference level |
| Huge fold changes | Low counts | Use LFC shrinkage |
| DESeq() slow | Large dataset | Pre-filter, use parallel |

---

## Getting Help

**Check first:**
1. DESeq2 vignette: `browseVignettes('DESeq2')`
2. Bioconductor support: https://support.bioconductor.org/

**When asking for help, provide:**
- Full error message
- `sessionInfo()` output
- Code that produces error
- Sample size and experimental design
