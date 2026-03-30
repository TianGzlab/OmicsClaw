# Clustering Decision Guide

Comprehensive guide for making critical clustering decisions with flowcharts, examples, and troubleshooting.

---

## Decision 1: Which Clustering Algorithm?

### Overview

Choosing the right clustering algorithm depends on dataset size, expected cluster shapes, whether you know k, and computational constraints.

### Algorithm Selection Table

| Algorithm | Best For | Pros | Cons | Sample Size | Requires k? |
|-----------|----------|------|------|-------------|-------------|
| **Hierarchical** | Exploration, visualization, biological interpretation | Dendrogram shows structure at all scales; deterministic; flexible k selection | Slow for >5k samples; high memory for distance matrix | <5k samples | No (cut tree later) |
| **K-means** | Large datasets, spherical clusters | Very fast; scales to millions of samples; simple interpretation | Requires k upfront; assumes spherical clusters; sensitive to initialization | >1k samples | Yes |
| **HDBSCAN** | Unknown k, outlier detection, arbitrary shapes | Finds k automatically; handles arbitrary shapes; marks outliers | Slow for >50k samples; parameter tuning can be tricky | 100-50k samples | No (automatic) |
| **GMM** | Soft clustering, uncertainty quantification | Probabilistic memberships; overlapping clusters; statistical framework | Requires k; assumes Gaussian distributions; can overfit | 100-10k samples | Yes |

### Decision Flowchart

```
START
  |
  ├─ Do you know k (number of clusters)?
  |   |
  |   ├─ NO → Do you want to detect outliers?
  |   |   |
  |   |   ├─ YES → HDBSCAN (automatic k + outlier detection)
  |   |   |
  |   |   └─ NO → Hierarchical (explore dendrogram, cut at any k)
  |   |
  |   └─ YES → How many samples do you have?
  |       |
  |       ├─ <5k samples → Do you need visualization?
  |       |   |
  |       |   ├─ YES → Hierarchical (dendrogram + known k)
  |       |   |
  |       |   └─ NO → Do clusters overlap?
  |       |       |
  |       |       ├─ YES → GMM (soft clustering)
  |       |       |
  |       |       └─ NO → K-means (efficient partitioning)
  |       |
  |       └─ >5k samples → K-means (fast, scalable)
```

### When to Use Each Algorithm

#### Hierarchical Clustering

**Use when:**
- ✅ You want to explore data structure before committing to k
- ✅ You need a dendrogram for publication/interpretation
- ✅ Sample size <5k (feasible computation)
- ✅ You want deterministic results (same every run)
- ✅ You need to show relationships between clusters

**Don't use when:**
- ❌ You have >10k samples (too slow, too much memory)
- ❌ You only care about final partitioning (k-means is faster)
- ❌ You have very high-dimensional data without PCA preprocessing

**Linkage methods:**
- **Ward** (default): Minimizes within-cluster variance, creates compact spherical clusters
- **Average**: More flexible cluster shapes, good for gene expression
- **Complete**: Avoids chaining, creates tight clusters
- **Single**: Can create elongated clusters, sensitive to outliers

#### K-means Clustering

**Use when:**
- ✅ You have >5k samples and need speed
- ✅ You know k or can test a range
- ✅ Clusters are roughly spherical/compact
- ✅ You want hard assignments (each sample to one cluster)
- ✅ You can run PCA preprocessing for high-dimensional data

**Don't use when:**
- ❌ Clusters have arbitrary shapes (use HDBSCAN)
- ❌ You don't know k at all (use hierarchical or HDBSCAN)
- ❌ You have extreme outliers (they will be forced into clusters)
- ❌ Clusters have very different sizes/densities

