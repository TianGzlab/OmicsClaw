# Distance Metrics Guide for Clustering

Choosing the right distance metric is critical for clustering success.

---

## Quick Selection Guide

| Data Type | Recommended Metric | Why |
|-----------|-------------------|-----|
| **Gene expression** | Correlation (1 - Pearson) | Focus on pattern similarity, not magnitude |
| **Normalized continuous data** | Euclidean | Standard for most applications |
| **Data with outliers** | Manhattan or Robust methods | Less sensitive to extreme values |
| **High-dimensional sparse** | Cosine | Handles sparsity well |
| **Ranked/ordinal data** | Spearman correlation | Preserves rank order |

---

## Distance Metrics

### Euclidean Distance

**Formula:**
```
d(x, y) = √(Σ (x_i - y_i)²)
```

**Properties:**
- Most common metric
- Measures "straight-line" distance
- Sensitive to magnitude differences
- Affected by feature scales

**Use when:**
- ✅ Data is normalized/standardized
- ✅ All features have similar importance
- ✅ Magnitude differences are meaningful

**Avoid when:**
- ❌ Features have different scales (normalize first!)
- ❌ Data has outliers
- ❌ Interested in patterns, not magnitudes

**Example:** Patient clustering by clinical measurements (all standardized)

---

### Manhattan Distance (L1)

**Formula:**
```
d(x, y) = Σ |x_i - y_i|
```

**Properties:**
- Sum of absolute differences
- More robust to outliers than Euclidean
- Geometric interpretation: "city block" distance

**Use when:**
- ✅ Data has outliers
- ✅ Features measured on different scales
- ✅ Grid-like structure

**Example:** Spatial data, feature counts

---

### Correlation Distance (1 - Pearson)

**Formula:**
```
d(x, y) = 1 - correlation(x, y)
```

**Properties:**
- Measures pattern similarity, ignores magnitude
- Range: [0, 2] (0 = perfect correlation, 2 = perfect anti-correlation)
- Invariant to linear transformations

**Use when:**
- ✅ Gene expression data (temporal or spatial patterns)
- ✅ Time series clustering
- ✅ Pattern matters more than magnitude
- ✅ Features on different scales

**Avoid when:**
- ❌ Magnitude is important
- ❌ Data has many zeros (unstable)

**Example:** Gene clustering (genes with similar patterns across samples)

---

### Spearman Correlation Distance

**Formula:**
```
d(x, y) = 1 - spearman_correlation(x, y)
```

**Properties:**
- Based on ranks, not raw values
- More robust to outliers than Pearson
- Captures monotonic relationships

**Use when:**
- ✅ Ordinal data
- ✅ Non-linear monotonic relationships
- ✅ Outliers present
- ✅ Ranked data (e.g., competition rankings)

**Example:** Ordinal clinical scores, ranked features

---

### Cosine Distance

**Formula:**
```
d(x, y) = 1 - (x·y) / (||x|| ||y||)
```

**Properties:**
- Measures angle between vectors
- Invariant to vector magnitude
- Range: [0, 2]
- Handles sparse data well

**Use when:**
- ✅ High-dimensional sparse data (e.g., text)
- ✅ Direction matters more than magnitude
- ✅ Document clustering

**Avoid when:**
- ❌ Magnitude is important
- ❌ Low-dimensional dense data

**Example:** Text clustering (TF-IDF vectors), topic modeling

---

### Canberra Distance

**Formula:**
```
d(x, y) = Σ |x_i - y_i| / (|x_i| + |y_i|)
```

**Properties:**
- Weighted version of Manhattan
- Emphasizes differences near zero
- Sensitive to small changes

**Use when:**
- ✅ Features with many zeros
- ✅ Small differences are important

**Example:** Ecological data, species abundance

---

### Chebyshev Distance (L∞)

**Formula:**
```
d(x, y) = max_i |x_i - y_i|
```

**Properties:**
- Maximum difference across all features
- Emphasizes largest discrepancy

**Use when:**
- ✅ Maximum deviation is critical
- ✅ Quality control (any feature above threshold)

**Example:** Anomaly detection, quality control

---

## Choosing the Right Metric

### Decision Tree

