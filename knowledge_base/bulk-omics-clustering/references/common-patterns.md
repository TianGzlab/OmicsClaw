# Common Clustering Patterns

Detailed code examples and variations for common clustering workflows with complete implementation guidance.

---

## Pattern 1: Sample Subtype Discovery

**Use case:** Group patients/samples by gene expression profiles to discover disease subtypes or treatment response groups

**When to use:**
- You have bulk RNA-seq, proteomics, or metabolomics data
- Samples are patients, cell lines, or biological replicates
- Goal is to find molecular subtypes
- Most common clustering application in biology

### Complete Working Example

```python
import numpy as np
import pandas as pd
from scripts.prepare_data import load_and_prepare_data
from scripts.dimensionality_reduction import apply_pca, apply_umap
from scripts.hierarchical_clustering import hierarchical_clustering
from scripts.optimal_clusters import find_optimal_clusters
from scripts.cluster_validation import validate_clustering
from scripts.plot_clustering_results import plot_all_results
from scripts.characterize_clusters import characterize_clusters
from scripts.export_results import export_clustering_results

# 1. Load normalized expression data (samples × genes)
data, metadata, genes, samples = load_and_prepare_data(
    data_path="expression_tpm.csv",
    metadata_path="sample_metadata.csv",
    transpose=False,  # Samples in rows, genes in columns
    normalize_method="zscore",  # Z-score normalization
    filter_low_variance=True,
    variance_threshold=0.1,  # Remove bottom 10% variance genes
    handle_missing="drop"  # Remove samples/genes with missing values
)

print(f"Loaded {data.shape[0]} samples × {data.shape[1]} genes")

# 2. Reduce dimensions (1000s of genes → 50 PCs)
# Keeps major variation, reduces noise and computational cost
pca_data, pca_model, explained_variance = apply_pca(
    data,
    n_components=50,  # Or use variance_threshold=0.90
    plot_variance=True  # Creates scree plot
)

print(f"PCA: {explained_variance.sum():.1%} variance explained by {pca_data.shape[1]} PCs")

# 3. Explore clustering structure with dendrogram
# Don't specify n_clusters to see full tree
linkage_matrix, _ = hierarchical_clustering(
    pca_data,
    n_clusters=None,  # Build full tree
    linkage_method="ward",  # Ward minimizes variance
    plot_dendrogram=True,  # Visual exploration
    save_path="dendrogram_exploration"
)

# 4. Determine optimal k using multiple metrics
results = find_optimal_clusters(
    pca_data,
    method="hierarchical",  # Test hierarchical
    k_range=range(2, 11),  # Test k=2 to k=10
    metrics=["elbow", "silhouette", "gap", "calinski"],
    plot_results=True,
    output_path="optimal_k_analysis"
)

print(f"Suggested optimal k: {results['optimal_k']}")
print(f"Silhouette scores: {results['silhouette_scores']}")

# 5. Apply final clustering with chosen k
optimal_k = results['optimal_k']  # Or manually choose based on biology
cluster_labels, _ = hierarchical_clustering(
    pca_data,
    n_clusters=optimal_k,
    linkage_method="ward"
)

# 6. Validate clustering quality
validation = validate_clustering(
    pca_data,
    cluster_labels,
    metrics="all",
    true_labels=metadata.get('known_subtype') if 'known_subtype' in metadata else None,
    plot_silhouette=True,
    output_path="validation_plots"
)

print(f"Silhouette score: {validation['silhouette']:.3f}")
print(f"Davies-Bouldin index: {validation['davies_bouldin']:.3f}")
print(f"Calinski-Harabasz score: {validation['calinski_harabasz']:.1f}")

# 7. Test clustering stability
from scripts.stability_analysis import stability_analysis
stability = stability_analysis(
    pca_data,
    cluster_labels,
    clustering_method="hierarchical",
    n_bootstrap=100,
    sample_fraction=0.8,
    plot_consensus=True,
    output_path="stability_analysis"
)

print(f"Mean stability: {stability['mean_stability']:.3f}")

# 8. Characterize clusters (find distinguishing features)
cluster_features = characterize_clusters(
    data,  # Use original data, not PCA
    cluster_labels,
    genes,
    method="anova",  # ANOVA for multi-cluster comparison
    top_n=50,  # Top 50 genes per cluster
    fdr_threshold=0.05,
    plot_heatmap=True,
    output_path="cluster_features_heatmap"
)

# 9. Comprehensive visualization
umap_embedding = apply_umap(pca_data, n_neighbors=15, min_dist=0.1)

plot_all_results(
    data,
    cluster_labels,
    samples,
    genes,
    pca_data=pca_data,
    umap_embedding=umap_embedding,
    linkage_matrix=linkage_matrix,
    metadata=metadata,
    output_dir="clustering_visualizations/"
)

# 10. Export all results
export_clustering_results(
    cluster_labels,
    samples,
    validation,
    cluster_features,
    output_dir="clustering_results/",
    prefix="sample_subtyping"
)

print("✓ Sample subtype discovery complete!")
```