**Variants:**
- **K-means** (Lloyd's algorithm): Standard, uses centroids
- **K-means++**: Better initialization (recommended)
- **Mini-batch K-means**: For >100k samples, trades accuracy for speed
- **K-medoids**: Uses actual data points as centers, robust to outliers

#### HDBSCAN (Density-Based)

**Use when:**
- ✅ You don't know k and want automatic detection
- ✅ You expect arbitrary cluster shapes (non-spherical)
- ✅ You want outlier detection
- ✅ Clusters have varying densities
- ✅ You want hierarchical + density-based benefits

**Don't use when:**
- ❌ You have >50k samples (becomes very slow)
- ❌ All your data points should be in clusters (HDBSCAN marks noise)
- ❌ Clusters are well-separated and spherical (k-means is faster)
- ❌ You need exactly k clusters for downstream analysis

**Key parameters:**
- **min_cluster_size**: Minimum samples per cluster (start with 5-10)
- **min_samples**: Noise threshold (same as min_cluster_size is good default)

#### Gaussian Mixture Models (GMM)

**Use when:**
- ✅ You need soft clustering (probabilistic memberships)
- ✅ Clusters overlap and you want uncertainty estimates
- ✅ You assume clusters follow Gaussian distributions
- ✅ You want a statistical model framework
- ✅ You need to quantify cluster assignment confidence

**Don't use when:**
- ❌ You want hard assignments only (k-means is simpler)
- ❌ Clusters are not approximately Gaussian
- ❌ You have many features without PCA (model can overfit)
- ❌ You need maximum speed (GMM is slower than k-means)

**Covariance types:**
- **full**: Each cluster has its own full covariance matrix (most flexible)
- **tied**: All clusters share same covariance (assumes similar shapes)
- **diag**: Diagonal covariance (assumes features are independent)
- **spherical**: Single variance per cluster (like k-means)

### Common Decision Scenarios

**Scenario 1:** "I have 500 gene expression samples and don't know how many subtypes exist"
- **Solution:** Hierarchical clustering with correlation distance
- **Why:** Small sample size (efficient), explore dendrogram, cut at multiple k values, correlation handles expression patterns

**Scenario 2:** "I have 50,000 samples and know there should be 5 clusters"
- **Solution:** K-means with k=5 and n_init=50
- **Why:** Large sample size needs speed, known k, k-means scales well

**Scenario 3:** "I expect 3-4 clusters but also outliers from batch effects"
- **Solution:** HDBSCAN to identify outliers, then k-means on clean data
- **Why:** HDBSCAN finds outliers (-1 label), remove them, then efficient k-means

**Scenario 4:** "My clusters might overlap and I need confidence scores"
- **Solution:** GMM with appropriate k
- **Why:** Probabilistic memberships quantify overlap, soft clustering handles uncertainty

**Scenario 5:** "I want to compare multiple methods for publication"
- **Solution:** Run hierarchical, k-means, HDBSCAN, and GMM; compare validation metrics
- **Why:** Robust results agree across methods, shows thorough analysis

---

## Decision 2: Which Distance Metric?

### Overview

The distance metric determines how similarity is measured between samples/features. The right choice depends on data type, normalization, and what "similarity" means in your context.

### Distance Metric Comparison Table

| Metric | Best For | Properties | Sensitive To | Range |
|--------|----------|------------|--------------|-------|
| **Euclidean** | Normalized continuous data, physical measurements | Straight-line distance; all features weighted equally | Scale differences, outliers | [0, ∞) |
| **Correlation** | Gene expression, time series | Pattern similarity (shape), ignores magnitude | Missing values, zero-variance features | [0, 2] |
| **Manhattan** | High-dimensional data, outlier-robust | City-block distance; less sensitive to outliers | Scale differences | [0, ∞) |
| **Cosine** | Sparse data, text-like features, directional data | Angle between vectors; ignores magnitude | Zero vectors | [0, 2] |

### Distance Metric Decision Tree

```
START
  |
  ├─ What type of data?
  |   |
  |   ├─ Gene expression / Time series
  |   |   └─ Do you care about pattern similarity more than magnitude?
  |   |       ├─ YES → Correlation (1 - Pearson correlation)
  |   |       └─ NO → Euclidean (after normalization)
  |   |
  |   ├─ Proteomics / Metabolomics
  |   |   └─ Is data normalized?
  |   |       ├─ YES → Euclidean
  |   |       └─ NO → Normalize first, then Euclidean
  |   |
  |   ├─ Clinical / Mixed features
  |   |   └─ Do you have outliers?
  |   |       ├─ YES → Manhattan (robust)
  |   |       └─ NO → Euclidean
  |   |
  |   └─ High-dimensional / Sparse
  |       └─ Cosine (directional similarity)
```

### Detailed Metric Properties

#### Euclidean Distance

**Formula:** `d(x,y) = sqrt(Σ(xi - yi)²)`

**Use when:**
- ✅ Data is normalized (all features on same scale)
- ✅ Magnitude differences are meaningful
- ✅ Features have similar importance
- ✅ Data is continuous and not too sparse

**Properties:**
- Most commonly used metric
- Assumes all features contribute equally
- Sensitive to outliers (squared differences)
- Works well with k-means (minimizes Euclidean distance by design)

**Example:** Comparing normalized protein abundances where both pattern and magnitude matter

#### Correlation Distance

**Formula:** `d(x,y) = 1 - Pearson_correlation(x,y)`

**Use when:**
- ✅ Gene expression data (pattern similarity)
- ✅ Time-series data with different baselines
- ✅ You want to group samples with similar trends regardless of magnitude
- ✅ Features are co-regulated or follow similar patterns

**Properties:**
- Invariant to linear transformations (scale + shift)
- Range: [0, 2] where 0 = perfect correlation, 2 = perfect anti-correlation
- Works excellently with hierarchical clustering (average linkage)
- Can fail with zero-variance features (returns NaN)

**Example:** Clustering genes by expression pattern across conditions (high vs low expression levels don't matter, pattern does)

#### Manhattan Distance

**Formula:** `d(x,y) = Σ|xi - yi|`

**Use when:**
- ✅ Data has outliers
- ✅ High-dimensional data (curse of dimensionality)
- ✅ Features on different scales (more robust than Euclidean)
- ✅ You want robust clustering

**Properties:**
- Less sensitive to outliers than Euclidean (absolute vs squared)
- Also called L1 distance or city-block distance
- Often performs better in high dimensions
- Computationally efficient

**Example:** Clinical data with mixed continuous features that may have outliers

#### Cosine Distance

**Formula:** `d(x,y) = 1 - (x·y)/(||x|| ||y||)`

**Use when:**
- ✅ Sparse, high-dimensional data
- ✅ Direction matters more than magnitude
- ✅ Features represent counts or frequencies
- ✅ Data is strictly non-negative

**Properties:**
- Measures angle between vectors, not magnitude
- Range: [0, 2] where 0 = same direction
- Invariant to vector scaling
- Fails with zero vectors

**Example:** Document clustering, sparse gene expression matrices, directional data

### Feature Scaling Requirements

**Before using Euclidean or Manhattan:**
- ✅ **Z-score normalization** (mean=0, sd=1): Recommended for most cases
- ✅ **Min-max scaling** (range [0,1]): When you want bounded distances
- ✅ **Robust scaling** (median, IQR): When outliers present

**Correlation distance:**
- No scaling needed (inherently scale-invariant)
- But remove zero-variance features (cause NaN)

**Cosine distance:**
- No scaling needed (magnitude-invariant)
- Works directly on raw counts or frequencies

### When to Try Multiple Metrics

**Always try multiple metrics when:**
- You're doing exploratory analysis
- You have mixed feature types
- Clusters are unstable with one metric
- Results don't match biological expectations

**Compare metrics by:**
- Silhouette scores (which metric gives better separation?)
- Stability analysis (which is more robust?)
- Biological validation (which matches known groups?)

---

## Decision 3: How Many Clusters (k)?

### Overview

Determining the optimal number of clusters is often the hardest decision. Multiple methods exist, and they often disagree. Use multiple approaches and prioritize biological interpretability.

### Optimal k Determination Methods

#### 1. Elbow Method

**What it does:** Plots within-cluster sum of squares (inertia) vs k

**How to use:**
- Look for "elbow" where adding clusters gives diminishing returns
- Elbow = point where curve bends sharply

**Strengths:**
- ✅ Simple, intuitive
- ✅ Works with any clustering method

**Weaknesses:**
- ❌ Elbow often ambiguous or absent
- ❌ Subjective interpretation

**Best for:** Initial exploration, k-means clustering

#### 2. Silhouette Method

**What it does:** Measures how similar each point is to its own cluster vs other clusters

**How to use:**
- Compute average silhouette score for each k
- Choose k with highest average silhouette
- Silhouette ranges from -1 (wrong cluster) to +1 (perfect)

**Thresholds:**
- >0.7: Strong structure
- 0.5-0.7: Reasonable structure
- 0.25-0.5: Weak structure
- <0.25: No substantial structure

**Strengths:**
- ✅ Accounts for both cohesion and separation
- ✅ Works with any distance metric
- ✅ Per-sample scores identify misclassified points

**Weaknesses:**
- ❌ Computationally expensive for large datasets
- ❌ Favors equal-sized clusters

**Best for:** Final validation, comparing multiple k values

#### 3. Gap Statistic

**What it does:** Compares within-cluster dispersion to null reference distribution

**How to use:**
- Choose k where gap(k) is maximum
- Or use "1-standard-error rule": smallest k where gap(k) ≥ gap(k+1) - SE(k+1)

**Strengths:**
- ✅ Statistical rigor (compares to null)
- ✅ Works when no clear structure exists (suggests k=1)
- ✅ Less biased than elbow method

**Weaknesses:**
- ❌ Very slow (requires many bootstrap samples)
- ❌ Can be unstable with small samples

**Best for:** Publication-quality analysis, when you need statistical justification

#### 4. Calinski-Harabasz Index (Variance Ratio Criterion)

**What it does:** Ratio of between-cluster variance to within-cluster variance

**How to use:**
- Choose k with highest index
- Higher values = better defined clusters

**Strengths:**
- ✅ Very fast to compute
- ✅ Works well for compact, well-separated clusters

**Weaknesses:**
- ❌ Favors k-means-like solutions
- ❌ Can overestimate k

**Best for:** Quick screening of many k values

### Decision Strategy When Metrics Disagree

**Common scenario:** Elbow suggests k=4, Silhouette suggests k=3, Gap suggests k=5

**Strategy:**
1. **Prioritize Silhouette** (most robust for cluster quality)
2. **Check biological interpretability** (does k=3 make sense in your domain?)
3. **Test stability** at k=3, 4, and 5 (which is most reproducible?)
4. **Visualize** with PCA/UMAP (do you see 3, 4, or 5 groups?)
5. **Consider range** [k-1, k+1] for sensitivity analysis

### Biological Interpretability Considerations

**Ask these questions:**
- Does k match known biological subtypes?
- Can you explain what distinguishes each cluster?
- Are cluster sizes reasonable (not 1% vs 99%)?
- Do clusters correspond to experimental groups, tissues, stages?
- Can you find differentially expressed genes between clusters?

**Example:** If silhouette suggests k=7 but you only have 3 treatment groups, check:
- Are clusters splitting known groups? (may indicate batch effects)
- Are there true biological subtypes within groups? (subtype discovery)
- Is k=3 much worse than k=7? (sacrifice some metrics for interpretability)

### When k Doesn't Matter

**Hierarchical clustering:**
- Don't need to choose k upfront
- Cut dendrogram at multiple heights
- Report cluster membership at different k values

**HDBSCAN:**
- Finds k automatically
- Focus on tuning min_cluster_size instead
- Accept that some points are labeled as noise (-1)

### Practical Workflow for k Determination

```python
# 1. Test range of k values
from scripts.optimal_clusters import find_optimal_clusters

results = find_optimal_clusters(
    data, method="kmeans", k_range=range(2, 16),
    metrics=["elbow", "silhouette", "gap", "calinski"]
)

# 2. Examine plots for all metrics
# Look for agreement and reasonable patterns

# 3. Short-list 2-3 candidate k values
candidates = [3, 5, 7]  # Based on metric peaks

# 4. Test stability for each candidate
from scripts.stability_analysis import stability_analysis

for k in candidates:
    labels, _ = kmeans_clustering(data, n_clusters=k)
    stability = stability_analysis(data, labels, clustering_method="kmeans")
    print(f"k={k}: stability = {stability['mean_stability']:.3f}")

# 5. Visualize each candidate
for k in candidates:
    labels, _ = kmeans_clustering(data, n_clusters=k)
    plot_pca_scatter(pca_data, labels, output_path=f"pca_k{k}.png")

# 6. Choose based on: silhouette + stability + visualization + biology
# Prioritize biological interpretation over marginal metric improvements
```

---

## Decision 4: Dimensionality Reduction

### When to Use PCA Before Clustering

**Use PCA when:**
- ✅ You have >1000 features (genes, proteins, metabolites)
- ✅ Features are correlated (gene expression data)
- ✅ You want to reduce noise
- ✅ Computational cost is high
- ✅ You want to focus on major variation patterns

**Skip PCA when:**
- ❌ You have <100 features
- ❌ You want to interpret individual features
- ❌ Features are already uncorrelated
- ❌ You have sparse data (may want sparse methods instead)

### How Many PCA Components to Keep?

**General rules:**
- **80-95% variance explained**: Most common choice
- **Elbow in scree plot**: Where explained variance flattens
- **Kaiser criterion**: Keep components with eigenvalue >1
- **Parallel analysis**: Compare to random data

**Practical approach:**
```python
# Try multiple component counts
n_components_list = [20, 50, 100]

for n in n_components_list:
    pca_data, _, explained_var = apply_pca(data, n_components=n)
    print(f"n={n}: {explained_var.sum():.1%} variance explained")

    # Cluster and validate
    labels, _ = kmeans_clustering(pca_data, n_clusters=5)
    validation = validate_clustering(pca_data, labels)
    print(f"  Silhouette: {validation['silhouette']:.3f}")

# Choose n with good variance/silhouette trade-off
```

### UMAP: Visualization vs Clustering

**UMAP for visualization:**
- ✅ Create 2D embeddings for plotting
- ✅ Better preserves local structure than PCA
- ✅ Makes nice publication figures

**UMAP for clustering:**
- ⚠️ Can distort distances
- ⚠️ Results depend heavily on parameters
- ⚠️ May create artificial clusters
- **Recommendation:** Use PCA for clustering, UMAP for visualization only

---

## Decision 5: Validation Strategy

### Internal Validation (No Labels)

**Use when:** You don't have ground truth labels (most common)

**Metrics:**
- **Silhouette score**: Cluster cohesion and separation
- **Davies-Bouldin index**: Average similarity ratio (lower is better)
- **Calinski-Harabasz index**: Variance ratio (higher is better)

**Strategy:**
1. Compute all three metrics
2. Look for agreement
3. Silhouette >0.5 + Davies-Bouldin <1.0 = good clustering

### External Validation (Labels Available)

**Use when:** You have known groups (tissue types, treatment groups, etc.)

**Metrics:**
- **Adjusted Rand Index (ARI)**: Measures agreement with true labels (0-1)
- **Normalized Mutual Information (NMI)**: Information theoretic measure
- **Fowlkes-Mallows Index**: Geometric mean of precision and recall

**Strategy:**
- If ARI >0.7: Clustering matches known groups well
- If ARI 0.3-0.7: Partial agreement (may indicate subtypes)
- If ARI <0.3: Clustering finds different structure than labels

### Stability Testing

**Use when:** You want reproducible, robust clusters

**Method:**
1. Bootstrap resample your data (80% of samples)
2. Re-cluster each bootstrap
3. Measure consistency of cluster assignments
4. Stability >0.85 = very robust

**When stability is low (<0.7):**
- Try different k (may be unstable at this k)
- Try different algorithm
- Check for outliers or batch effects
- May indicate no strong clustering structure

### Biological Validation

**Use when:** You want biologically meaningful clusters

**Approaches:**
1. **Differential expression**: Find genes that distinguish clusters
2. **Pathway enrichment**: Are clusters enriched for biological functions?
3. **Clinical correlation**: Do clusters associate with outcomes/phenotypes?
4. **Literature validation**: Do clusters match known subtypes?

**Red flags:**
- Clusters separate by batch instead of biology
- No differentially expressed genes between clusters
- Clusters have no clinical/phenotypic differences
- Known subtypes split across multiple clusters

---

## Common Decision Scenarios (Comprehensive)

### Scenario 1: Small Exploratory Analysis
**Context:** 200 samples, 2000 genes, no idea about clusters

**Decisions:**
- Algorithm: Hierarchical (small dataset, exploration)
- Distance: Correlation (gene expression)
- k: Examine dendrogram, try k=2-10
- Dim reduction: PCA to 50 components (retain 90% variance)
- Validation: Silhouette + stability

### Scenario 2: Large-Scale Classification
**Context:** 10,000 samples, expecting 5 disease subtypes

**Decisions:**
- Algorithm: K-means (large dataset, known k)
- Distance: Euclidean (with z-score normalization)
- k: 5 (based on prior knowledge), validate with silhouette
- Dim reduction: PCA to 100 components
- Validation: Internal metrics + clinical correlation

### Scenario 3: Outlier Detection Focus
**Context:** 500 samples, suspect batch effects/outliers

**Decisions:**
- Algorithm: HDBSCAN (outlier detection)
- Distance: Manhattan (robust to outliers)
- k: Automatic (HDBSCAN finds it)
- Dim reduction: PCA to 30 components
- Validation: Identify outliers (-1 label), re-cluster clean data

### Scenario 4: Gene Pattern Discovery
**Context:** 5,000 genes, 50 samples, find co-expressed gene modules

**Decisions:**
- Algorithm: Hierarchical (visualization of gene relationships)
- Distance: Correlation (pattern similarity)
- k: Cut dendrogram at height corresponding to 10-20 modules
- Dim reduction: None (clustering in original space)
- Validation: Check for pathway enrichment in modules

### Scenario 5: Publication-Quality Analysis
**Context:** 400 samples, preparing manuscript, need robust results

**Decisions:**
- Algorithm: Compare hierarchical, k-means, HDBSCAN
- Distance: Try Euclidean and correlation
- k: Use gap statistic + silhouette, test stability
- Dim reduction: PCA with variance explained justification
- Validation: All internal metrics + stability + biological validation

### Scenario 6: Time-Series / Trajectory
**Context:** Developmental stages, time-course experiment

**Decisions:**
- Algorithm: Hierarchical (see progression) or HDBSCAN
- Distance: Correlation (pattern over time)
- k: Based on known stages or dendrogram
- Dim reduction: PCA + UMAP for trajectory visualization
- Validation: Check if clusters follow time order

---

## Decision Checklist

Before finalizing your clustering analysis, ensure:

- [ ] **Algorithm chosen** based on sample size, cluster shape expectations, and k knowledge
- [ ] **Distance metric selected** based on data type, normalization, and similarity definition
- [ ] **Optimal k determined** using multiple metrics (or method doesn't require k)
- [ ] **Dimensionality reduction** decision made (PCA components or original space)
- [ ] **Validation strategy** selected and executed
- [ ] **Computational resources** sufficient for chosen method
- [ ] **Results visualized** with PCA/UMAP to sanity-check
- [ ] **Cluster sizes** reasonable (not 1% vs 99%)
- [ ] **Stability tested** if results will be used for important decisions
- [ ] **Biological interpretation** considered and documented
- [ ] **Batch effects** checked and accounted for
- [ ] **Outliers** identified and handled appropriately
- [ ] **Multiple k values** tested for sensitivity analysis
- [ ] **Method comparison** performed if results are critical
- [ ] **Parameters documented** for reproducibility

---

## Troubleshooting Decision Problems

### Problem: "All my metrics disagree on optimal k"

**Solutions:**
1. Plot cluster results for k-1, k, k+1 (visualize with PCA)
2. Check stability at each k
3. Prioritize silhouette over other metrics
4. Consider biological interpretability
5. Report results for multiple k values

### Problem: "My clusters don't make biological sense"

**Check:**
1. Are you separating by batch instead of biology? (check PCA colored by batch)
2. Is your distance metric appropriate? (try correlation for gene expression)
3. Have you normalized your data properly?
4. Are there outliers dominating the clustering?
5. Try different algorithms (maybe data doesn't cluster well)

### Problem: "Clustering is very unstable"

**Solutions:**
1. Increase n_init for k-means (try 100+)
2. Try hierarchical instead (deterministic)
3. Reduce k (may be overfitting)
4. Remove outliers first
5. Check if there's real clustering structure (try HDBSCAN)

### Problem: "Results vary dramatically with small parameter changes"

**This suggests:**
- No strong clustering structure exists
- Consider not clustering at all
- Use stability analysis extensively
- Report sensitivity in results
- Try consensus clustering across multiple runs

### Problem: "Method A says k=3, Method B says k=7"

**Strategy:**
1. Check if k=7 is splitting k=3 clusters into subclusters
2. Test both with stability analysis
3. Look at dendrogram to see hierarchical relationships
4. Consider reporting both (coarse and fine-grained clustering)
5. Let biological interpretation guide final choice
