# Clustering Methods Comparison

This guide helps you choose the right clustering algorithm for your data.

---

## Quick Selection Guide

| Use Case | Recommended Method | Why |
|----------|-------------------|-----|
| Unknown # of clusters, any shape | **HDBSCAN** | Finds clusters automatically, handles arbitrary shapes |
| Hierarchical relationships important | **Hierarchical** | Produces dendrogram showing relationships |
| Large dataset (>10k samples), known k | **K-means** | Fast, scalable, works well for spherical clusters |
| Overlapping clusters, uncertainty needed | **GMM** | Probabilistic assignments, quantifies uncertainty |
| Small-medium dataset, exploring k | **Hierarchical or K-means** | Try both, compare results |

---

## Method Comparison

### Hierarchical Clustering

**Type:** Agglomerative (bottom-up)

**Strengths:**
- ✅ No need to specify k upfront
- ✅ Produces dendrogram showing cluster relationships
- ✅ Deterministic (no random initialization)
- ✅ Works well with any distance metric
- ✅ Can cut at different heights for different k values

**Limitations:**
- ❌ Slow on large datasets (O(n²) or O(n³))
- ❌ Cannot undo merge decisions
- ❌ Sensitive to outliers
- ❌ Limited to < 5000 samples practically

**Best for:**
- Exploring hierarchical structure in data
- Small-medium datasets
- When dendrogram visualization is valuable
- Gene/sample clustering in genomics

**Linkage methods:**
- **Ward**: Minimizes within-cluster variance (requires Euclidean distance)
- **Average**: Average distance between all pairs
- **Complete**: Maximum distance (produces compact clusters)
- **Single**: Minimum distance (can create elongated clusters)

---

### K-means Clustering

**Type:** Partitioning (centroid-based)

**Strengths:**
- ✅ Very fast, scalable to millions of samples
- ✅ Simple to understand and implement
- ✅ Works well with spherical, equal-sized clusters
- ✅ Can predict cluster for new samples

**Limitations:**
- ❌ Requires specifying k upfront
- ❌ Assumes spherical clusters of similar size
- ❌ Sensitive to initialization (run with multiple n_init)
- ❌ Sensitive to outliers
- ❌ Limited to Euclidean-like distances

**Best for:**
- Large datasets
- When k is known or can be estimated
- Data with relatively compact, spherical clusters
- When speed is critical

**Variants:**
- **K-means**: Standard algorithm
- **Mini-batch K-means**: Faster for very large data (>100k samples)
- **K-medoids**: More robust to outliers, uses actual data points as centers

---

### HDBSCAN (Hierarchical Density-Based Clustering)

**Type:** Density-based

**Strengths:**
- ✅ Automatically determines number of clusters
- ✅ Finds clusters of arbitrary shape
- ✅ Robust to noise (identifies outliers)
- ✅ Probabilistic membership scores
- ✅ More stable than DBSCAN

**Limitations:**
- ❌ Slower than k-means (though faster than DBSCAN)
- ❌ Requires tuning min_cluster_size parameter
- ❌ May struggle with clusters of very different densities
- ❌ Less interpretable than k-means/hierarchical

**Best for:**
- Unknown number of clusters
- Arbitrary cluster shapes (non-spherical)
- Data with noise/outliers
- When cluster density varies

**Key parameters:**
- **min_cluster_size**: Minimum samples per cluster (smaller = more clusters)
- **min_samples**: Core point threshold (higher = more conservative)

---

### Gaussian Mixture Models (GMM)

**Type:** Model-based (probabilistic)

**Strengths:**
- ✅ Soft (probabilistic) clustering
- ✅ Quantifies assignment uncertainty
- ✅ Can model overlapping clusters
- ✅ Flexible cluster shapes (with full covariance)
- ✅ Provides statistical model selection (BIC/AIC)

**Limitations:**
- ❌ Requires specifying k upfront
- ❌ Assumes Gaussian (normal) distributions
- ❌ Slower than k-means
- ❌ Can be sensitive to initialization

**Best for:**
- Overlapping clusters
- When uncertainty quantification is important
- Data approximately Gaussian
- Soft assignments needed