### Variations

**With batch effect correction:**
```python
# If samples cluster by batch instead of biology
from scripts.prepare_data import regress_out_batch

data_corrected = regress_out_batch(
    data,
    batch_labels=metadata['batch'],
    preserve_design=metadata['condition']  # Preserve biological signal
)

# Then proceed with clustering on data_corrected
```

**With bootstrap validation:**
```python
# For publication: test multiple k values with stability
k_candidates = [3, 4, 5]

for k in k_candidates:
    labels, _ = hierarchical_clustering(pca_data, n_clusters=k)
    stability = stability_analysis(pca_data, labels, n_bootstrap=100)
    validation = validate_clustering(pca_data, labels)

    print(f"k={k}: Silhouette={validation['silhouette']:.3f}, Stability={stability['mean_stability']:.3f}")

# Choose k with best silhouette + stability trade-off
```

**With feature filtering:**
```python
# Focus on most variable genes (faster, less noise)
from sklearn.feature_selection import VarianceThreshold

selector = VarianceThreshold(threshold=1.0)  # Keep genes with variance > 1
data_filtered = selector.fit_transform(data)

# Proceed with clustering
```

---

## Pattern 2: Gene Co-clustering

**Use case:** Group genes/proteins by similar expression patterns across samples to find co-regulated modules

**When to use:**
- You want to find co-expressed gene modules
- Goal is to understand gene relationships, not sample relationships
- Transpose your data: genes as rows, samples as columns
- Often followed by pathway enrichment analysis

### Complete Working Example

```python
import numpy as np
import pandas as pd
from scripts.prepare_data import load_and_prepare_data
from scripts.distance_metrics import calculate_distance_matrix
from scripts.hierarchical_clustering import hierarchical_clustering
from scripts.characterize_clusters import characterize_clusters
from scripts.plot_clustering_results import plot_cluster_heatmap

# 1. Load and transpose (genes × samples)
data, metadata, samples, genes = load_and_prepare_data(
    data_path="expression_tpm.csv",
    transpose=True,  # CRITICAL: genes as rows, samples as columns
    normalize_method="zscore",  # Normalize across samples for each gene
    filter_low_variance=True,
    variance_threshold=0.2  # Remove lowly expressed genes
)

print(f"Loaded {data.shape[0]} genes × {data.shape[1]} samples")

# 2. Use correlation distance (pattern similarity)
# Correlation focuses on pattern, not magnitude
distance_matrix = calculate_distance_matrix(
    data,
    metric="correlation",  # 1 - Pearson correlation
    show_distribution=True
)

# 3. Hierarchical clustering with average linkage
# Average linkage works well with correlation distance
linkage_matrix, cluster_labels = hierarchical_clustering(
    data,
    n_clusters=15,  # 10-20 modules is typical for gene clustering
    linkage_method="average",  # Average linkage for correlation
    metric="precomputed",  # Already computed distance matrix
    distance_matrix=distance_matrix,
    plot_dendrogram=True,
    save_path="gene_dendrogram"
)

# 4. Characterize gene clusters
# Find which conditions/samples show high/low expression for each module
cluster_features = characterize_clusters(
    data.T,  # Transpose back: samples × genes
    cluster_labels,
    genes,
    method="anova",
    plot_heatmap=True,
    output_path="gene_module_heatmap"
)

# 5. Export gene modules
gene_clusters_df = pd.DataFrame({
    'Gene': genes,
    'Module': cluster_labels
})

for module in np.unique(cluster_labels):
    module_genes = gene_clusters_df[gene_clusters_df['Module'] == module]['Gene'].tolist()
    print(f"\nModule {module}: {len(module_genes)} genes")

    # Save module genes for pathway enrichment
    with open(f"gene_modules/module_{module}_genes.txt", 'w') as f:
        f.write('\n'.join(module_genes))

# 6. Visualize module expression patterns
plot_cluster_heatmap(
    data.T,  # samples × genes
    cluster_labels,
    genes,
    samples,
    top_n_features=None,  # Show all genes (or top 100)
    output_path="gene_modules_heatmap"
)

print("✓ Gene co-clustering complete!")
```

