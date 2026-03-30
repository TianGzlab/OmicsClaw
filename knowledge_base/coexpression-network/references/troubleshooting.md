# WGCNA Troubleshooting Guide

Common errors, issues, and solutions for WGCNA analysis.

---

## Installation Issues

### Error: "package 'WGCNA' is not available"

**Cause:** WGCNA is a Bioconductor package, not on CRAN.

**Solution:**
```r
if (!requireNamespace("BiocManager", quietly = TRUE))
    install.packages("BiocManager")

BiocManager::install("WGCNA")
```

### Error: "CRAN mirror not set" / "@CRAN@"

**Cause:** CRAN repository not configured.

**Solution:**
```r
options(repos = c(CRAN = "https://cloud.r-project.org"))
```

---

## Data Preparation Issues

### Error: "Too few samples"

**Cause:** WGCNA requires ≥15 samples.

**Solution:**
- Combine biological replicates if appropriate
- Pool samples from similar conditions
- If <15 samples, consider alternative methods (correlation networks, pathway analysis)

### Warning: "Data has excessive missing values"

**Cause:** Too many NAs in expression matrix.

**Solution:**
```r
# Check missing value percentage
sum(is.na(datExpr)) / (nrow(datExpr) * ncol(datExpr)) * 100

# Remove genes with >10% missing values
missing_per_gene <- colSums(is.na(datExpr)) / nrow(datExpr)
datExpr <- datExpr[, missing_per_gene < 0.1]

# Or impute missing values
library(impute)
datExpr <- impute.knn(as.matrix(datExpr))$data
```

### Error: "Samples and metadata don't match"

**Cause:** Sample IDs mismatch between expression and metadata.

**Solution:**
```r
# Check sample names
cat("Expression samples:", head(rownames(datExpr)), "\n")
cat("Metadata samples:", head(rownames(meta)), "\n")

# Find common samples
common_samples <- intersect(rownames(datExpr), rownames(meta))
datExpr <- datExpr[common_samples, ]
meta <- meta[common_samples, ]
```

---

## Soft Power Selection Issues

### Issue: No power reaches R² > 0.85

**Cause:** Data doesn't fit scale-free topology well (batch effects, poor normalization, wrong network type).

**Diagnosis:**
```r
# Check soft threshold fit
sft <- pickSoftThreshold(datExpr, powerVector = 1:20, verbose = 5)
print(sft$fitIndices)

# Look at scale-free topology plot
plot(sft$fitIndices[, 1], sft$fitIndices[, 2],
     xlab = "Soft Threshold (power)",
     ylab = "Scale Free Topology Model Fit, R^2",
     main = "Scale independence")
```

**Solutions:**
1. **Check for batch effects:**
   ```r
   # PCA to visualize batch effects
   pca <- prcomp(datExpr, scale. = TRUE)
   plot(pca$x[, 1:2], col = as.factor(meta$batch))

   # Remove batch effects with ComBat or limma
   library(sva)
   datExpr_corrected <- ComBat(dat = t(datExpr), batch = meta$batch)
   datExpr <- t(datExpr_corrected)
   ```

2. **Try different network types:**
   ```r
   # Try unsigned network
   sft_unsigned <- pickSoftThreshold(datExpr, networkType = "unsigned")

   # Try signed hybrid
   sft_hybrid <- pickSoftThreshold(datExpr, networkType = "signed hybrid")
   ```

3. **Filter genes more stringently:**
   ```r
   # Use only top 3000-5000 most variable genes
   gene_var <- apply(datExpr, 2, var)
   top_genes <- names(sort(gene_var, decreasing = TRUE))[1:5000]
   datExpr <- datExpr[, top_genes]
   ```

4. **Accept lower R² threshold (0.75-0.80):**
   ```r
   # If biological signal is weak, R² = 0.75 may be acceptable
   power <- min(sft$fitIndices$Power[sft$fitIndices$SFT.R.sq > 0.75])
   ```

