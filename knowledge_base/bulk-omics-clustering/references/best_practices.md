# Clustering Analysis Best Practices

General best practices for robust and reproducible clustering analysis.

---

## Data Preparation

### 1. Understand Your Data

**Before clustering:**
- [ ] Plot distributions of features
- [ ] Check for outliers
- [ ] Assess missingness patterns
- [ ] Understand feature scales
- [ ] Check for batch effects

**Questions to ask:**
- How many samples? (affects method choice)
- How many features? (may need dimensionality reduction)
- What are the features? (affects distance metric)
- Are there known groups? (for validation)

---

### 2. Handle Missing Data Properly

**Options:**
1. **Drop samples** with >20% missing values
2. **Drop features** with >50% missing values
3. **Impute** with mean/median (simple) or KNN (better)

**Don't:**
- ❌ Ignore missing values (will cause errors)
- ❌ Impute before splitting data (causes leakage)
- ❌ Use imputation methods that don't preserve structure

---

### 3. Normalize/Standardize Data

**When to normalize:**
- Features have different scales
- Using Euclidean or Manhattan distance
- Before PCA

**Methods:**
- **Z-score**: (x - mean) / std → Use for most cases
- **Min-Max**: (x - min) / (max - min) → Use for bounded data
- **Robust**: (x - median) / IQR → Use with outliers
- **Log transform**: log2(x + 1) → Use for right-skewed data

**Don't:**
- ❌ Normalize after clustering
- ❌ Skip normalization with Euclidean distance
- ❌ Mix normalized and raw features

---

### 4. Remove Batch Effects

**If multiple batches:**
1. Visualize with PCA (color by batch)
2. If batch effects present, correct before clustering
3. Use ComBat, limma, or similar methods

**Warning:** Don't remove biological signal when correcting batches!

---

## Dimensionality Reduction

### When to Use PCA Before Clustering

**Use PCA when:**
- ✅ More than 100-1000 features
- ✅ Features are correlated
- ✅ Want to reduce noise
- ✅ Computational speed is important

**How many components:**
- Keep 80-95% variance (typical)
- Or use elbow plot
- For 5000+ features → typically 20-50 PCs

**Don't:**
- ❌ Use too few PCs (<80% variance)
- ❌ Skip PCA for very high-dimensional data
- ❌ Use PCA on count data (use variance-stabilizing transform first)

---

## Clustering Method Selection

### Try Multiple Methods

**Recommended workflow:**
1. Start with **k-means** (fast, baseline)
2. Try **hierarchical** (dendrogram useful)
3. If unknown k, try **HDBSCAN**
4. For uncertainty, try **GMM**

**Compare results:**
- Adjusted Rand Index between methods
- If ARI > 0.7 → methods agree (good!)
- If ARI < 0.5 → methods disagree (investigate why)

---

### Don't Over-Cluster

**Warning signs:**
- Many clusters with <5% of samples
- Silhouette score decreases with more clusters
- Biological interpretation unclear

**Guidelines:**
- Minimum cluster size: 5-10 samples (or 2-5% of data)
- Maximum k: ~sqrt(n/2) as rough upper limit
- If k > 15, reconsider approach

---

## Validation and Quality Control

### Always Validate

**Required validations:**
1. **Internal**: Silhouette score > 0.5
2. **Stability**: Bootstrap analysis (mean > 0.8)
3. **Visual**: PCA/UMAP plots show separation
4. **Biological**: Clusters make sense (if applicable)

**Don't:**
- ❌ Trust a single metric
- ❌ Skip visualization
- ❌ Ignore low scores (<0.5 silhouette)

---

### Test Multiple k Values

**Don't:** Pick k=3 without testing alternatives

**Do:** Test k = 2 to ~15 (or sqrt(n))

**Evaluate:**
- Elbow plot
- Silhouette scores
- Calinski-Harabasz scores
- Gap statistic (if time permits)

**Look for consensus** across metrics

---

### Assess Stability

**Bootstrap resampling:**
```python
from scripts.stability_analysis import stability_analysis

results = stability_analysis(
    data, cluster_labels,
    n_bootstrap=100,
    sample_fraction=0.8
)
```

**Interpret:**
- Mean stability > 0.85 → Robust clusters
- Mean stability < 0.7 → Unreliable clusters

---

## Interpretation

### Characterize Clusters

**Always do:**
1. **Size distribution**: Check cluster sizes
2. **Feature analysis**: Find discriminating features
3. **Visualization**: Plot clusters in reduced dimensions
4. **Statistical tests**: ANOVA/Kruskal-Wallis for features

