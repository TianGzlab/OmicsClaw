# WGCNA Parameter Tuning Guide

This guide provides detailed recommendations for tuning WGCNA parameters based on your specific dataset characteristics and analysis goals.

---

## Table of Contents

1. [Parameter Overview](#parameter-overview)
2. [Gene Filtering Parameters](#gene-filtering-parameters)
3. [Network Construction Parameters](#network-construction-parameters)
4. [Module Detection Parameters](#module-detection-parameters)
5. [Parameter Tuning Strategies](#parameter-tuning-strategies)
6. [Example Scenarios](#example-scenarios)

---

## Parameter Overview

### Critical Parameters by Analysis Stage

| Stage | Parameter | Default | Impact | Tuning Priority |
|-------|-----------|---------|--------|-----------------|
| **Filtering** | `top_n_genes` | 5000 | Genes analyzed | High |
| **Network** | `power` | Auto | Connection strength | Critical |
| **Network** | `networkType` | "signed" | Correlation interpretation | Medium |
| **Modules** | `minModuleSize` | 30 | Minimum genes per module | High |
| **Modules** | `deepSplit` | 2 | Module granularity | Medium |
| **Modules** | `mergeCutHeight` | 0.25 | Module merging threshold | High |

---

## Gene Filtering Parameters

### `top_n_genes`: Number of Genes to Analyze

**Purpose:** Select most variable genes for network construction

**Default:** 5000

**Decision Matrix:**

| Sample Size | Conservative | Balanced | Aggressive |
|-------------|-------------|----------|------------|
| **< 30** | 3000 | 5000 | 7000 |
| **30-50** | 5000 | 8000 | 10000 |
| **50+** | 8000 | 10000 | 15000 |

**When to use fewer genes (3000-5000):**
- ✅ Small sample size (< 30)
- ✅ Preliminary exploratory analysis
- ✅ Computational constraints
- ✅ Poor data quality

**When to use more genes (10000-15000):**
- ✅ Large sample size (50+)
- ✅ Comprehensive analysis
- ✅ Heterogeneous samples
- ✅ High-quality data

**Warning signs:**
- **Too many genes:** Scale-free topology not achieved (R² < 0.70)
- **Too few genes:** Missing important biological modules

**Tuning approach:**
```r
# Test multiple values
for (n_genes in c(3000, 5000, 8000, 10000)) {
  data <- prepare_wgcna_data(expr_file, meta_file, top_n_genes = n_genes)
  power <- pick_soft_power(data$datExpr)
  cat("Genes:", n_genes, "| Power R²:", max(power$sft$fitIndices[,2]), "\n")
}
# Choose configuration with best R² balance
```

---

## Network Construction Parameters

### `power`: Soft-Thresholding Power

**Purpose:** Transform correlations to achieve scale-free topology

**Default:** Auto-selected by `pickSoftThreshold()`

**Selection criteria:**
1. **Primary**: First power where R² ≥ 0.85
2. **Fallback**: Highest R² if none reach 0.85

**Typical ranges:**
- **RNA-seq**: 6-12
- **Microarray**: 4-10
- **High noise data**: 12-20

**Manual override scenarios:**

**Scenario 1: Power too low (< 4)**
```r
# Problem: Too many connections, not scale-free
# Solution: Increase power manually
network <- build_network(datExpr, power = 6, ...)
```

**Scenario 2: Power too high (> 15)**
```r
# Problem: May indicate poor data quality
# Solution: Improve filtering or check data quality before increasing
```

**Trade-offs:**
- **Low power**: More connections, less selective
- **High power**: Fewer connections, more selective
- **Sweet spot**: Scale-free (R² > 0.85) with reasonable connectivity

---

### `networkType`: Signed vs Unsigned Networks

**Purpose:** How to interpret positive vs negative correlations

**Options:**

| Type | Correlation Treatment | Use When |
|------|----------------------|----------|
| **"signed"** (default) | Positive only | Default; biological networks are typically signed |
| **"unsigned"** | Both positive and negative | Exploratory; some microarray analyses |
| **"signed hybrid"** | Intermediate | Rare; specific use cases |

**Recommendation:** Use `"signed"` unless you have specific reason not to.

**Why signed is preferred:**
- Biological networks are directed (activation/repression)
- Negative correlations often non-specific (e.g., housekeeping vs specialized genes)
- Easier interpretation of module eigengenes

---

### `corType`: Correlation Method

**Purpose:** Method for calculating gene-gene correlations

**Options:**

| Method | Use When | Pros | Cons |
|--------|----------|------|------|
| **"pearson"** (default) | Standard analysis | Fast, standard | Sensitive to outliers |
| **"bicor"** | Outlier genes | Robust to outliers | Slower |

**When to use bicor:**
- Data with outlier samples or genes
- Heterogeneous sample populations
- Want robust results

```r
# Use biweight midcorrelation for robustness
network <- build_network(datExpr, power = 12, corType = "bicor")
```

---

## Module Detection Parameters

### `minModuleSize`: Minimum Genes Per Module

**Purpose:** Smallest allowed module size

**Default:** 30

**Decision guide:**

| Goal | minModuleSize | Expected Result |
|------|---------------|-----------------|
| **Broad processes** | 50-100 | Fewer, larger modules |
| **Balanced** | 30-50 | Standard modules |
| **Fine-grained** | 20-30 | More, smaller modules |

**When to DECREASE (20-25):**
- ✅ Focused gene set (< 5000 genes)
- ✅ Want to capture specific small pathways
- ✅ Many genes in grey module

**When to INCREASE (50-100):**
- ✅ Large gene set (> 10000 genes)
- ✅ Want broad biological themes
- ✅ Too many small modules

**Example tuning:**
```r
# Compare module sizes
for (min_size in c(20, 30, 50)) {
  network <- build_network(datExpr, power = soft_power, min_module_size = min_size)
  cat("minModuleSize:", min_size, "| Modules:", length(unique(network$module_colors)), "\n")
  print(table(network$module_colors))
}
```

---

### `deepSplit`: Module Splitting Sensitivity

**Purpose:** Controls how aggressively to split modules during hierarchical clustering

**Range:** 0-4 (integer)

**Default:** 2

| Value | Effect | Module Sizes | Use When |
|-------|--------|-------------|----------|
| **0** | Minimal splitting | Large modules | Broad biological processes |
| **1** | Conservative | Large-medium | General analysis |
| **2** (default) | Balanced | Medium | Standard use |
| **3** | Aggressive | Small-medium | Specific pathways |
| **4** | Maximum splitting | Small modules | Fine-grained analysis |

**Interaction with minModuleSize:**
- Higher `deepSplit` + lower `minModuleSize` = Many small modules
- Lower `deepSplit` + higher `minModuleSize` = Fewer large modules

**Tuning strategy:**
```r
# Test different deepSplit values
for (ds in 0:4) {
  network <- build_network(datExpr, power = 12,
                          deepSplit = ds,
                          min_module_size = 30)
  cat("deepSplit:", ds, "| Modules:", length(unique(network$module_colors)), "\n")
}
```

---

### `mergeCutHeight`: Module Merging Threshold

**Purpose:** Merge modules with similar eigengenes (based on correlation)

**Default:** 0.25

**Interpretation:** Modules with eigengene correlation > (1 - mergeCutHeight) are merged

| Value | Correlation Threshold | Effect | Use When |
|-------|----------------------|--------|----------|
| **0.10** | > 0.90 | Very aggressive merging | Want distinct modules only |
| **0.15** | > 0.85 | Aggressive merging | Fewer, clear modules |
| **0.25** (default) | > 0.75 | Balanced | Standard analysis |
| **0.35** | > 0.65 | Conservative | Keep similar modules separate |
| **0.50** | > 0.50 | Minimal merging | Maximum module diversity |

**When to DECREASE (more merging):**
- ✅ Too many similar modules
- ✅ Want fewer, distinct modules
- ✅ Eigengene heatmap shows highly correlated modules

**When to INCREASE (less merging):**
- ✅ Modules merging into one giant module
- ✅ Want to preserve subtle differences
- ✅ Eigengenes are distinct

**Example:**
```r
# Compare merging thresholds
for (cut_height in c(0.15, 0.25, 0.35)) {
  network <- build_network(datExpr, power = 12, merge_cut_height = cut_height)
  cat("mergeCutHeight:", cut_height, "| Modules:", length(unique(network$module_colors)), "\n")
}
```

---

## Parameter Tuning Strategies

### Strategy 1: Start with Defaults, Iterate

**Step 1:** Run with default parameters
```r
data <- prepare_wgcna_data(expr_file, meta_file, top_n_genes = 5000)
power <- pick_soft_power(data$datExpr)
network <- build_network(data$datExpr, power = power$power)
```

**Step 2:** Evaluate results
- Check scale-free topology R²
- Count modules and sizes
- Assess grey module proportion

**Step 3:** Adjust based on issues (see Troubleshooting below)

---

### Strategy 2: Parameter Sweep (Exploratory)

**When to use:** Uncertain about optimal parameters, want to compare options

**Example workflow:**
```r
# Define parameter grid
params <- expand.grid(
  top_n_genes = c(3000, 5000, 8000),
  minModuleSize = c(20, 30, 50),
  mergeCutHeight = c(0.15, 0.25, 0.35)
)

# Test each combination (pseudo-code)
results <- list()
for (i in 1:nrow(params)) {
  # Run WGCNA with params[i,]
  # Store module count, R², grey proportion
  results[[i]] <- evaluate_wgcna(params[i,])
}

# Compare and select best
```

**Evaluation metrics:**
- Scale-free topology R²
- Number of modules (aim for 5-20)
- Grey module proportion (< 30%)
- Module-trait correlation strength

---

### Strategy 3: Biological Validation-Driven

**Step 1:** Run with multiple parameter sets
**Step 2:** Perform functional enrichment on modules
**Step 3:** Select parameter set yielding most biologically meaningful modules

**Example:**
```r
# Configuration A: Conservative (few large modules)
network_A <- build_network(datExpr, power = 12, min_module_size = 50, merge_cut_height = 0.15)

# Configuration B: Balanced
network_B <- build_network(datExpr, power = 12, min_module_size = 30, merge_cut_height = 0.25)

# Configuration C: Granular (many small modules)
network_C <- build_network(datExpr, power = 12, min_module_size = 20, merge_cut_height = 0.35)

# Compare enrichment results
# Select configuration with strongest, most specific enrichments
```

---

## Example Scenarios

### Scenario 1: Standard RNA-seq (n = 40 samples)

**Goal:** Identify co-expression modules associated with treatment

**Recommended parameters:**
```r
top_n_genes <- 5000           # Balanced
power <- auto_selected         # Typically 8-12
networkType <- "signed"
minModuleSize <- 30
deepSplit <- 2
mergeCutHeight <- 0.25
```

**Rationale:** Defaults work well for standard-sized, good-quality datasets

---

### Scenario 2: Small Sample Size (n = 20)

**Goal:** Exploratory network analysis with limited samples

**Recommended parameters:**
```r
top_n_genes <- 3000           # Conservative
power <- auto_selected         # May need lower power
networkType <- "signed"
minModuleSize <- 25            # Lower to capture more modules
deepSplit <- 2
mergeCutHeight <- 0.30         # Less aggressive merging
```

**Rationale:** Conservative approach given limited statistical power

**Caveats:**
- Results may be less stable
- Validate findings with independent data if possible
- Focus on strongest modules only

---

### Scenario 3: Large Dataset (n = 100+ samples)

**Goal:** Comprehensive co-expression network with high resolution

**Recommended parameters:**
```r
top_n_genes <- 10000          # More genes supported
power <- auto_selected         # Typically 10-14
networkType <- "signed"
minModuleSize <- 50            # Larger modules for robustness
deepSplit <- 2
mergeCutHeight <- 0.20         # More aggressive merging
```

**Rationale:** Large sample size allows more genes and robust module detection

**Opportunities:**
- Can detect smaller, more specific modules
- Higher statistical power for module-trait correlations
- More reliable hub gene identification

---

### Scenario 4: Heterogeneous Samples (e.g., multiple tissues)

**Goal:** Find co-expression modules across diverse sample types

**Recommended parameters:**
```r
top_n_genes <- 8000           # More genes to capture diversity
power <- auto_selected
networkType <- "signed"
corType <- "bicor"             # Robust to heterogeneity
minModuleSize <- 40
deepSplit <- 1                 # Less splitting (broader modules)
mergeCutHeight <- 0.20         # Merge similar modules
```

**Rationale:** Focus on conserved co-expression across sample types

**Alternative approach:**
- Perform separate WGCNA per tissue
- Compare module preservation across tissues

---

### Scenario 5: Focused Gene Set (e.g., 1000 DEGs)

**Goal:** Network analysis of differentially expressed genes only

**Recommended parameters:**
```r
top_n_genes <- all_genes       # Use all DEGs
power <- auto_selected         # May need higher power
networkType <- "signed"
minModuleSize <- 15            # Lower for small gene set
deepSplit <- 3                 # More splitting
mergeCutHeight <- 0.30         # Less merging
```

**Rationale:** Small gene set requires adjusted parameters to form meaningful modules

**Note:** With < 1000 genes, consider alternative co-expression methods

---

### Scenario 6: Poor Scale-Free Topology (R² < 0.70)

**Goal:** Improve network topology fit

**Troubleshooting steps:**

**Step 1: Filter genes more stringently**
```r
top_n_genes <- 3000  # Reduce to most variable
```

**Step 2: Try different correlation methods**
```r
corType <- "bicor"  # More robust
```

**Step 3: Check batch effects**
```r
# Remove batch effects before WGCNA
library(sva)
expr_corrected <- ComBat(expr_matrix, batch = metadata$batch)
```

**Step 4: Accept lower R² if necessary**
```r
# Use highest R² power, document limitation
power <- 14  # Or highest tested
```

---

## Practical Tips

### 1. Document Your Parameters

Always document the parameters used in your analysis:

```r
# Save parameter configuration
params <- list(
  top_n_genes = 5000,
  power = 12,
  networkType = "signed",
  minModuleSize = 30,
  deepSplit = 2,
  mergeCutHeight = 0.25
)
saveRDS(params, "wgcna_parameters.rds")
```

### 2. Compare Before/After Parameter Changes

When tuning, compare key metrics:

```r
compare_params <- function(network1, network2, name1, name2) {
  cat("\n", name1, ":\n")
  cat("  Modules:", length(unique(network1$module_colors)), "\n")
  cat("  Grey genes:", sum(network1$module_colors == "grey"), "\n")

  cat("\n", name2, ":\n")
  cat("  Modules:", length(unique(network2$module_colors)), "\n")
  cat("  Grey genes:", sum(network2$module_colors == "grey"), "\n")
}
```

### 3. Parameter Sensitivity Analysis

Test robustness of results to parameter changes:
- If results change dramatically with small parameter tweaks → less reliable
- If modules remain similar across parameter ranges → robust findings

### 4. Prioritize Scale-Free Topology

**Most important:** Achieving scale-free topology (R² > 0.85)
- This is why WGCNA works - mimics biological networks
- If not achieved, results may be less biologically meaningful

---

## Summary: Quick Reference

| To achieve... | Adjust parameter... | Direction... |
|---------------|-------------------|--------------|
| **Better scale-free fit** | `top_n_genes` | Decrease |
| **Fewer modules** | `minModuleSize` | Increase |
| **Fewer modules** | `mergeCutHeight` | Decrease |
| **More modules** | `deepSplit` | Increase |
| **Larger modules** | `minModuleSize` | Increase |
| **Larger modules** | `deepSplit` | Decrease |
| **Less grey genes** | `minModuleSize` | Decrease |
| **Robust to outliers** | `corType` | Set to "bicor" |

---

**Last Updated:** January 27, 2026