### Issue: Recommended power is very high (>20)

**Cause:** Data has very low correlations or high noise.

**Solutions:**
- Check data normalization
- Filter out low-expressed genes
- Try unsigned network type
- Consider if data is suitable for WGCNA

---

## Network Construction Issues

### Error: "System is computationally singular"

**Cause:** Genes have identical expression patterns (duplicates, isoforms).

**Solution:**
```r
# Remove duplicate genes
datExpr <- datExpr[, !duplicated(t(datExpr))]

# Or: Remove genes with zero variance
gene_var <- apply(datExpr, 2, var)
datExpr <- datExpr[, gene_var > 0]
```

### Issue: All genes assigned to grey module

**Cause:** `minModuleSize` too large or poor module detection.

**Solution:**
```r
# Lower minimum module size
net <- blockwiseModules(datExpr, power = power,
                        minModuleSize = 20,  # try 20-30
                        mergeCutHeight = 0.25,
                        verbose = 3)

# Or: Increase gene count
# Use 10,000-15,000 most variable genes instead of 5,000
```

### Issue: Too many small modules

**Cause:** `minModuleSize` too small or `mergeCutHeight` too high.

**Solution:**
```r
# Increase minimum module size
net <- blockwiseModules(datExpr, power = power,
                        minModuleSize = 50,  # increase from 30
                        mergeCutHeight = 0.15,  # lower to merge more
                        verbose = 3)
```

### Error: Memory allocation error / "Cannot allocate vector of size X GB"

**Cause:** Too many genes for available RAM.

**Solutions:**
```r
# 1. Reduce gene count
top_genes <- 5000  # instead of 10,000+
gene_var <- apply(datExpr, 2, var)
datExpr <- datExpr[, names(sort(gene_var, decreasing = TRUE))[1:top_genes]]

# 2. Use blockwise construction (automatically handles large datasets)
net <- blockwiseModules(datExpr, power = power,
                        maxBlockSize = 5000,  # process in blocks
                        verbose = 3)

# 3. Increase R memory limit (if possible)
memory.limit(size = 16000)  # Windows only
```

---

## Module-Trait Correlation Issues

### Issue: No significant module-trait correlations

**Cause:** Weak biological signal, incorrect trait coding, or insufficient samples.

**Diagnosis:**
```r
# Check trait variation
apply(traits, 2, function(x) c(min = min(x), max = max(x), var = var(x)))

# Check sample size per group
table(traits$condition)
```

**Solutions:**
1. **Check trait coding:**
   ```r
   # Binary traits should be 0/1
   traits$treatment <- as.numeric(traits$treatment == "treated")

   # Continuous traits should be numeric
   traits$age <- as.numeric(traits$age)
   ```

2. **Try different traits:**
   ```r
   # Test multiple traits
   moduleTraitCor <- cor(MEs, traits, use = "p")
   ```

3. **Increase sample size:** Need 20+ samples for robust results

4. **Check module eigengene variation:**
   ```r
   # Modules with low variation won't correlate well
   apply(MEs, 2, var)
   ```

### Error: "Incompatible dimensions"

**Cause:** Sample count mismatch between MEs and traits.

**Solution:**
```r
# Ensure same samples in same order
common_samples <- intersect(rownames(MEs), rownames(traits))
MEs <- MEs[common_samples, ]
traits <- traits[common_samples, ]
```

---

## Hub Gene Identification Issues

### Error: "subscript out of bounds" when calculating connectivity

**Cause:** Module colors don't match datExpr genes.

**Solution:**
```r
# Ensure module colors match gene order
length(moduleColors) == ncol(datExpr)
names(moduleColors) <- colnames(datExpr)

# Recalculate if needed
moduleColors <- net$colors
```

### Issue: Hub genes have low connectivity

**Cause:** Incorrect power or network type.