**Report:**
- Top features per cluster
- Enrichment analysis (if applicable)
- Cluster characteristics

---

### Biological Validation

**If biological data:**
- Check enrichment of known pathways
- Compare to published classifications
- Validate with external datasets
- Test biological hypotheses

**Don't:**
- ❌ Force biological interpretation on poor clusters
- ❌ Claim discovery without validation

---

## Reproducibility

### Set Random Seeds

**Always set:**
```python
random_state=42
np.random.seed(42)
```

**For k-means:** Use high `n_init` (50-100) for robustness

---

### Document Parameters

**Save:**
- All parameters used
- Software versions
- Random seeds
- Preprocessing steps

**Use:** `export_parameters()` function

---

### Version Control

**Track:**
- Input data version
- Code version
- Environment (requirements.txt or environment.yml)
- Results (cluster assignments)

---

## Common Mistakes to Avoid

### 1. Forgetting to Normalize
**Problem:** Features with large values dominate
**Solution:** Z-score normalization before Euclidean distance

### 2. Not Testing Multiple k
**Problem:** Miss optimal number of clusters
**Solution:** Try k = 2 to 15, use multiple metrics

### 3. Ignoring Low Validation Scores
**Problem:** Trust clustering that isn't meaningful
**Solution:** Silhouette < 0.5 → data may not cluster well

### 4. Using Wrong Distance Metric
**Problem:** Gene expression with Euclidean = magnitude, not pattern
**Solution:** Use correlation for patterns, Euclidean for magnitudes

### 5. Clustering Without Question
**Problem:** No clear goal
**Solution:** Define question first (patient subtypes? gene modules?)

### 6. Over-interpreting Results
**Problem:** Claim biological discovery without validation
**Solution:** Validate with external data, biological experiments

### 7. Ignoring Outliers
**Problem:** Outliers affect k-means, hierarchical clustering
**Solution:** Identify outliers first, use HDBSCAN, or remove

### 8. Not Visualizing
**Problem:** Miss obvious problems (batch effects, no separation)
**Solution:** Always plot PCA/UMAP before and after clustering

---

## Reporting Checklist

When reporting clustering results, include:

- [ ] **Data description**: n samples, n features, data type
- [ ] **Preprocessing**: Normalization, filtering, missing data
- [ ] **Method**: Algorithm, parameters, random seed
- [ ] **Number of clusters**: How k was chosen
- [ ] **Validation metrics**: Silhouette, Davies-Bouldin, stability
- [ ] **Visualization**: PCA/UMAP with clusters
- [ ] **Cluster sizes**: Distribution of samples
- [ ] **Characterization**: Top features per cluster
- [ ] **Biological validation**: If applicable
- [ ] **Code/data availability**: For reproducibility

---

## Example Good Practices Workflow

### Step 1: Explore Data (5-10% of time)
- Load data, check dimensions
- Plot feature distributions
- Check for missing values, outliers
- Visualize with PCA (look for batch effects)

### Step 2: Prepare Data (10-20% of time)
- Handle missing values
- Normalize/standardize
- Filter low-variance features
- Apply PCA if needed (>100 features)

### Step 3: Initial Clustering (20-30% of time)
- Try k-means with k = 2 to 15
- Plot elbow curve, silhouette scores
- Visualize top 3 k values in PCA space

### Step 4: Refine and Validate (30-40% of time)
- Test multiple methods (hierarchical, HDBSCAN, GMM)
- Bootstrap stability analysis
- Compare methods (ARI)
- Silhouette analysis per sample

### Step 5: Characterize (20-30% of time)
- Find discriminating features (ANOVA)
- Plot heatmap of top features
- Biological interpretation
- External validation (if possible)

### Step 6: Report and Export (5-10% of time)
- Export assignments, statistics
- Generate final plots
- Document parameters
- Write summary report

---

## Resources

### Online Tools
- **scikit-learn documentation**: https://scikit-learn.org/stable/modules/clustering.html
- **HDBSCAN**: https://hdbscan.readthedocs.io/

### Papers
1. **Clustering review**: Xu & Tian (2015). "A comprehensive survey of clustering algorithms."
2. **Validation**: Rousseeuw (1987). "Silhouettes: A graphical aid."
3. **Biological data**: D'haeseleer (2005). "How does gene expression clustering work?"

### Books
- Hastie et al. (2009). "The Elements of Statistical Learning." Chapter 14.
- Han et al. (2011). "Data Mining: Concepts and Techniques." Chapter 10.
