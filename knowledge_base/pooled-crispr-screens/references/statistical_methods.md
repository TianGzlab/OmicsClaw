# Statistical Methods for CRISPR Screen Analysis

Detailed description of statistical methods used for outlier detection and differential expression in pooled CRISPR screens.

---

## Outlier Detection Methods

### Overview

Outlier detection identifies cells with perturbation-induced phenotypes by comparing their transcriptional profiles to non-targeting controls. Unlike clustering-based approaches, outlier methods are more sensitive to subtle phenotypes and don't require predefined clusters.

**General workflow:**
1. For each perturbation, compute PCA on differentially expressed genes
2. Train outlier detector on control cells in PCA space
3. Predict outliers among perturbed cells
4. Flag perturbations with significant outlier counts as "hits"

---

### LocalOutlierFactor (LOF)

**Algorithm:** Density-based outlier detection that compares local density of a point to its neighbors.

**How it works:**
1. For each control cell, compute k-nearest neighbors (default k=20)
2. Calculate local reachability density (LRD): inverse of mean distance to neighbors
3. For each perturbed cell, compute LOF score = ratio of cell's LRD to neighbors' LRD
4. Cells with LOF > threshold are outliers (lower density than neighbors)

**Parameters:**
```python
from sklearn.neighbors import LocalOutlierFactor

clf = LocalOutlierFactor(
    n_neighbors=20,        # Number of neighbors for density estimation
    contamination='auto',  # Expected outlier fraction (auto-determined)
    novelty=True           # Use for prediction on new data
)

# Train on control cells
clf.fit(control_pca)

# Predict on perturbed cells (-1 = outlier, 1 = inlier)
predictions = clf.predict(perturbed_pca)
```

**Advantages:**
- ✅ Sensitive to local density changes (good for subtle phenotypes)
- ✅ No assumptions about outlier distribution
- ✅ Fast (k-NN based)
- ✅ Works well with small sample sizes

**Disadvantages:**
- ❌ Sensitive to n_neighbors parameter
- ❌ May miss global outliers (only detects local anomalies)
- ❌ Performance degrades in high dimensions (use PCA first)

**Best for:**
- Perturbations causing localized phenotypic shifts
- Screens where phenotypes cluster in specific regions of transcriptional space
- When you expect heterogeneous phenotypes across perturbations

**Parameter tuning:**
```python
# More conservative (fewer outliers)
clf = LocalOutlierFactor(n_neighbors=30, contamination=0.03)

# More sensitive (more outliers)
clf = LocalOutlierFactor(n_neighbors=10, contamination=0.10)

# Adaptive (recommended starting point)
clf = LocalOutlierFactor(n_neighbors=20, contamination='auto')
```

---

### IsolationForest

**Algorithm:** Tree-based outlier detection that isolates outliers by randomly partitioning data.

**How it works:**
1. Build ensemble of isolation trees (random feature/split combinations)
2. Outliers are easier to isolate (fewer splits needed)
3. Compute anomaly score = average path length to isolate each cell
4. Cells with short path lengths are outliers

**Parameters:**
```python
from sklearn.ensemble import IsolationForest

clf = IsolationForest(
    n_estimators=100,       # Number of trees in ensemble
    contamination='auto',   # Expected outlier fraction
    random_state=42,        # For reproducibility
    max_features=1.0        # Fraction of features to use per tree
)

# Train on control cells
clf.fit(control_pca)

# Predict on perturbed cells
predictions = clf.predict(perturbed_pca)
```

**Advantages:**
- ✅ Handles high-dimensional data well
- ✅ Scalable to large datasets
- ✅ Robust to irrelevant features
- ✅ Detects global outliers effectively

**Disadvantages:**
- ❌ May miss subtle, localized phenotypes
- ❌ Requires more control cells for training (>100 recommended)
- ❌ Stochastic (results vary between runs, use random_state)

**Best for:**
- Perturbations causing strong, global transcriptional changes
- Large screens with many control cells
- When phenotypes are expected to be distinct from bulk population

**Parameter tuning:**
```python
# More trees (slower, more stable)
clf = IsolationForest(n_estimators=200, random_state=42)

# Fewer features per tree (more robust to noise)
clf = IsolationForest(n_estimators=100, max_features=0.5, random_state=42)
```

---

