# Pseudobulk Differential Expression Analysis Guide

## Overview

This guide covers best practices for performing differential expression (DE) analysis in single-cell RNA-seq experiments to compare conditions across biological replicates.

**Critical principle:** Cell-level DE tests (Wilcoxon, t-test) are **exploratory only** for identifying cluster markers. For comparing conditions across samples, **pseudobulk aggregation with DESeq2/edgeR is mandatory** to avoid pseudoreplication.

---

## Why Pseudobulk?

### The Pseudoreplication Problem

In multi-sample scRNA-seq experiments, cells from the same sample are not independent observations. Treating individual cells as replicates leads to:

- **Inflated Type I error rates**: False positive rates can exceed 50-90% instead of nominal 5%
- **Invalid p-values**: Statistical tests assume independence, which is violated
- **Non-reproducible results**: Findings don't replicate across studies

**Example:** If you have 3 treated vs 3 control samples with 10,000 cells each, you have **N=3** biological replicates, not N=60,000.

### Pseudobulk Solution

**Pseudobulk aggregation** sums counts within each sample × cell type combination, treating samples as replicates:

```
Individual cells (invalid):      Pseudobulk (valid):
Sample1_Cell1                   Sample1_CellTypeA (sum of all CellTypeA cells)
Sample1_Cell2         →         Sample2_CellTypeA
Sample1_Cell3                   Sample3_CellTypeA
...                             ...
```

This approach:
- ✅ Respects biological replicate structure
- ✅ Produces valid p-values and confidence intervals
- ✅ Accounts for sample-to-sample variability
- ✅ Compatible with standard bulk RNA-seq tools (DESeq2, edgeR)

---

## When to Use Pseudobulk

### Use Pseudobulk When:
- Comparing **conditions** across biological replicates (treated vs control, disease vs healthy, timepoint A vs B)
- Testing **hypotheses about biological effects**
- Reporting **inferential statistics** (p-values, confidence intervals)
- Preparing results for **publication**

### Use Cell-Level DE When:
- Finding **cluster markers** (exploratory, within-dataset characterization)
- Identifying genes that define cell types or states
- **Not making claims about condition effects**

---

## Pseudobulk Workflow

### Step 1: Aggregate Counts

**Sum raw counts** (not normalized) per sample × cell type:

```python
# Python (scanpy)
import pandas as pd

def aggregate_to_pseudobulk(adata, sample_key, celltype_key, min_cells=10):
    """Aggregate counts to pseudobulk"""
    pseudobulk = []

    for sample in adata.obs[sample_key].unique():
        for celltype in adata.obs[celltype_key].unique():
            # Select cells
            mask = (adata.obs[sample_key] == sample) & (adata.obs[celltype_key] == celltype)
            n_cells = mask.sum()

            if n_cells >= min_cells:
                # Sum raw counts
                summed_counts = adata[mask, :].X.sum(axis=0).A1

                pseudobulk.append({
                    'sample': sample,
                    'celltype': celltype,
                    'n_cells': n_cells,
                    'counts': summed_counts
                })

    return pseudobulk
```

```r
# R (Seurat)
library(muscat)

# Aggregate using muscat
pb_data <- aggregateData(
  seurat_obj,
  assay = "counts",
  fun = "sum",  # CRITICAL: use sum, not mean
  by = c("sample_id", "cluster_id")
)
```

**Key points:**
- Use **raw counts**, not normalized data
- Use **sum**, not mean or median
- Filter: Minimum 10 cells per sample × cell type
- Filter: Minimum 3 samples per condition

### Step 2: Create Sample Metadata

```python
# Python
sample_metadata = pd.DataFrame({
    'sample_id': ['S1', 'S2', 'S3', 'S4', 'S5', 'S6'],
    'condition': ['control', 'control', 'control', 'treated', 'treated', 'treated'],
    'batch': ['batch1', 'batch1', 'batch2', 'batch1', 'batch2', 'batch2'],
    'donor': ['D1', 'D2', 'D3', 'D4', 'D5', 'D6']
})
```

### Step 3: Run DESeq2