**Covariance types:**
- **Full**: Most flexible, each cluster has own covariance matrix
- **Tied**: All clusters share covariance (similar shapes)
- **Diagonal**: Features assumed independent
- **Spherical**: Simplest, assumes spherical clusters

---

## Decision Tree

```
Do you know the number of clusters (k)?
│
├─ Yes, I know k
│  │
│  ├─ Data > 10,000 samples? → K-means
│  ├─ Need uncertainty? → GMM
│  └─ Want dendrogram? → Hierarchical
│
└─ No, don't know k
   │
   ├─ Arbitrary cluster shapes? → HDBSCAN
   ├─ Need dendrogram? → Hierarchical (cut at different heights)
   └─ Relatively spherical? → K-means (try multiple k)
```

---

## Performance Comparison

### Computational Complexity

| Method | Time Complexity | Space Complexity |
|--------|-----------------|------------------|
| K-means | O(nkdi) | O(nk) |
| Hierarchical | O(n²log n) to O(n³) | O(n²) |
| HDBSCAN | O(n log n) | O(n) |
| GMM | O(nkdi) | O(nk) |

*n = samples, k = clusters, d = features, i = iterations*

### Scalability Guide

| Dataset Size | Recommended Methods |
|--------------|---------------------|
| < 1,000 | Any method |
| 1,000 - 5,000 | All except hierarchical |
| 5,000 - 50,000 | K-means, HDBSCAN, GMM |
| > 50,000 | Mini-batch K-means, HDBSCAN |

---

## Combining Methods

### Strategy 1: Hierarchical then K-means
1. Use hierarchical clustering on sample subset
2. Estimate k from dendrogram
3. Apply k-means to full dataset with this k

### Strategy 2: K-means then GMM
1. Use k-means for initial clustering
2. Refine with GMM for soft assignments

### Strategy 3: Multiple method consensus
1. Run multiple methods (e.g., k-means, hierarchical, GMM)
2. Compare results with adjusted Rand index
3. Use consensus clustering

---

## Common Pitfalls

### K-means
- **Issue**: Poor results with elongated clusters
- **Solution**: Try HDBSCAN or GMM with full covariance

### Hierarchical
- **Issue**: Slow on large data
- **Solution**: Subsample data or use k-means

### HDBSCAN
- **Issue**: Many noise points
- **Solution**: Decrease min_cluster_size, increase min_samples

### GMM
- **Issue**: BIC/AIC don't agree
- **Solution**: Use silhouette score, try different covariance types

---

## Example Scenarios

### Scenario 1: Patient stratification (RNA-seq, 200 samples)
- **Data**: 200 patients, 5000 genes
- **Goal**: Find disease subtypes
- **Recommendation**: Hierarchical (ward linkage) or K-means (try k=2-8)
- **Reasoning**: Medium dataset, likely spherical clusters, want dendrogram

### Scenario 2: Large-scale sample clustering (10,000 samples)
- **Data**: 10,000 samples, 1000 features
- **Goal**: Fast clustering
- **Recommendation**: K-means with multiple k values, use elbow + silhouette
- **Reasoning**: Large dataset requires scalable method

### Scenario 3: Unknown structure exploration
- **Data**: 1000 samples, unknown clusters
- **Goal**: Discover natural groupings
- **Recommendation**: HDBSCAN first, then validate with k-means
- **Reasoning**: No prior knowledge, want automatic k detection

### Scenario 4: Overlapping cell types (single-cell data)
- **Data**: 5000 cells, expect overlap
- **Goal**: Soft cell type assignments
- **Recommendation**: GMM with full covariance
- **Reasoning**: Biological cell types often overlap, need uncertainty

---

## References

1. Xu, D. & Tian, Y. (2015). "A comprehensive survey of clustering algorithms." *Annals of Data Science*.

2. McInnes, L. et al. (2017). "hdbscan: Hierarchical density based clustering." *JOSS*.

3. Rodriguez, M.Z. et al. (2019). "Clustering algorithms: A comparative approach." *PLOS ONE*.