### OneClassSVM

**Algorithm:** Support vector machine that learns decision boundary around normal data (controls).

**How it works:**
1. Learn hyperplane that separates control cells from origin
2. Optimize margin (distance from hyperplane to origin)
3. Cells outside decision boundary are outliers
4. Uses kernel trick for non-linear boundaries (RBF kernel default)

**Parameters:**
```python
from sklearn.svm import OneClassSVM

clf = OneClassSVM(
    kernel='rbf',    # Radial basis function kernel (non-linear)
    gamma='scale',   # Kernel coefficient (auto-scaled)
    nu=0.1           # Upper bound on outlier fraction
)

# Train on control cells
clf.fit(control_pca)

# Predict on perturbed cells
predictions = clf.predict(perturbed_pca)
```

**Advantages:**
- ✅ Learns complex, non-linear decision boundaries
- ✅ Theoretically well-founded (maximum margin)
- ✅ Works with small sample sizes

**Disadvantages:**
- ❌ Slow (O(n²) to O(n³) time complexity)
- ❌ Sensitive to hyperparameters (gamma, nu)
- ❌ Difficult to interpret

**Best for:**
- Perturbations with complex, non-linear phenotypic manifolds
- Small to medium screens (<10,000 perturbations)
- When computational time is not limiting

**Parameter tuning:**
```python
# More strict (fewer outliers)
clf = OneClassSVM(kernel='rbf', nu=0.05)

# More lenient (more outliers)
clf = OneClassSVM(kernel='rbf', nu=0.15)

# Linear kernel (faster, for linear separability)
clf = OneClassSVM(kernel='linear', nu=0.1)
```

---

## Method Comparison

### Empirical Performance

| Method | Speed | Sensitivity | False Positive Rate | Best Use Case |
|--------|-------|-------------|-------------------|---------------|
| LocalOutlierFactor | Fast | High | Low (if tuned) | Subtle, localized phenotypes |
| IsolationForest | Medium | Medium | Medium | Strong, global phenotypes |
| OneClassSVM | Slow | Medium | Low | Complex, non-linear phenotypes |

### Recommended Method Selection

**Start with LocalOutlierFactor:**
- Default choice for most screens
- Good balance of speed and sensitivity
- Works well across different phenotype types

**Switch to IsolationForest if:**
- LocalOutlierFactor yields too many false positives (>10% control outliers)
- Large screen with many control cells (>500)
- Strong phenotypes expected

**Switch to OneClassSVM if:**
- Need non-linear decision boundaries
- Small screen (<500 perturbations)
- Complex phenotypic patterns observed in PCA

### Ensemble Approach

For maximum confidence, use multiple methods and require agreement:

```python
from sklearn.neighbors import LocalOutlierFactor
from sklearn.ensemble import IsolationForest

# Train multiple detectors
lof = LocalOutlierFactor(novelty=True).fit(control_pca)
iso = IsolationForest(random_state=42).fit(control_pca)

# Predict with both
pred_lof = lof.predict(perturbed_pca)
pred_iso = iso.predict(perturbed_pca)

# Consensus: call outlier only if both agree
consensus = (pred_lof == -1) & (pred_iso == -1)

print(f"LOF outliers: {(pred_lof == -1).sum()}")
print(f"IsolationForest outliers: {(pred_iso == -1).sum()}")
print(f"Consensus outliers: {consensus.sum()}")
```

---

## Differential Expression Methods

### t-test (Welch's t-test)

**Algorithm:** Parametric test comparing means of two groups.

**How it works:**
1. Calculate mean and variance for each group (perturbed vs control)
2. Compute t-statistic: difference in means / pooled standard error
3. Calculate p-value from t-distribution
4. Adjust for multiple testing (Benjamini-Hochberg)

**Implementation:**
```python
import diffxpy.api as de

# Run t-test
test = de.test.t_test(
    data=adata,
    grouping='gene',     # Column with group labels
    is_logged=True       # Data is log-transformed
)

# Get results
de_results = test.summary()
de_results_sig = de_results[de_results['pval'] < 0.05]
```

**Advantages:**
- ✅ Fast (closed-form solution)
- ✅ Interpretable (mean difference, effect size)
- ✅ Works well with log-normalized scRNA-seq data
- ✅ Appropriate for screening purposes (preliminary hits)