```python
# Python (via rpy2)
from rpy2.robjects import r, pandas2ri
import rpy2.robjects as ro

# Convert to R objects
pandas2ri.activate()
r_counts = pandas2ri.py2rpy(counts_df)
r_metadata = pandas2ri.py2rpy(sample_metadata)

# Run DESeq2 in R
r('''
library(DESeq2)

# Create DESeqDataSet
dds <- DESeqDataSetFromMatrix(
  countData = counts_matrix,
  colData = metadata,
  design = ~ batch + condition
)

# Run DE analysis
dds <- DESeq(dds)
results <- results(dds, contrast = c("condition", "treated", "control"))

# Shrink log2 fold changes
results_shrunk <- lfcShrink(dds, coef = "condition_treated_vs_control", type = "ashr")
''')
```

```r
# R (native)
library(DESeq2)

# Create DESeqDataSet
dds <- DESeqDataSetFromMatrix(
  countData = assay(pb_data),
  colData = colData(pb_data),
  design = ~ batch + condition
)

# Filter low count genes
keep <- rowSums(counts(dds) >= 10) >= 3
dds <- dds[keep, ]

# Run DESeq2
dds <- DESeq(dds)

# Extract results
res <- results(dds, contrast = c("condition", "treated", "control"))

# Shrink log2FC for better effect size estimates
res_shrunk <- lfcShrink(dds, coef = "condition_treated_vs_control", type = "ashr")
```

### Step 4: Filter and Interpret Results

```r
# Filter significant genes
sig_genes <- subset(res_shrunk, padj < 0.05 & abs(log2FoldChange) > 0.5 & baseMean > 10)

# Sort by adjusted p-value
sig_genes <- sig_genes[order(sig_genes$padj), ]
```

**Filtering criteria:**
- `padj < 0.05`: Adjusted p-value (controls FDR)
- `abs(log2FoldChange) > 0.5`: Minimum 1.4x fold change (biological relevance)
- `baseMean > 10`: Exclude lowly expressed genes (reduces noise)

---

## Design Formula Guidelines

### Basic Comparison
```r
design = ~ condition
```
Use when: Single variable, no confounders

### Accounting for Batch Effects
```r
design = ~ batch + condition
```
Use when: Known batch effects (sequencing run, library prep date)

### Paired/Matched Design
```r
design = ~ donor + condition
```
Use when: Samples paired by donor (e.g., before/after treatment in same individual)

### Complex Designs
```r
design = ~ batch + sex + condition
```
Use when: Multiple covariates to control

---

## muscat Framework (Recommended for R)

The `muscat` package provides a streamlined workflow for pseudobulk DE in scRNA-seq:

```r
library(muscat)
library(SingleCellExperiment)

# Convert Seurat to SCE
sce <- as.SingleCellExperiment(seurat_obj)

# Aggregate to pseudobulk
pb <- aggregateData(sce,
                    assay = "counts",
                    fun = "sum",
                    by = c("sample_id", "cluster_id"))

# Run DE with DESeq2
res_DS <- pbDS(pb,
               design = ~ condition,
               contrast = c("condition", "treated", "control"),
               method = "DESeq2")

# Extract results per cell type
res_table <- resDS(sce, res_DS)
```

---

## Common Pitfalls

### ❌ DON'T: Use Cell-Level Tests for Condition Comparisons

```r
# WRONG: Wilcoxon on individual cells
Idents(seurat) <- "condition"
markers <- FindMarkers(seurat, ident.1 = "treated", ident.2 = "control")
# This ignores sample structure and inflates Type I error!
```

### ✅ DO: Use Pseudobulk

```r
# CORRECT: Pseudobulk aggregation
pb <- aggregateData(..., by = c("sample_id", "cluster_id"))
dds <- DESeqDataSetFromMatrix(assay(pb), colData(pb), ~ condition)
```

### ❌ DON'T: Use Mean/Median Aggregation

```r
# WRONG
pb <- aggregateData(..., fun = "mean")
```

### ✅ DO: Use Sum Aggregation

```r
# CORRECT
pb <- aggregateData(..., fun = "sum")
```

### ❌ DON'T: Use Normalized Counts

```r
# WRONG: DESeq2 on log-normalized data
dds <- DESeqDataSetFromMatrix(log_normalized_counts, ...)
```

### ✅ DO: Use Raw Counts

```r
# CORRECT: DESeq2 on raw counts
dds <- DESeqDataSetFromMatrix(raw_counts, ...)
```