### Variations

**Time-series gene clustering:**
```python
# For developmental or time-course data
# Order samples by time before clustering

time_ordered_samples = metadata.sort_values('timepoint').index
data_ordered = data[:, time_ordered_samples]

# Cluster genes, then plot modules showing temporal patterns
from scripts.plot_clustering_results import plot_temporal_patterns
plot_temporal_patterns(
    data_ordered,
    cluster_labels,
    timepoints=metadata.loc[time_ordered_samples, 'timepoint'],
    output_path="temporal_gene_modules"
)
```

**Condition-specific patterns:**
```python
# Find genes that cluster differently across conditions

conditions = metadata['condition'].unique()

for condition in conditions:
    condition_samples = metadata[metadata['condition'] == condition].index
    data_condition = data[:, condition_samples]

    # Cluster within condition
    linkage, labels = hierarchical_clustering(
        data_condition, n_clusters=10,
        linkage_method="average"
    )

    # Compare to overall clustering
```

**Multi-omics gene integration:**
```python
# Cluster genes using both transcriptomics and proteomics

# Concatenate standardized features
rna_data_zscore = (rna_data - rna_data.mean(axis=1, keepdims=True)) / rna_data.std(axis=1, keepdims=True)
protein_data_zscore = (protein_data - protein_data.mean(axis=1, keepdims=True)) / protein_data.std(axis=1, keepdims=True)

multi_omics_data = np.concatenate([rna_data_zscore, protein_data_zscore], axis=1)

# Cluster on integrated data
```

---

## Pattern 3: Method Comparison

**Use case:** Systematically compare multiple clustering algorithms to find most robust solution

**When to use:**
- Exploratory analysis where you don't know the best approach
- Publication-quality analysis requiring method justification
- Data with unclear structure
- Want to show results are robust across methods

### Complete Working Example

```python
import numpy as np
import pandas as pd
from scripts.prepare_data import load_and_prepare_data
from scripts.dimensionality_reduction import apply_pca
from scripts.hierarchical_clustering import hierarchical_clustering
from scripts.kmeans_clustering import kmeans_clustering
from scripts.density_clustering import hdbscan_clustering
from scripts.model_based_clustering import gmm_clustering
from scripts.cluster_validation import validate_clustering
from scripts.plot_clustering_results import plot_comparison

# 1. Prepare data
data, metadata, genes, samples = load_and_prepare_data(
    "expression_matrix.csv",
    normalize_method="zscore"
)

pca_data, _, _ = apply_pca(data, n_components=50)

# 2. Apply multiple methods with same k (where applicable)
k = 5  # Or test multiple k values

methods = {}

# Hierarchical
linkage, labels_hier = hierarchical_clustering(
    pca_data, n_clusters=k, linkage_method="ward"
)
methods['Hierarchical'] = labels_hier

# K-means
labels_kmeans, _, _ = kmeans_clustering(
    pca_data, n_clusters=k, method="kmeans", n_init=50
)
methods['K-means'] = labels_kmeans

# HDBSCAN (finds k automatically)
labels_hdbscan, _, n_clusters_hdbscan = hdbscan_clustering(
    pca_data, min_cluster_size=10, min_samples=5
)
methods['HDBSCAN'] = labels_hdbscan
print(f"HDBSCAN found {n_clusters_hdbscan} clusters")

# GMM
labels_gmm, _, _ = gmm_clustering(
    pca_data, n_components=k, covariance_type="full"
)
methods['GMM'] = labels_gmm

# 3. Validate each method
validation_results = {}

for name, labels in methods.items():
    validation = validate_clustering(
        pca_data, labels, metrics="all"
    )
    validation_results[name] = validation

    print(f"\n{name}:")
    print(f"  Silhouette: {validation['silhouette']:.3f}")
    print(f"  Davies-Bouldin: {validation['davies_bouldin']:.3f}")
    print(f"  Calinski-Harabasz: {validation['calinski_harabasz']:.1f}")

# 4. Create comparison table
comparison_df = pd.DataFrame({
    'Method': list(validation_results.keys()),
    'Silhouette': [v['silhouette'] for v in validation_results.values()],
    'Davies-Bouldin': [v['davies_bouldin'] for v in validation_results.values()],
    'Calinski-Harabasz': [v['calinski_harabasz'] for v in validation_results.values()],
    'N_clusters': [len(np.unique(labels[labels >= 0])) for labels in methods.values()]
})

comparison_df = comparison_df.sort_values('Silhouette', ascending=False)
print("\n=== Method Comparison ===")
print(comparison_df.to_string(index=False))

# Save comparison
comparison_df.to_csv("method_comparison.csv", index=False)

# 5. Test agreement between methods
from sklearn.metrics import adjusted_rand_score

print("\n=== Method Agreement (Adjusted Rand Index) ===")
method_names = list(methods.keys())

for i, name1 in enumerate(method_names):
    for name2 in method_names[i+1:]:
        ari = adjusted_rand_score(methods[name1], methods[name2])
        print(f"{name1} vs {name2}: ARI = {ari:.3f}")

# 6. Visual comparison
from scripts.plot_clustering_results import plot_pca_scatter

for name, labels in methods.items():
    plot_pca_scatter(
        pca_data, labels, samples,
        output_path=f"clustering_comparison/{name}_pca"
    )

# 7. Choose best method
best_method = comparison_df.iloc[0]['Method']
best_labels = methods[best_method]

print(f"\n✓ Best method: {best_method}")
print("✓ Method comparison complete!")
```