**Disadvantages:**
- ❌ Assumes normality (approximately satisfied by log-transformation)
- ❌ Less precise p-values than count-based methods
- ❌ Ignores dropout (zero-inflation) in scRNA-seq data

**Best for:**
- Initial hit screening
- Large screens (genome-wide) requiring speed
- Log-normalized data

**Assumptions:**
- Data is approximately normally distributed (log-transformation helps)
- Samples are independent
- Variances are not necessarily equal (Welch's correction handles this)

---

### Wilcoxon Rank-Sum Test

**Algorithm:** Non-parametric test comparing distributions of two groups.

**How it works:**
1. Rank all observations across both groups
2. Compute sum of ranks for each group
3. Calculate test statistic (U-statistic)
4. Compute p-value from rank distribution

**Implementation:**
```python
import diffxpy.api as de

# Run Wilcoxon test
test = de.test.wilcoxon(
    data=adata,
    grouping='gene'
)

de_results = test.summary()
```

**Advantages:**
- ✅ No distribution assumptions (non-parametric)
- ✅ Robust to outliers
- ✅ Works with non-normal data

**Disadvantages:**
- ❌ Slower than t-test
- ❌ Less power than t-test if normality assumptions met
- ❌ No direct effect size estimate (log fold-change)

**Best for:**
- Small sample sizes (<50 cells per group)
- Non-normal distributions
- When robustness is more important than power

---

### Negative Binomial (DESeq2/edgeR-style)

**Algorithm:** Generalized linear model (GLM) for count data with overdispersion.

**How it works:**
1. Model counts as negative binomial distribution
2. Estimate dispersion parameter per gene
3. Fit GLM: log(expression) ~ group + covariates
4. Likelihood ratio test or Wald test for significance

**Implementation:**
```python
import diffxpy.api as de

# Run negative binomial test (requires raw counts)
test = de.test.wald(
    data=adata,
    formula_loc="~ 1 + gene",  # Model formula
    factor_loc_totest="gene"    # Factor to test
)

de_results = test.summary()
```

**Advantages:**
- ✅ Accurate p-values (models count distribution explicitly)
- ✅ Handles overdispersion (variance > mean)
- ✅ Can include covariates (batch, QC metrics)
- ✅ Shrinkage of dispersion estimates improves power

**Disadvantages:**
- ❌ Slow (iterative fitting)
- ❌ Requires raw counts (not log-normalized)
- ❌ Can fail to converge for some genes

**Best for:**
- Final validation of hits
- Small to medium screens (< 1,000 perturbations)
- When precise p-values are critical
- Publishing results (gold standard method)

---

### MAST (Hurdle Model)

**Algorithm:** Two-part generalized linear model for zero-inflated scRNA-seq data.

**How it works:**
1. **Part 1 (Discrete)**: Logistic regression for detection rate (zero vs non-zero)
2. **Part 2 (Continuous)**: Linear model for expression level (conditional on non-zero)
3. Combine p-values from both parts (likelihood ratio test)

**Implementation:**
```python
# Requires MAST R package via rpy2
# Not included in diffxpy, use R directly

# R code:
# library(MAST)
# sca <- FromMatrix(exprsArray = expr_matrix,
#                  cData = cell_metadata,
#                  fData = gene_metadata)
# zlm_fit <- zlm(~ condition + cngeneson, sca)
# summary_zlm <- summary(zlm_fit, doLRT='conditionPerturbed')
```

**Advantages:**
- ✅ Explicitly models zero-inflation (dropout)
- ✅ Accounts for cellular detection rate (cngeneson)
- ✅ Designed specifically for scRNA-seq

**Disadvantages:**
- ❌ Very slow (double GLM per gene)
- ❌ Requires R installation
- ❌ Complex interpretation (two p-values per gene)

**Best for:**
- Final hit validation
- Small screens (<100 perturbations)
- When dropout is severe (>50% zeros)

---

## Method Comparison

### Speed Comparison (1,000 genes, 100 cells per group)

| Method | Time | Memory |
|--------|------|--------|
| t-test | <1 sec | Low |
| Wilcoxon | ~5 sec | Low |
| Negative binomial | ~30 sec | Medium |
| MAST | ~5 min | High |

### Recommended Pipeline

**Stage 1 - Initial screening (all perturbations):**
```python
# Use t-test for speed
test = de.test.t_test(data=adata, grouping='gene', is_logged=True)
```

**Stage 2 - Hit refinement (top 100 hits):**
```python
# Use negative binomial for precision
test = de.test.wald(data=adata_raw, formula_loc="~ 1 + gene")
```

**Stage 3 - Final validation (top 10 hits):**
```python
# Use MAST or validate experimentally
# (Not critical for computational screens)
```

---

## Multiple Testing Correction

### Benjamini-Hochberg (FDR)

**Default choice for genome-wide screens:**

```python
from statsmodels.stats.multitest import multipletests

# Correct p-values
_, qvals, _, _ = multipletests(pvals, method='fdr_bh')

# Filter by FDR threshold
sig_genes = de_results[qvals < 0.05]
```

**FDR interpretation:**
- FDR = 0.05 means 5% of discoveries are expected false positives
- More permissive than Bonferroni (controls family-wise error rate)
- Appropriate for exploratory screens

### Bonferroni Correction

**Conservative, for small targeted screens:**

```python
# Correct p-values
alpha_corrected = 0.05 / len(pvals)
sig_genes = de_results[de_results['pval'] < alpha_corrected]
```

**When to use:**
- Small screens (<100 perturbations)
- When false positives are very costly
- Final validation experiments

### Permutation-Based FDR

**For complex designs or when distribution assumptions unclear:**

```python
# Permute group labels 1000 times
n_permutations = 1000
null_pvals = []

for i in range(n_permutations):
    # Permute labels
    adata_permuted = adata.copy()
    adata_permuted.obs['gene'] = np.random.permutation(adata.obs['gene'])

    # Run DE test
    test = de.test.t_test(data=adata_permuted, grouping='gene')
    null_pvals.extend(test.summary()['pval'])

# Estimate FDR
fdr = np.mean(np.array(null_pvals) < threshold) / np.mean(real_pvals < threshold)
```

---

## Effect Size Metrics

### Log2 Fold-Change

**Most common effect size measure:**

```python
# Calculate log2 fold-change
log2fc = np.log2(mean_perturbed / mean_control)

# Filter by combined criteria
sig_hits = de_results[(de_results['pval'] < 0.05) & (abs(de_results['log2fc']) > 0.5)]
```

**Thresholds:**
- |log2FC| > 0.5: Modest effect (1.4-fold change)
- |log2FC| > 1.0: Strong effect (2-fold change)
- |log2FC| > 2.0: Very strong effect (4-fold change)

### Cohen's d

**Standardized effect size (mean difference / pooled SD):**

```python
# Calculate Cohen's d
def cohens_d(group1, group2):
    mean1, mean2 = group1.mean(), group2.mean()
    sd1, sd2 = group1.std(), group2.std()
    n1, n2 = len(group1), len(group2)
    pooled_sd = np.sqrt(((n1-1)*sd1**2 + (n2-1)*sd2**2) / (n1 + n2 - 2))
    return (mean1 - mean2) / pooled_sd
```

**Interpretation:**
- |d| < 0.2: Small effect
- |d| = 0.5: Medium effect
- |d| > 0.8: Large effect

---

## Practical Recommendations

### Outlier Detection

1. **Start with LocalOutlierFactor** (default: n_neighbors=20, contamination='auto')
2. **Check control outlier rate**: Should be <5%
3. **If too many control outliers**: Lower contamination or increase n_neighbors
4. **If too few hits**: Try IsolationForest or lower n_neighbors

### Differential Expression

1. **Use t-test for initial screening** (fast, sufficient for hit calling)
2. **Validate top hits with negative binomial** (more precise p-values)
3. **Apply FDR correction** (Benjamini-Hochberg for genome-wide screens)
4. **Filter by effect size**: Require |log2FC| > 0.5 in addition to p < 0.05

### Reporting

**Always report:**
- Statistical method used
- Multiple testing correction method
- Effect size metric and thresholds
- Number of tests performed
- Sample sizes per group

**Example:**
> "Differential expression was assessed using Welch's t-test on log-normalized counts. P-values were corrected for multiple testing using the Benjamini-Hochberg procedure (FDR < 0.05). Genes with FDR < 0.05 and |log2FC| > 0.5 were considered significant."