---

## Minimum Sample Size Requirements

| Comparison | Absolute Minimum | Recommended | Notes |
|------------|-----------------|-------------|-------|
| Two conditions | **2 per condition** | 5-6 per condition | N=1 in any group is **invalid** — DESeq2 cannot estimate dispersion |
| Paired design | 3 pairs | 5-6 pairs | |
| Multi-group | 3 per group | 4-5 per group | |

⚠️ **CRITICAL: N=1 makes pseudobulk DE invalid.** DESeq2 requires biological replicates to estimate gene-wise dispersion. With N=1 in any group:
- Dispersion cannot be estimated → p-values are meaningless
- The `run_deseq2_analysis()` script will **refuse to run** and print an error
- Use cell-level Wilcoxon for exploratory analysis only, with explicit pseudoreplication caveats

**When N=1 is unavoidable (e.g., rare condition, pilot study):**
1. **Do NOT run pseudobulk DE** — report this as a study design limitation
2. **Exploratory cell-level DE** (Wilcoxon) can identify candidate genes, but results are exploratory, not inferential — state this clearly
3. **Descriptive statistics** — report cell composition differences, but note N=1 prevents significance testing
4. **Recommend follow-up** — additional samples needed for valid statistical inference

**Power considerations:**
- **N=2**: Can technically run DESeq2 but very low power; only detects massive effects
- **N=3**: Can detect very large effects (>2-fold) with moderate power
- **N=5-6**: Good power for 1.5-2-fold changes
- **N≥8**: Robust power for smaller effect sizes

---

## Output and Reporting

### Required Information

For each cell type, report:
1. **Number of samples** per condition
2. **Number of cells** aggregated per sample
3. **Design formula** used
4. **Filtering criteria** applied
5. **Multiple testing correction** method (usually Benjamini-Hochberg)

### Example Results Table

| Gene | baseMean | log2FC | lfcSE | stat | pvalue | padj | n_samples | n_cells_mean |
|------|----------|--------|-------|------|--------|------|-----------|--------------|
| GENE1 | 245.3 | 2.14 | 0.31 | 6.9 | 1.2e-11 | 3.4e-08 | 6 | 421 |
| GENE2 | 189.7 | -1.87 | 0.28 | -6.7 | 2.1e-11 | 3.4e-08 | 6 | 421 |

---

## Cell-Level vs Pseudobulk: Quick Reference

| Analysis Goal | Method | Valid for Inference? |
|---------------|--------|---------------------|
| Find cluster markers | Wilcoxon (cell-level) | ❌ No (exploratory only) |
| Compare conditions | Pseudobulk + DESeq2 | ✅ Yes (inferential) |
| Identify cell types | Wilcoxon (cell-level) | ✅ Yes (within-dataset) |
| Test treatment effect | Pseudobulk + DESeq2 | ✅ Yes (inferential) |

---

## Key References

1. **Squair JW et al. (2021)** Confronting false discoveries in single-cell differential expression. *Nature Communications* 12:5692.
   - Demonstrates pseudoreplication problem and pseudobulk solution

2. **Crowell HL et al. (2020)** muscat detects subpopulation-specific state transitions from multi-sample multi-condition single-cell transcriptomics data. *Nature Communications* 11:6077.
   - Introduces muscat framework

3. **Zimmerman KD et al. (2021)** A practical solution to pseudoreplication bias in single-cell studies. *Nature Communications* 12:738.
   - Guidelines for aggregation-based methods

4. **Love MI et al. (2014)** Moderated estimation of fold change and dispersion for RNA-seq data with DESeq2. *Genome Biology* 15:550.
   - DESeq2 methodology

---

## Summary

- ✅ **Always use pseudobulk** for condition comparisons across samples
- ✅ **Aggregate by sum**, not mean or median
- ✅ **Use raw counts**, not normalized data
- ✅ **Include batch effects** in design formula when present
- ✅ **Report sample sizes and cell numbers** clearly
- ❌ **Never use cell-level tests** (Wilcoxon, t-test) for condition inference
- ❌ **Never report cell-level p-values** for biological hypotheses

Following these guidelines ensures valid, reproducible differential expression analysis in single-cell RNA-seq experiments.