### Variations

**Systematic parameter sweep:**
```python
# Test multiple k values for each method

k_range = range(2, 11)
results = []

for k in k_range:
    # Hierarchical
    labels_h, _ = hierarchical_clustering(pca_data, n_clusters=k)
    val_h = validate_clustering(pca_data, labels_h)

    # K-means
    labels_k, _, _ = kmeans_clustering(pca_data, n_clusters=k)
    val_k = validate_clustering(pca_data, labels_k)

    # GMM
    labels_g, _, _ = gmm_clustering(pca_data, n_components=k)
    val_g = validate_clustering(pca_data, labels_g)

    results.append({
        'k': k,
        'Hierarchical_silhouette': val_h['silhouette'],
        'K-means_silhouette': val_k['silhouette'],
        'GMM_silhouette': val_g['silhouette']
    })

results_df = pd.DataFrame(results)
results_df.to_csv("parameter_sweep.csv", index=False)

# Plot silhouette vs k for each method
import matplotlib.pyplot as plt
plt.figure(figsize=(10, 6))
for method in ['Hierarchical', 'K-means', 'GMM']:
    plt.plot(results_df['k'], results_df[f'{method}_silhouette'], marker='o', label=method)
plt.xlabel('Number of clusters (k)')
plt.ylabel('Silhouette score')
plt.legend()
plt.title('Method comparison across k values')
plt.savefig("method_comparison_silhouette.png", dpi=300)
```

**Consensus clustering:**
```python
# Combine results from multiple methods

# Get cluster assignments from each method
all_labels = np.column_stack([
    methods['Hierarchical'],
    methods['K-means'],
    methods['GMM']
])

# Create consensus matrix (how often samples cluster together)
n_samples = len(all_labels)
consensus_matrix = np.zeros((n_samples, n_samples))

for labels in all_labels.T:
    for i in range(n_samples):
        for j in range(i+1, n_samples):
            if labels[i] == labels[j]:
                consensus_matrix[i, j] += 1
                consensus_matrix[j, i] += 1

consensus_matrix /= all_labels.shape[1]  # Normalize by number of methods

# Cluster on consensus matrix
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

consensus_dist = 1 - consensus_matrix
linkage_consensus = linkage(squareform(consensus_dist), method='average')
consensus_labels = fcluster(linkage_consensus, k, criterion='maxclust')

print("✓ Consensus clustering complete!")
```

---

## Pattern 4: QC and Outlier Detection

**Use case:** Identify batch effects, outlier samples, or data quality issues before main analysis

**When to use:**
- Before performing differential expression or other analyses
- When you suspect batch effects or technical artifacts
- To identify mislabeled or contaminated samples
- As part of quality control pipeline

### Complete Working Example