**Solution:**
- Check soft power selection
- Try signed vs unsigned network
- Verify adjacency matrix was calculated correctly

---

## Enrichment Analysis Issues

### Error: "No gene can be mapped"

**Cause:** Gene ID mismatch (e.g., ENSEMBL IDs vs gene symbols).

**Solutions:**
```r
# Check gene ID format
head(module_genes)

# Convert if needed
library(biomaRt)
mart <- useMart("ensembl", dataset = "hsapiens_gene_ensembl")
gene_map <- getBM(attributes = c("ensembl_gene_id", "hgnc_symbol"),
                  filters = "ensembl_gene_id",
                  values = module_genes,
                  mart = mart)
```

### Error: "OrgDb not found" or organism package missing

**Solution:**
```r
# Install organism annotation package
BiocManager::install("org.Hs.eg.db")  # Human
BiocManager::install("org.Mm.eg.db")  # Mouse
BiocManager::install("org.Rn.eg.db")  # Rat
```

### Issue: No enrichment results

**Causes:**
1. Wrong organism
2. Gene symbols don't match annotation
3. Module too small
4. Genes not functionally related

**Solutions:**
```r
# Verify organism matches your data
# Try different ontologies (BP, MF, CC)
# Use larger modules (>50 genes)
```

---

## Visualization Issues

### Error: "Cannot open graphics device"

**Cause:** Too many plot windows open or graphics device issue.

**Solution:**
```r
# Close all graphics devices
graphics.off()

# Or specify output device explicitly
png("plot.png", width = 800, height = 600)
# ... your plot code ...
dev.off()
```

### Issue: Heatmap labels overlapping

**Solution:**
```r
# For ComplexHeatmap
Heatmap(data,
        row_names_gp = gpar(fontsize = 8),  # smaller font
        column_names_gp = gpar(fontsize = 8),
        show_row_names = FALSE)  # hide if too many
```

### Issue: Plot is cut off or too small

**Solution:**
```r
# Increase plot size
png("plot.png", width = 1200, height = 800, res = 150)
# ... plot code ...
dev.off()

# Or adjust margins
par(mar = c(10, 10, 5, 5))  # bottom, left, top, right
```

---

## Performance Issues

### Issue: Analysis is very slow

**Solutions:**
1. **Reduce gene count:** Use 5,000-10,000 most variable genes
2. **Use multiple cores:**
   ```r
   library(WGCNA)
   enableWGCNAThreads(nThreads = 4)
   ```
3. **Use blockwise construction:**
   ```r
   net <- blockwiseModules(datExpr, maxBlockSize = 5000)
   ```

### Issue: R session crashes during network construction

**Causes:** Insufficient memory

**Solutions:**
- Reduce gene count
- Close other applications
- Use a machine with more RAM
- Process in blocks with `maxBlockSize`

---

## Interpretation Issues

### Question: What does grey module mean?

**Answer:** Grey module contains genes that don't fit well into any module. This is normal and expected. Typically 10-30% of genes are grey.

### Question: How many modules should I expect?

**Answer:** Typical range is 10-30 modules for 5,000-10,000 genes. Depends on:
- Biological heterogeneity
- Sample diversity
- Gene filtering strategy
- Module detection parameters

### Question: Which module is most important?

**Answer:** Focus on modules with:
- Strong correlation with traits of interest (|r| > 0.5, p < 0.05)
- Enrichment for known biological processes
- Hub genes that are known regulators
- Preservation across independent datasets

---

## Getting Additional Help

If you encounter issues not covered here:

1. **Check WGCNA FAQs:** https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/faq.html
2. **WGCNA tutorials:** https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/Tutorials/
3. **Bioconductor support:** https://support.bioconductor.org/t/wgcna/
4. **Review parameter tuning guide:** [parameter-tuning-guide.md](parameter-tuning-guide.md)
5. **Review best practices:** [wgcna-best-practices.md](wgcna-best-practices.md)