```
What type of data do you have?
│
├─ Gene expression / Time series
│  ├─ Care about patterns? → Correlation distance
│  └─ Care about magnitude? → Euclidean (normalized)
│
├─ Continuous measurements
│  ├─ Outliers present? → Manhattan
│  ├─ Normalized data? → Euclidean
│  └─ Different scales? → Correlation or normalize first
│
├─ Sparse high-dimensional
│  └─ → Cosine distance
│
└─ Ordinal/ranked
   └─ → Spearman correlation
```

---

## Data Preprocessing for Distance Metrics

### Standardization (Z-score)

**When:** Using Euclidean or Manhattan
**How:** `(x - mean) / std`
**Effect:** Features have mean=0, std=1

### Min-Max Scaling

**When:** Want features in [0,1]
**How:** `(x - min) / (max - min)`
**Effect:** All features in same range

### Log Transform

**When:** Right-skewed data
**How:** `log2(x + 1)`
**Effect:** Reduces impact of large values

### Robust Scaling

**When:** Data with outliers
**How:** `(x - median) / IQR`
**Effect:** Uses robust statistics

---

## Metric Comparison Example

**Scenario:** 100 samples, 5000 genes, gene expression data

### Option 1: Euclidean (normalized)
```python
# Normalize data
data_norm = (data - data.mean(axis=0)) / data.std(axis=0)
distance = pdist(data_norm, metric='euclidean')
```
**Result:** Clusters by overall expression level

### Option 2: Correlation
```python
distance = pdist(data, metric='correlation')
```
**Result:** Clusters by expression pattern (ignores level)

### Recommendation:
- Use **correlation** for gene expression (pattern similarity)
- Use **Euclidean** only if absolute expression level matters

---

## Common Pitfalls

### Pitfall 1: Not normalizing before Euclidean
**Problem:** Features with larger scales dominate
**Solution:** Standardize (z-score) all features

### Pitfall 2: Using Euclidean for gene expression
**Problem:** Genes with same pattern but different levels cluster apart
**Solution:** Use correlation distance

### Pitfall 3: Correlation with sparse data
**Problem:** Unstable with many zeros
**Solution:** Filter features, use cosine, or add pseudocount

### Pitfall 4: Wrong metric for hierarchical clustering
**Problem:** Ward linkage requires Euclidean
**Solution:** Check compatibility (ward + euclidean only)

---

## Linkage Method Compatibility

| Linkage | Compatible Metrics |
|---------|-------------------|
| Ward | **Euclidean only** |
| Average | Any metric |
| Complete | Any metric |
| Single | Any metric |

---

## Testing Multiple Metrics

**Recommendation:** Try 2-3 metrics and compare

```python
from scripts.distance_metrics import compare_distance_metrics

metrics = ["euclidean", "correlation", "manhattan"]
distance_matrices = compare_distance_metrics(data, metrics)

# Cluster with each, compare silhouette scores
```

**Interpret:**
- Similar results → Choice doesn't matter much
- Different results → Domain knowledge needed

---

## Metric-Specific Considerations

### For Gene Expression
1. **Correlation** - Standard choice
2. Consider **Spearman** if outliers present
3. Avoid **Euclidean** unless magnitude matters

### For Clinical Data
1. **Euclidean** after standardization
2. **Manhattan** if outliers suspected
3. Consider mixed-type distances for categorical variables

### For Proteomics/Metabolomics
1. **Correlation** for patterns
2. **Euclidean** (log-transformed) for abundance
3. Consider **Canberra** for sparse data

### For Spatial Data
1. **Euclidean** for true spatial clustering
2. **Manhattan** for grid-like structures

---

## Advanced: Custom Distance Functions

For specialized needs, define custom distance:

```python
from scipy.spatial.distance import pdist

def custom_distance(u, v):
    # Your distance calculation
    return distance

distances = pdist(data, metric=custom_distance)
```

---

## Further Reading

1. Deza, M.M. & Deza, E. (2009). "Encyclopedia of Distances." Springer.

2. Cha, S.H. (2007). "Comprehensive survey on distance/similarity measures between probability density functions." *International Journal of Mathematical Models and Methods in Applied Sciences*.