```python
import numpy as np
import pandas as pd
from scripts.prepare_data import load_and_prepare_data
from scripts.dimensionality_reduction import apply_pca, apply_umap
from scripts.density_clustering import hdbscan_clustering
from scripts.plot_clustering_results import plot_pca_scatter

# 1. Load data without aggressive filtering
data, metadata, genes, samples = load_and_prepare_data(
    "expression_matrix.csv",
    metadata_path="sample_metadata.csv",
    normalize_method="zscore",
    filter_low_variance=False,  # Keep all data for QC
    handle_missing="drop"
)

# 2. PCA for visualization
pca_data, pca_model, explained_var = apply_pca(
    data, n_components=10, plot_variance=True
)

# 3. Quick clustering without knowing k (HDBSCAN)
cluster_labels, probabilities, n_clusters = hdbscan_clustering(
    pca_data[:, :5],  # Use first 5 PCs
    min_cluster_size=5,  # Minimum 5 samples per cluster
    min_samples=3  # Core samples threshold
)

print(f"HDBSCAN detected {n_clusters} clusters")

# 4. Identify outliers (label = -1 in HDBSCAN)
outlier_mask = cluster_labels == -1
outlier_indices = np.where(outlier_mask)[0]
outlier_samples = [samples[i] for i in outlier_indices]

print(f"\nDetected {len(outlier_samples)} outlier samples:")
print(outlier_samples)

# 5. Check if outliers correspond to known issues
if 'batch' in metadata.columns:
    outlier_batches = metadata.iloc[outlier_indices]['batch'].value_counts()
    print("\nOutlier distribution by batch:")
    print(outlier_batches)

if 'qc_metrics' in metadata.columns:
    outlier_qc = metadata.iloc[outlier_indices]['qc_metrics'].describe()
    normal_qc = metadata.iloc[~outlier_mask]['qc_metrics'].describe()
    print("\nQC metrics comparison:")
    print(f"Outliers: {outlier_qc['mean']:.2f} ± {outlier_qc['std']:.2f}")
    print(f"Normal: {normal_qc['mean']:.2f} ± {normal_qc['std']:.2f}")

# 6. Visualize with PCA colored by cluster/batch
plot_pca_scatter(
    pca_data,
    cluster_labels,
    samples,
    output_path="qc_pca_clusters"
)

# Color by batch if available
if 'batch' in metadata.columns:
    batch_labels = pd.Categorical(metadata['batch']).codes
    plot_pca_scatter(
        pca_data,
        batch_labels,
        samples,
        output_path="qc_pca_batch"
    )

    # Check if clustering separates by batch (bad!)
    from sklearn.metrics import adjusted_rand_score
    ari_batch = adjusted_rand_score(cluster_labels[~outlier_mask],
                                     batch_labels[~outlier_mask])
    print(f"\nClustering vs Batch ARI: {ari_batch:.3f}")
    if ari_batch > 0.5:
        print("⚠️  WARNING: Samples cluster by batch! Consider batch correction.")

# 7. UMAP for detailed visualization
umap_embedding = apply_umap(pca_data, n_neighbors=15, min_dist=0.1)

from scripts.plot_clustering_results import plot_umap_scatter
plot_umap_scatter(
    umap_embedding,
    cluster_labels,
    samples,
    output_path="qc_umap_clusters"
)

# 8. Save outlier report
outlier_report = metadata.iloc[outlier_indices].copy()
outlier_report['hdbscan_probability'] = probabilities[outlier_indices]
outlier_report.to_csv("outlier_samples_report.csv")

# 9. Decision: remove outliers or investigate
print("\n=== Outlier Decision Guide ===")
print("If outliers are:")
print("  - Technical artifacts → Remove from downstream analysis")
print("  - Biological variation → Keep (may be interesting subtypes)")
print("  - Batch effects → Apply batch correction instead of removal")
print("  - Mislabeled → Investigate and correct metadata")

# 10. Re-cluster after removing outliers (if decided)
data_clean = data[~outlier_mask]
samples_clean = [s for i, s in enumerate(samples) if not outlier_mask[i]]

print(f"\n✓ QC complete! {len(samples_clean)} samples retained ({len(outlier_samples)} outliers)")
```

### Variations

**Multi-step outlier removal:**
```python
# Iteratively remove outliers until none remain

max_iterations = 5
current_data = data.copy()
current_samples = samples.copy()
all_outliers = []

for iteration in range(max_iterations):
    # Cluster
    pca_data, _, _ = apply_pca(current_data, n_components=10)
    labels, probs, _ = hdbscan_clustering(pca_data[:, :5], min_cluster_size=5)

    # Find outliers
    outlier_mask = labels == -1

    if not outlier_mask.any():
        print(f"No more outliers found after {iteration+1} iterations")
        break

    # Remove outliers
    outlier_samples = [current_samples[i] for i, is_outlier in enumerate(outlier_mask) if is_outlier]
    all_outliers.extend(outlier_samples)

    current_data = current_data[~outlier_mask]
    current_samples = [s for s, is_outlier in zip(current_samples, outlier_mask) if not is_outlier]

    print(f"Iteration {iteration+1}: Removed {outlier_mask.sum()} outliers")

print(f"Total outliers removed: {len(all_outliers)}")
```

