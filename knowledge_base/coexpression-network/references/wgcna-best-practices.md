# WGCNA Best Practices and Guidelines

This document provides detailed best practices for weighted gene co-expression network analysis (WGCNA), covering data preparation, parameter selection, analysis decisions, and result interpretation.

---

## Table of Contents

1. [Data Preparation](#data-preparation)
2. [Sample Size Requirements](#sample-size-requirements)
3. [Gene Filtering Strategies](#gene-filtering-strategies)
4. [Soft-Thresholding Power Selection](#soft-thresholding-power-selection)
5. [Module Detection Parameters](#module-detection-parameters)
6. [Module-Trait Correlation](#module-trait-correlation)
7. [Hub Gene Identification](#hub-gene-identification)
8. [Quality Control Checkpoints](#quality-control-checkpoints)
9. [Common Pitfalls](#common-pitfalls)
10. [Troubleshooting](#troubleshooting)

---

## Data Preparation

### Input Data Requirements

**✅ CORRECT Input:**
- Normalized expression data (VST, rlog, TPM, FPKM)
- Variance-stabilized counts from DESeq2
- Log2-transformed data with pseudocount

**❌ INCORRECT Input:**
- Raw counts (use DESeq2 VST or rlog transformation first)
- Data with batch effects (correct before analysis)
- Data with outlier samples (remove or investigate first)

### Normalization Methods

| Method | Source | Best For | Notes |
|--------|--------|----------|-------|
| **VST** | DESeq2 | RNA-seq, most datasets | Recommended for n ≥ 30 |
| **rlog** | DESeq2 | RNA-seq, small samples | Recommended for n < 30 |
| **TPM** | Kallisto/Salmon | Transcript quantification | Already normalized |
| **FPKM/RPKM** | Various | Legacy data | Less preferred than TPM |
| **log2(counts+1)** | Manual | Quick analysis | Not optimal, use VST/rlog |

### Data Matrix Format

WGCNA requires **samples as rows, genes as columns** (opposite of typical format):

```r
# Typical format: genes × samples
expr_matrix <- read.csv("expression.csv", row.names = 1)
#              Sample1  Sample2  Sample3
# Gene1          10.2     9.8     11.1
# Gene2           8.5     8.9      8.3

# WGCNA format: samples × genes (transpose)
datExpr <- t(expr_matrix)
#          Gene1  Gene2  Gene3
# Sample1   10.2    8.5    7.2
# Sample2    9.8    8.9    6.8
# Sample3   11.1    8.3    7.5
```

---

## Sample Size Requirements

### Minimum Sample Requirements

| Sample Size | WGCNA Suitability | Recommendations |
|-------------|------------------|-----------------|
| **< 15** | ❌ Not recommended | Results unreliable; consider alternative methods |
| **15-30** | ⚠️ Minimum | Use conservative parameters; results with caution |
| **30-50** | ✅ Good | Standard analysis appropriate |
| **50+** | ✅ Excellent | Robust module detection possible |

### Why Sample Size Matters

- **Correlation stability**: Small sample sizes lead to unstable correlations
- **Module detection**: Insufficient samples may miss true modules or create spurious ones
- **Statistical power**: Module-trait correlations require adequate power
- **Network topology**: Scale-free topology harder to achieve with few samples

**Rule of Thumb:** For every 1,000 genes, aim for at least 20 samples.

---

## Gene Filtering Strategies

### How Many Genes to Keep?

| Dataset Size | Recommended Gene Count | Rationale |
|--------------|----------------------|-----------|
| Small (n < 30) | 3,000-5,000 | Conservative to ensure stability |
| Medium (n = 30-50) | 5,000-10,000 | Standard analysis |
| Large (n > 50) | 10,000-15,000 | Can handle more genes |

### Filtering Methods

**1. Most Variable Genes (Recommended)**
```r
# Calculate variance for each gene
gene_vars <- apply(expr_matrix, 1, var)

# Select top N most variable genes
top_genes <- names(sort(gene_vars, decreasing = TRUE)[1:5000])
expr_filtered <- expr_matrix[top_genes, ]
```

**2. Expression Threshold + Variance**
```r
# Remove lowly expressed genes, then select by variance
mean_expr <- rowMeans(expr_matrix)
expr_matrix <- expr_matrix[mean_expr > 1, ]  # Adjust threshold

gene_vars <- apply(expr_matrix, 1, var)
top_genes <- names(sort(gene_vars, decreasing = TRUE)[1:5000])
```

**3. From DE Analysis (Optional)**
```r
# Use only genes passing DE pre-filtering
# This focuses network on biologically relevant genes
```

### Why Filter?

- **Computational efficiency**: Fewer genes = faster analysis
- **Noise reduction**: Low-variance genes add noise, not signal
- **Module quality**: High-variance genes form more meaningful modules
- **Multiple testing**: Fewer genes reduces multiple testing burden

---

## Soft-Thresholding Power Selection

### Understanding Soft Thresholding

WGCNA transforms correlations using a power function to achieve scale-free topology:
```
adjacency = |correlation|^power
```

**Scale-free topology**: Most genes have few connections, few genes are hubs (like biological networks).

### Selection Criteria

**Target:** R² ≥ 0.85 for scale-free topology fit

**Decision Guide:**
1. **If R² ≥ 0.85 is achieved**: Use the **lowest power** that reaches 0.85
2. **If R² never reaches 0.85**: Use the power with the **highest R²** (but results may be less reliable)
3. **If multiple powers reach 0.85**: Choose the lowest to preserve more connections

### Typical Power Values

| Data Type | Typical Range | Notes |
|-----------|--------------|-------|
| **RNA-seq** | 6-12 | Most common |
| **Microarray** | 4-10 | Often lower than RNA-seq |
| **Poor quality data** | > 15 | High power needed; consider data quality |

### Interpreting the Power Selection Plot

```r
# Output from pick_soft_power()
# Left plot: Scale-free topology fit vs. power
# Right plot: Mean connectivity vs. power
```

**What to look for:**
- **Left plot**: Find where curve plateaus above 0.85 (horizontal blue line)
- **Right plot**: Higher power = fewer connections (trade-off)
- **Sweet spot**: Adequate R² with reasonable connectivity

**Warning signs:**
- R² never exceeds 0.6: Data may not be suitable for WGCNA
- Need very high power (> 20): Check data quality and filtering

---

## Module Detection Parameters

### Key Parameters

#### 1. `minModuleSize`

**What it does:** Minimum number of genes per module

| Value | Use When | Result |
|-------|----------|--------|
| **20-30** | Few genes, exploratory | Many small modules |
| **30-50** (default) | Standard analysis | Balanced |
| **50-100** | Many genes, focused analysis | Fewer, larger modules |

**Recommendation:** Start with default (30), adjust based on results.

#### 2. `mergeCutHeight`

**What it does:** Threshold for merging similar modules (based on eigengene correlation)

| Value | Effect | Use When |
|-------|--------|----------|
| **0.15** | Aggressive merging | Want fewer, distinct modules |
| **0.25** (default) | Balanced | Standard analysis |
| **0.35** | Conservative | Want more, specific modules |

**Interpretation:** Modules with eigengene correlation > (1 - mergeCutHeight) are merged.
- 0.25 = merge modules with correlation > 0.75

### deepSplit Parameter

**What it does:** Controls sensitivity of module splitting (0-4 scale)

| Value | Effect | Use When |
|-------|--------|----------|
| **0-1** | Large modules | Broad biological processes |
| **2** (default) | Balanced | Standard analysis |
| **3-4** | Small modules | Fine-grained processes |

---

## Module-Trait Correlation

### Preparing Trait Data

**Numeric traits** (continuous):
```r
# Age, dose, time, expression levels - use as-is
traits <- data.frame(age = sample_metadata$age,
                     dose = sample_metadata$dose)
```

**Categorical traits** (binary/multi-level):
```r
# Convert to numeric (0/1 for binary)
traits <- data.frame(
  is_treated = as.numeric(sample_metadata$condition == "treated"),
  is_disease = as.numeric(sample_metadata$status == "disease")
)

# For multi-level factors, create dummy variables
traits <- model.matrix(~ condition - 1, data = sample_metadata)
```

### Interpreting Results

**Correlation values:**
- **|r| > 0.7**: Strong association
- **|r| > 0.5**: Moderate association (typically significant)
- **|r| < 0.3**: Weak association

**P-values:**
- Always use **adjusted p-values** if testing multiple modules
- **p < 0.05** after correction indicates significant association

**Positive vs. Negative correlation:**
- **Positive**: Module genes increase with trait
- **Negative**: Module genes decrease with trait

### Focus on Biologically Relevant Modules

Not all modules will associate with traits:
- **Grey module**: Unassigned genes (background) - usually ignore
- **Trait-associated modules**: Focus functional enrichment here
- **Non-associated modules**: May relate to unmeasured factors (batch, cell type composition)

---

## Hub Gene Identification

### Hub Gene Metrics

#### 1. **Intramodular Connectivity (kWithin)**

**What it measures:** How strongly connected a gene is to other genes in its module

**Interpretation:**
- High kWithin = central to module = likely important for module function
- Hub genes often have regulatory roles (transcription factors, signaling molecules)

#### 2. **Module Membership (MM)**

**What it measures:** Correlation between gene expression and module eigengene

**Interpretation:**
- MM close to 1: Gene expression highly representative of module
- MM close to 0: Gene expression weakly related to module

#### 3. **Gene Significance (GS)**

**What it measures:** Correlation between gene expression and trait

**Interpretation:**
- High GS: Gene strongly associated with trait
- Combine with high MM to find trait-associated hub genes

### Hub Gene Selection Strategy

**Priority 1: Trait-Associated Hubs**
```r
# High MM + High GS + High kWithin
hub_candidates <- gene_info %>%
  filter(module == "blue") %>%  # Trait-associated module
  filter(MM_blue > 0.8, GS_trait > 0.5, kWithin > quantile(kWithin, 0.9))
```

**Priority 2: Module Central Hubs**
```r
# Top by kWithin alone
top_hubs <- gene_info %>%
  group_by(module) %>%
  top_n(10, kWithin)
```

### Validating Hub Genes

**Biological validation:**
- Are hub genes known regulators (TFs, kinases)?
- Do they have relevant GO terms or pathways?
- Are they differentially expressed in your conditions?

**Network validation:**
- Do hub genes connect to many genes with related functions?
- Do hub gene knockdown/knockout experiments affect module genes?

---

## Quality Control Checkpoints

### 1. Sample Clustering (Before Analysis)

**Check for outliers:**
```r
# From prepare_wgcna_data.R
sampleTree <- hclust(dist(datExpr), method = "average")
plot(sampleTree)
```

**Action if outliers found:**
- Investigate technical issues (failed sequencing, contamination)
- Remove if justified (document reason)
- Keep if biological variation (disease samples)

### 2. Scale-Free Topology Fit

**✅ Good:** R² > 0.85
**⚠️ Acceptable:** R² = 0.70-0.85 (proceed with caution)
**❌ Poor:** R² < 0.70 (reconsider WGCNA suitability)

### 3. Module Sizes

**Check module distribution:**
```r
table(module_colors)
```

**Warning signs:**
- **Too many genes in grey**: Lower minModuleSize or increase top_n_genes
- **One giant module**: Increase mergeCutHeight or deepSplit
- **Many tiny modules**: Increase minModuleSize or decrease deepSplit

### 4. Module-Trait Correlation Patterns

**Expected patterns:**
- At least some modules correlate with traits
- Different modules associate with different traits
- Correlations make biological sense

**Warning signs:**
- No modules correlate with any trait (check trait preparation)
- All modules correlate similarly (possible confounding factor)

---

## Common Pitfalls

### 1. Using Raw Counts
**Problem:** Raw counts violate WGCNA assumptions (mean-variance relationship)
**Solution:** Use VST, rlog, TPM, or log-transformed data

### 2. Batch Effects
**Problem:** Batch effects create spurious co-expression modules
**Solution:** Remove batch effects with ComBat or limma::removeBatchEffect before WGCNA

### 3. Insufficient Sample Size
**Problem:** Unreliable correlations and unstable modules
**Solution:** Combine datasets, use more samples, or consider alternative methods

### 4. Too Many/Too Few Genes
**Problem:**
- Too many: Computational burden, noise
- Too few: Miss important modules
**Solution:** Follow filtering guidelines (3,000-15,000 genes depending on sample size)

### 5. Ignoring Network Topology
**Problem:** Forcing WGCNA when scale-free topology not achieved
**Solution:** If R² < 0.70, consider:
- Better gene filtering
- Checking data quality
- Alternative co-expression methods (e.g., direct correlation networks)

### 6. Over-Interpreting Small Modules
**Problem:** Modules with < 20 genes may be spurious
**Solution:** Increase minModuleSize or focus on larger modules

### 7. Treating Grey Module as Real Module
**Problem:** Grey = unassigned genes, not a biological module
**Solution:** Exclude grey module from downstream analysis

---

## Troubleshooting

### Problem: "Error in pickSoftThreshold: not enough samples"

**Cause:** Fewer than 15 samples
**Solution:** WGCNA not recommended; use alternative methods (e.g., differential co-expression)

### Problem: "No power reaches R² > 0.85"

**Possible causes:**
1. Poor data quality
2. Too many/too few genes
3. Batch effects
4. Heterogeneous sample population

**Solutions:**
1. Try stricter gene filtering (select more variable genes)
2. Check and correct batch effects
3. Use the highest R² power available (document limitation)
4. Consider signed network (`networkType = "signed"`)

### Problem: "Most genes assigned to grey module"

**Possible causes:**
1. `minModuleSize` too large
2. `mergeCutHeight` too low (over-merging)
3. Poor gene selection

**Solutions:**
1. Lower `minModuleSize` to 20-30
2. Increase `mergeCutHeight` to 0.30-0.35
3. Select more genes or use different filtering strategy

### Problem: "No modules correlate with traits"

**Possible causes:**
1. Trait encoding incorrect (e.g., character instead of numeric)
2. Missing values in traits
3. Traits not relevant to co-expression structure
4. Sample size too small

**Solutions:**
1. Verify trait data.frame is numeric
2. Remove or impute missing values
3. Try different traits or metadata variables
4. Check if trait is real biological signal

### Problem: "Module colors changed between runs"

**Explanation:** WGCNA assigns colors alphabetically by module size, which can vary slightly
**Solution:** This is expected; track modules by eigengene or gene membership, not color

### Problem: "Error: sample names don't match"

**Cause:** Sample order differs between datExpr and traits
**Solution:**
```r
# Ensure samples are in same order
traits <- traits[rownames(datExpr), ]
```

---

## Additional Resources

### Key Papers

1. **Langfelder & Horvath (2008)**. WGCNA: an R package for weighted correlation network analysis. *BMC Bioinformatics*. doi:10.1186/1471-2105-9-559
   - Original WGCNA paper - cite in all analyses

2. **Zhang & Horvath (2005)**. A general framework for weighted gene co-expression network analysis. *Statistical Applications in Genetics and Molecular Biology*. doi:10.2202/1544-6115.1128
   - Theoretical foundation

3. **Langfelder & Horvath (2012)**. Fast R Functions for Robust Correlations and Hierarchical Clustering. *Journal of Statistical Software*. doi:10.18637/jss.v046.i11
   - Performance improvements

### Online Resources

- **WGCNA Tutorials**: https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/Tutorials/
- **WGCNA FAQ**: https://horvath.genetics.ucla.edu/html/CoexpressionNetwork/Rpackages/WGCNA/faq.html
- **Bioconductor Package**: https://bioconductor.org/packages/release/bioc/html/WGCNA.html

---

**Last Updated:** January 27, 2026
