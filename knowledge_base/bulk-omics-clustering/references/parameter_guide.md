# Clustering Parameter Guide

Detailed guide to parameter selection and tuning for each clustering method.

---

## Hierarchical Clustering

### Linkage Methods

**ward**
- Minimizes within-cluster variance
- Produces compact, spherical clusters
- **Only works with Euclidean distance**
- Best for: Most general-purpose applications
- Default choice for hierarchical clustering

**average**
- Uses average distance between all point pairs
- More robust than complete linkage
- Works with any distance metric
- Best for: Balanced cluster shapes

**complete**
- Uses maximum distance between clusters
- Produces very compact clusters
- Sensitive to outliers
- Best for: When tight clusters desired

**single**
- Uses minimum distance between clusters
- Can create elongated "chain" clusters
- Useful for: Detecting connected components
- Warning: Sensitive to noise

### When to Use Each

```
Euclidean distance → ward (default)
Other metrics → average
Compact clusters needed → complete
Chain-like structures → single
```

---

## K-means Parameters

### n_clusters
- **Description**: Number of clusters to form
- **Range**: 2 to sqrt(n_samples) typically
- **Selection**: Use elbow method, silhouette, or gap statistic
- **Rule of thumb**: Start with domain knowledge if available

### n_init
- **Description**: Number of random initializations
- **Default**: 10 (increase for production)
- **Recommended**: 50-100 for important analyses
- **Why**: K-means sensitive to initialization
- **Trade-off**: Higher = more robust but slower

### max_iter
- **Description**: Maximum iterations per run
- **Default**: 300
- **Typical**: 100-500 sufficient
- **Check**: Model.n_iter_ to see if converged

### method variants

**kmeans** (standard)
- Best for: Most applications
- Speed: Medium
- Memory: O(nk)

**minibatch**
- Best for: Very large datasets (>100k samples)
- Speed: 3-10x faster than standard
- Accuracy: Slightly lower quality
- batch_size: min(1000, n_samples)

**kmedoids**
- Best for: Outlier-robust clustering
- Speed: Slower than k-means
- Advantage: Uses actual data points as centers
- Requires: scikit-learn-extra package

---

## HDBSCAN Parameters

### min_cluster_size
- **Description**: Minimum samples per cluster
- **Range**: 5 to n_samples/10
- **Effect**:
  - Smaller → more, smaller clusters
  - Larger → fewer, denser clusters
- **Recommended starting values**:
  - Small data (<500): 5-15
  - Medium data (500-5000): 15-50
  - Large data (>5000): 50-100
- **Tuning**: Try 2-3 values, compare results

### min_samples
- **Description**: Core point density threshold
- **Default**: Same as min_cluster_size (recommended)
- **Range**: 1 to min_cluster_size
- **Effect**:
  - Lower → more points included in clusters
  - Higher → more conservative, more noise points
- **When to adjust**:
  - Decrease if too many noise points
  - Increase if clusters not dense enough

### metric
- **Options**: Same as distance metrics (euclidean, manhattan, etc.)
- **Default**: euclidean
- **For gene expression**: Consider correlation

### cluster_selection_method
- **"eom"** (Excess of Mass): Default, generally best
- **"leaf"**: More granular clusters
- **When to use leaf**: Want more, smaller clusters

### Example tuning workflow

```python
# Try multiple min_cluster_size values
from scripts.density_clustering import tune_hdbscan_min_cluster_size

results = tune_hdbscan_min_cluster_size(
    data,
    min_cluster_sizes=[10, 20, 30, 50, 100]
)

# Choose based on:
# 1. Reasonable number of clusters
# 2. Low noise percentage (<10%)
# 3. Biological interpretability
```

---

## GMM Parameters

### n_components
- **Description**: Number of Gaussian components (clusters)
- **Selection**: Use BIC/AIC criterion
- **Function**: `select_gmm_components_bic()` in model_based_clustering.py

### covariance_type

**"full"** (most flexible)
- Each cluster has own covariance matrix
- Can model elliptical clusters of any orientation
- Parameters: k × d × (d+1) / 2
- Best for: General use, overlapping clusters
- **Default choice**

**"tied"**
- All clusters share same covariance
- Assumes similar cluster shapes
- Parameters: d × (d+1) / 2
- Best for: When clusters have similar spread

**"diag"**
- Diagonal covariance (features independent within cluster)
- Axis-aligned elliptical clusters
- Parameters: k × d
- Best for: High-dimensional data, feature independence

**"spherical"**
- Single variance per cluster (spherical)
- Most constrained, fewest parameters
- Parameters: k
- Best for: Compact, similar-sized clusters

### Selection strategy

```python
# Compare covariance types
from scripts.model_based_clustering import compare_covariance_types

results = compare_covariance_types(data, n_components=5)

# Choose lowest BIC (or AIC)
best_type = min(results.keys(), key=lambda x: results[x]['bic'])
```