**Batch-aware outlier detection:**
```python
# Detect outliers within each batch separately

all_outliers = []

for batch in metadata['batch'].unique():
    batch_mask = metadata['batch'] == batch
    batch_data = data[batch_mask]
    batch_samples = [samples[i] for i, is_batch in enumerate(batch_mask) if is_batch]

    # Cluster within batch
    pca_data, _, _ = apply_pca(batch_data, n_components=10)
    labels, _, _ = hdbscan_clustering(pca_data[:, :5])

    # Find batch-specific outliers
    outlier_mask = labels == -1
    batch_outliers = [batch_samples[i] for i, is_outlier in enumerate(outlier_mask) if is_outlier]

    all_outliers.extend(batch_outliers)
    print(f"Batch {batch}: {len(batch_outliers)} outliers")

print(f"Total outliers across all batches: {len(all_outliers)}")
```

---

## Pattern 5: Robust Clustering with Stability Testing

**Use case:** Ensure clustering results are reproducible and not artifacts of random initialization or sampling

**When to use:**
- Publication-quality analysis requiring robust results
- When k-means gives variable results across runs
- To justify cluster number choice
- When you need confidence in cluster assignments

### Complete Working Example

```python
import numpy as np
import pandas as pd
from scripts.prepare_data import load_and_prepare_data
from scripts.dimensionality_reduction import apply_pca
from scripts.kmeans_clustering import kmeans_clustering
from scripts.cluster_validation import validate_clustering
from scripts.stability_analysis import stability_analysis

# 1. Prepare data
data, metadata, genes, samples = load_and_prepare_data(
    "expression_matrix.csv",
    normalize_method="zscore"
)

pca_data, _, _ = apply_pca(data, n_components=50)

# 2. Test multiple k values with stability
k_range = [3, 4, 5, 6]
stability_results = []

for k in k_range:
    print(f"\n=== Testing k={k} ===")

    # Perform clustering with high n_init for reproducibility
    cluster_labels, centroids, inertia = kmeans_clustering(
        pca_data,
        n_clusters=k,
        method="kmeans",
        n_init=100,  # Run 100 times, take best
        random_state=42  # For reproducibility
    )

    # Compute validation metrics
    validation = validate_clustering(pca_data, cluster_labels, metrics="all")

    # Test stability via bootstrap
    stability = stability_analysis(
        pca_data,
        cluster_labels,
        clustering_method="kmeans",
        n_bootstrap=100,  # 100 bootstrap samples
        sample_fraction=0.8,  # 80% of samples per bootstrap
        plot_consensus=True,
        output_path=f"stability_k{k}"
    )

    # Store results
    stability_results.append({
        'k': k,
        'silhouette': validation['silhouette'],
        'davies_bouldin': validation['davies_bouldin'],
        'stability_mean': stability['mean_stability'],
        'stability_std': stability['std_stability'],
        'stable_samples_pct': stability['stable_samples_pct']
    })

    print(f"k={k}: Silhouette={validation['silhouette']:.3f}, Stability={stability['mean_stability']:.3f}")

# 3. Create comparison table
stability_df = pd.DataFrame(stability_results)
stability_df.to_csv("stability_comparison.csv", index=False)

print("\n=== Stability Comparison ===")
print(stability_df.to_string(index=False))

# 4. Choose k based on silhouette + stability trade-off
# Prioritize stability >0.85, then optimize silhouette

stable_options = stability_df[stability_df['stability_mean'] > 0.85]

if len(stable_options) > 0:
    best_k = stable_options.loc[stable_options['silhouette'].idxmax(), 'k']
    print(f"\n✓ Best k: {int(best_k)} (stable + highest silhouette)")
else:
    print("\n⚠️  No k value achieved stability >0.85")
    best_k = stability_df.loc[stability_df['stability_mean'].idxmax(), 'k']
    print(f"  Choosing k={int(best_k)} with highest stability ({stability_df['stability_mean'].max():.3f})")

# 5. Final clustering with chosen k
final_labels, _, _ = kmeans_clustering(
    pca_data,
    n_clusters=int(best_k),
    n_init=100,
    random_state=42
)

# 6. Test reproducibility across multiple runs
print("\n=== Testing Reproducibility ===")

from sklearn.metrics import adjusted_rand_score

run_labels = []
for run in range(10):
    labels, _, _ = kmeans_clustering(
        pca_data,
        n_clusters=int(best_k),
        n_init=50,
        random_state=run  # Different seed
    )
    run_labels.append(labels)

# Compute ARI between all pairs of runs
ari_scores = []
for i in range(len(run_labels)):
    for j in range(i+1, len(run_labels)):
        ari = adjusted_rand_score(run_labels[i], run_labels[j])
        ari_scores.append(ari)

mean_ari = np.mean(ari_scores)
print(f"Mean ARI across 10 runs: {mean_ari:.3f}")

if mean_ari > 0.95:
    print("✓ Clustering is highly reproducible")
elif mean_ari > 0.85:
    print("✓ Clustering is reasonably reproducible")
else:
    print("⚠️  Clustering has low reproducibility - consider hierarchical instead")

# 7. Identify unstable samples
final_stability = stability_analysis(
    pca_data, final_labels, clustering_method="kmeans", n_bootstrap=100
)

unstable_samples = [
    samples[i] for i, prob in enumerate(final_stability['sample_stability'])
    if prob < 0.7
]

print(f"\nIdentified {len(unstable_samples)} unstable samples (<70% stability)")
if len(unstable_samples) > 0:
    print("Unstable samples:", unstable_samples[:10], "..." if len(unstable_samples) > 10 else "")

# 8. Export results with stability scores
results_df = pd.DataFrame({
    'Sample': samples,
    'Cluster': final_labels,
    'Stability': final_stability['sample_stability']
})

results_df.to_csv("clustering_with_stability.csv", index=False)

print("\n✓ Robust clustering with stability testing complete!")
```

### Variations

**Consensus matrix visualization:**
```python
# Create and visualize consensus matrix from bootstrap

import matplotlib.pyplot as plt
import seaborn as sns

# Get consensus matrix from stability analysis
stability = stability_analysis(
    pca_data, cluster_labels, clustering_method="kmeans",
    n_bootstrap=100, return_consensus=True
)

consensus_matrix = stability['consensus_matrix']

# Plot consensus matrix (sorted by cluster)
sorted_idx = np.argsort(cluster_labels)

plt.figure(figsize=(10, 8))
sns.heatmap(
    consensus_matrix[sorted_idx][:, sorted_idx],
    cmap='RdBu_r',
    vmin=0, vmax=1,
    xticklabels=False,
    yticklabels=False,
    cbar_kws={'label': 'Co-clustering frequency'}
)
plt.title('Consensus Matrix (sorted by cluster)')
plt.savefig("consensus_matrix.png", dpi=300, bbox_inches='tight')

# Clear block structure = stable clustering
```

**Perturbation analysis:**
```python
# Test sensitivity to feature noise

noise_levels = [0.0, 0.05, 0.1, 0.15, 0.2]
perturbation_results = []

# Original clustering
labels_original, _, _ = kmeans_clustering(pca_data, n_clusters=5)

for noise_level in noise_levels:
    # Add Gaussian noise
    pca_noisy = pca_data + np.random.normal(0, noise_level, pca_data.shape)

    # Re-cluster
    labels_noisy, _, _ = kmeans_clustering(pca_noisy, n_clusters=5, n_init=50)

    # Compare to original
    ari = adjusted_rand_score(labels_original, labels_noisy)
    perturbation_results.append({'noise_level': noise_level, 'ARI': ari})

    print(f"Noise level {noise_level:.2f}: ARI = {ari:.3f}")

# Robust clustering should maintain high ARI even with noise
```

---

## Pattern 6: Hierarchical Exploration Then Efficient Partitioning

**Use case:** Use dendrogram to guide k selection, then apply scalable method for final clustering

**When to use:**
- Large datasets where hierarchical is too slow for final clustering
- Want dendrogram visualization benefits
- Need efficient final clustering (k-means)
- Best of both worlds approach

### Complete Working Example

```python
# 1. Subsample for hierarchical exploration
n_samples = len(data)
subsample_size = min(2000, n_samples)  # Max 2000 for hierarchical
subsample_indices = np.random.choice(n_samples, subsample_size, replace=False)

data_subsample = data[subsample_indices]
pca_subsample, _, _ = apply_pca(data_subsample, n_components=50)

# 2. Hierarchical on subsample to explore structure
from scripts.hierarchical_clustering import hierarchical_clustering

linkage_matrix, labels_subsample = hierarchical_clustering(
    pca_subsample,
    n_clusters=None,  # Full tree
    linkage_method="ward",
    plot_dendrogram=True,
    save_path="exploration_dendrogram"
)

# 3. Examine dendrogram, choose k
# Let's say dendrogram suggests k=5

# 4. Apply k-means on full dataset
pca_full, _, _ = apply_pca(data, n_components=50)

labels_full, centroids, _ = kmeans_clustering(
    pca_full,
    n_clusters=5,  # Based on dendrogram
    n_init=100
)

# 5. Validate on full data
validation = validate_clustering(pca_full, labels_full)
print(f"Full dataset clustering: Silhouette = {validation['silhouette']:.3f}")

# This approach combines hierarchical exploration with k-means efficiency
```