### n_init
- **Description**: Number of initializations
- **Default**: 10
- **Recommended**: 10-20 sufficient
- **Less critical** than k-means (EM algorithm more stable)

---

## PCA Parameters

### n_components (fixed number)
- **Description**: Number of PCs to keep
- **Selection strategies**:
  - Variance threshold: Keep PCs explaining 80-95% variance
  - Elbow method: Plot explained variance
  - Rule of thumb: 20-50 components for clustering

### variance_threshold (automatic)
- **Description**: Keep PCs explaining this fraction of variance
- **Typical values**: 0.80, 0.90, 0.95
- **Recommended**: 0.90-0.95 for clustering
- **Trade-off**: More variance = more components = slower clustering

### When to use PCA

```
Features > 1000 → Always use PCA (keep 90-95% variance)
Features 100-1000 → Consider PCA (optional but recommended)
Features < 100 → Can skip PCA
```

---

## UMAP Parameters

### n_neighbors
- **Description**: Local neighborhood size
- **Range**: 5-50
- **Effect**:
  - Smaller (5-15) → local structure emphasized
  - Larger (30-50) → global structure emphasized
- **Default**: 15 (good for most cases)
- **For clustering**: 10-30 typical

### min_dist
- **Description**: Minimum distance between points in embedding
- **Range**: 0.0-0.99
- **Effect**:
  - Smaller (0.0-0.1) → tighter clusters
  - Larger (0.3-0.5) → more spread out
- **Default**: 0.1 (good for visualization)
- **For clustering input**: 0.0-0.1

### n_components
- **For visualization**: 2 or 3
- **For clustering**: 10-50 (like PCA)
- **Trade-off**: More components = more structure but slower

### metric
- Same as distance metrics
- Default: euclidean
- For gene expression: Consider correlation

---

## Validation Parameters

### Bootstrap Stability Analysis

**n_bootstrap**
- **Description**: Number of bootstrap iterations
- **Minimum**: 50
- **Recommended**: 100
- **For publication**: 100-500
- **Trade-off**: More = more reliable but slower

**sample_fraction**
- **Description**: Fraction of samples in each bootstrap
- **Default**: 0.8 (80% of samples)
- **Range**: 0.6-0.9
- **Don't use**: <0.5 or >0.95

---

## Parameter Tuning Strategies

### Strategy 1: Grid Search (Systematic)

```python
# Example: Tune k-means
k_values = range(2, 11)
results = []

for k in k_values:
    labels, _, _ = kmeans_clustering(data, n_clusters=k)
    silhouette = silhouette_score(data, labels)
    results.append((k, silhouette))

# Choose k with best silhouette
```

### Strategy 2: Coarse-to-Fine

1. **Coarse search**: Test wide range with large steps
   - k-means: k = [2, 5, 10, 15, 20]
   - HDBSCAN: min_cluster_size = [10, 50, 100]

2. **Fine search**: Narrow down to best region
   - k-means: If k=5 best, try [3, 4, 5, 6, 7]
   - HDBSCAN: If 50 best, try [30, 40, 50, 60, 70]

### Strategy 3: Use Defaults First

1. Start with default parameters
2. Evaluate with validation metrics
3. Only tune if results unsatisfactory
4. Focus on most impactful parameters:
   - k-means: **n_clusters**
   - HDBSCAN: **min_cluster_size**
   - GMM: **n_components**, **covariance_type**

---

## Common Parameter Issues

### Issue: K-means gives different results each time
**Cause**: Random initialization
**Solution**: Increase `n_init` to 50-100

### Issue: HDBSCAN labels everything as noise
**Cause**: min_cluster_size too large
**Solution**: Decrease min_cluster_size by half

### Issue: HDBSCAN finds too many tiny clusters
**Cause**: min_cluster_size too small
**Solution**: Increase min_cluster_size

### Issue: GMM BIC keeps decreasing
**Cause**: No clear optimal k
**Solution**: Look for "elbow" or plateau, use silhouette score

### Issue: Hierarchical clustering very slow
**Cause**: Too many samples
**Solution**: Use k-means or subsample data

---

## Parameter Recording for Reproducibility

Always record:
- Method and version
- All non-default parameters
- Random seeds
- Data preprocessing parameters

```python
parameters = {
    'method': 'kmeans',
    'n_clusters': 5,
    'n_init': 50,
    'random_state': 42,
    'normalization': 'zscore',
    'pca_variance': 0.95
}

# Save
from scripts.export_results import export_parameters
export_parameters(parameters, 'clustering_parameters.json')
```

---

## Further Reading

- Scikit-learn documentation: Parameter descriptions and defaults
- HDBSCAN documentation: Extensive parameter guide with examples
- Original papers: Theoretical justification for parameters