---

## Pattern 7: High-Dimensional Feature Clustering

**Use case:** Cluster 10,000+ features (genes, proteins, metabolites) efficiently

**When to use:**
- Clustering features, not samples
- Very high-dimensional data
- Need to reduce computation time
- Want to find feature modules

### Complete Working Example

```python
# 1. Start with feature matrix (features × samples)
# For 10,000+ features, direct clustering is slow

# 2. Pre-filter to most variable features
from sklearn.feature_selection import VarianceThreshold

selector = VarianceThreshold(threshold=1.0)  # Variance > 1 after z-scoring
data_filtered = selector.fit_transform(data)
genes_filtered = [genes[i] for i in selector.get_support(indices=True)]

print(f"Filtered to {len(genes_filtered)} high-variance features")

# 3. Use correlation distance + average linkage (efficient for features)
distance_matrix = calculate_distance_matrix(
    data_filtered,
    metric="correlation"
)

# 4. Hierarchical clustering
linkage_matrix, cluster_labels = hierarchical_clustering(
    data_filtered,
    n_clusters=20,  # 10-30 modules typical
    linkage_method="average",
    metric="precomputed",
    distance_matrix=distance_matrix
)

# 5. For even larger feature sets (>50k), use approximate methods
# Mini-batch K-means on feature space
from sklearn.cluster import MiniBatchKMeans

mbk = MiniBatchKMeans(n_clusters=20, batch_size=1000, n_init=10)
cluster_labels_approx = mbk.fit_predict(data.T)  # Transpose: features as rows

print("✓ High-dimensional feature clustering complete!")
```

---

## Troubleshooting Pattern Selection

**Problem → Recommended Pattern:**

- **"My clusters are unstable"** → Pattern 5 (Robust Clustering with Stability)
- **"I need to compare methods"** → Pattern 3 (Method Comparison)
- **"I have outliers/batch effects"** → Pattern 4 (QC and Outlier Detection)
- **"I want to find disease subtypes"** → Pattern 1 (Sample Subtype Discovery)
- **"I want co-expressed gene modules"** → Pattern 2 (Gene Co-clustering)
- **"I have >10k samples"** → Pattern 6 (Hierarchical exploration + k-means)
- **"I have >50k features"** → Pattern 7 (High-dimensional feature clustering)
- **"Results don't match biology"** → Start with Pattern 4 (QC), then Pattern 1
- **"I need publication-quality analysis"** → Pattern 5 (Stability) + Pattern 3 (Comparison)
- **"I don't know where to start"** → Pattern 1 (most common starting point)

---

## Combining Patterns

**Example: Comprehensive Publication-Ready Analysis**

```python
# 1. QC and outlier detection (Pattern 4)
data_clean, outliers = qc_and_outlier_detection(data)

# 2. Sample subtype discovery (Pattern 1)
cluster_labels = sample_subtype_discovery(data_clean)

# 3. Stability testing (Pattern 5)
stability = test_clustering_stability(data_clean, cluster_labels)

# 4. Method comparison (Pattern 3)
method_comparison = compare_clustering_methods(data_clean, cluster_labels)

# 5. Gene module discovery (Pattern 2)
gene_modules = gene_coclustering(data_clean, cluster_labels)

# This provides: clean data + robust clusters + method validation + gene signatures
```

---

## Summary

**Most Common Patterns:**
1. **Pattern 1** (Sample Subtype Discovery): ~60% of use cases
2. **Pattern 2** (Gene Co-clustering): ~20% of use cases
3. **Pattern 4** (QC/Outliers): ~15% of use cases (often before Pattern 1)

**For Robust Analysis:**
- Combine Pattern 1 + Pattern 5 (discovery + stability)
- Or Pattern 1 + Pattern 3 (discovery + method comparison)

**For Publications:**
- Pattern 4 → Pattern 1 → Pattern 5 → Pattern 3
- (QC → Discovery → Stability → Comparison)
