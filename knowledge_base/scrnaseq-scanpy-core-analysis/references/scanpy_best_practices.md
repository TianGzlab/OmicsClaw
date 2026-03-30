# Scanpy Best Practices Guide

This guide provides recommendations for single-cell RNA-seq analysis using scanpy and the scverse ecosystem.

---

## Normalization Methods

### Standard Normalization (Recommended for most data)

**Method:** Target sum normalization + log transformation

```python
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
```

**When to use:**
- Standard scRNA-seq datasets
- 10X Chromium data
- Most droplet-based methods

**Advantages:**
- Fast and interpretable
- Well-established method
- Works well for most datasets

### Pearson Residuals

**Method:** Analytical Pearson residuals

```python
sc.experimental.pp.normalize_pearson_residuals(adata)
```

**When to use:**
- When you want to better handle heteroscedasticity
- Alternative to standard normalization
- Experimental workflows

**Advantages:**
- Better variance stabilization
- No need for log transformation
- Can improve downstream analysis

**Note:** This is still an experimental feature in scanpy.

---

## Highly Variable Genes Selection

### Seurat Method (Default)

```python
sc.pp.highly_variable_genes(
    adata,
    n_top_genes=2000,
    flavor='seurat',
    min_mean=0.0125,
    max_mean=3,
    min_disp=0.5
)
```

**Recommendations:**
- Use 2000-3000 genes for most datasets
- Adjust `min_mean` and `min_disp` if too few/many genes selected
- Visualize with `sc.pl.highly_variable_genes()` to check thresholds

### Seurat v3 Method

```python
sc.pp.highly_variable_genes(
    adata,
    n_top_genes=2000,
    flavor='seurat_v3',
    layer='counts'
)
```

**When to use:**
- When integrating datasets
- More robust to batch effects
- Requires raw counts in layer

---

## Dimensionality Reduction

### Number of PCs

**General recommendations:**
- Compute 50 PCs initially
- Use `suggest_n_pcs()` from `scale_and_pca.py` or the elbow plot to determine how many to keep
- **Standard range: 20-30 PCs. NEVER use <15 PCs.**
- For PBMC data: 20 PCs is standard, 30 PCs is conservative/safe
- Being conservative (using more PCs) rarely hurts; using too few causes underfitting

**Decision process:**
1. Plot variance explained: `sc.pl.pca_variance_ratio(adata)`
2. Call `suggest_n_pcs(adata)` for an automated recommendation
3. Look for elbow in scree plot
4. Check that cumulative variance is >80-90%
5. Use 30 PCs as safe default if unclear
6. **Do NOT use heuristics like "last PC where variance > X% of PC1"** — this often yields too few PCs

### Regression Variables

**Common variables to regress out:**
- `total_counts`: Library size effects
- `pct_counts_mt`: Mitochondrial content
- Batch/sample effects (if present)

```python
sc.pp.regress_out(adata, keys=['total_counts', 'pct_counts_mt'])
```

**Caution:**
- Only regress out technical variation
- Don't regress out biological signal
- Over-regression can remove real biology

---

## Clustering

### Leiden Algorithm (Recommended)

```python
sc.tl.leiden(adata, resolution=0.8)
```

**Advantages over Louvain:**
- Better guarantees of community quality
- More consistent results
- Slightly faster

### Resolution Parameter

**Guidelines:**
- Lower resolution (0.3-0.5): Fewer, broader clusters
- Medium resolution (0.6-0.8): Standard granularity
- Higher resolution (1.0-1.5): More fine-grained clusters

**Recommendation:** Test multiple resolutions

```python
for res in [0.4, 0.6, 0.8, 1.0]:
    sc.tl.leiden(adata, resolution=res, key_added=f'leiden_{res}')
```

### Neighbor Graph Parameters

```python
sc.pp.neighbors(adata, n_neighbors=10, n_pcs=30)
```

**Recommendations:**
- `n_neighbors=10`: Good default for most datasets
- Increase for larger datasets (15-20)
- Decrease for smaller datasets (5-8)
- Use same number as in UMAP for consistency

---

## UMAP Parameters

### Standard Settings

```python
sc.tl.umap(adata, min_dist=0.5, spread=1.0)
```

**Parameter effects:**
- `min_dist`: Controls tightness of clusters
  - Smaller (0.1-0.3): Tighter clusters
  - Larger (0.5-1.0): More spread out
- `spread`: Overall spread of points
  - Default 1.0 works well for most cases

**Recommendations:**
- Use default parameters initially
- Adjust `min_dist` if visualization isn't clear
- UMAP is stochastic - set random seed for reproducibility

---

## Marker Gene Identification

### Statistical Tests

**Wilcoxon (Default, Recommended):**
```python
sc.tl.rank_genes_groups(adata, groupby='leiden', method='wilcoxon')
```
- Fast and robust
- Non-parametric
- Good for most cases

**t-test:**
```python
sc.tl.rank_genes_groups(adata, groupby='leiden', method='t-test')
```
- Faster than Wilcoxon
- Assumes normality
- Use with oversampled option

**Logistic Regression:**
```python
sc.tl.rank_genes_groups(adata, groupby='leiden', method='logreg')
```
- Allows controlling for covariates
- Slower
- Good for complex experimental designs

### Filtering Markers

```python
sc.tl.filter_rank_genes_groups(
    adata,
    min_in_group_fraction=0.25,
    min_fold_change=1.0,
    max_out_group_fraction=0.5
)
```

**Recommendations:**
- `min_in_group_fraction=0.25`: Gene expressed in ≥25% of cluster
- `min_fold_change=1.0`: Natural log fold change ≥1 (e-fold ≈2.7)
- Adjust based on marker quality

---

## Data Management

### Sparse Matrices

- Keep data sparse whenever possible
- Most scanpy functions handle sparse matrices
- Convert to dense only when necessary:
  ```python
  if issparse(adata.X):
      adata.X = adata.X.toarray()
  ```

### Layers

**Recommended layer structure:**
- `adata.X`: Normalized, log-transformed data
- `adata.layers['counts']`: Raw counts
- `adata.layers['scaled']`: Scaled data (optional)

### Memory Management

**For large datasets:**
- Use backed mode:
  ```python
  adata = sc.read_h5ad('data.h5ad', backed='r+')
  ```
- Subset to HVGs before intensive operations
- Use `batch_size` parameter in functions when available

---

## Quality Control

### Cell Filtering Thresholds

**General guidelines:**
```python
# Minimum genes per cell
min_genes = 200  # Remove low-quality cells

# Maximum genes per cell (tissue-specific)
max_genes = 2500  # PBMC
max_genes = 6000  # Brain (neurons have many genes)

# Maximum mitochondrial percentage (tissue-specific)
max_pct_mt = 5   # PBMC
max_pct_mt = 10  # Brain
max_pct_mt = 20  # Tumor (higher tolerance)
```

**Doublet detection:**
```python
# Using scrublet
import scrublet as scr
scrub = scr.Scrublet(adata.X)
doublet_scores, predicted_doublets = scrub.scrub_doublets()
adata.obs['doublet_score'] = doublet_scores
adata.obs['predicted_doublet'] = predicted_doublets
```

### Gene Filtering

```python
# Remove genes expressed in few cells
sc.pp.filter_genes(adata, min_cells=3)

# Remove lowly expressed genes (optional)
sc.pp.filter_genes(adata, min_counts=10)
```

---

## Integration and Batch Correction

### When batch correction is needed

- Multiple samples from different batches
- Technical batch effects visible in PCA/UMAP
- Batch effects confound biological signal

### Recommended methods

**scVI (Deep learning-based):**
```python
import scvi
scvi.model.SCVI.setup_anndata(adata, batch_key='batch')
model = scvi.model.SCVI(adata)
model.train()
adata.obsm['X_scVI'] = model.get_latent_representation()
```

**Harmony:**
```python
import scanpy.external as sce
sce.pp.harmony_integrate(adata, key='batch')
```

**Combat:**
```python
sc.pp.combat(adata, key='batch')
```

---

## Visualization Best Practices

### Publication-Quality Plots

**Use seaborn + matplotlib for publication-quality plots:**
```python
import seaborn as sns
import matplotlib.pyplot as plt

sns.set_style("ticks")
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = ['Helvetica']

# Create UMAP dataframe
umap_df = pd.DataFrame(adata.obsm['X_umap'], columns=['UMAP1', 'UMAP2'])
umap_df['cell_type'] = adata.obs['cell_type'].values

# Plot
fig, ax = plt.subplots(figsize=(8, 6))
for ct in umap_df['cell_type'].unique():
    mask = umap_df['cell_type'] == ct
    ax.scatter(umap_df.loc[mask, 'UMAP1'], umap_df.loc[mask, 'UMAP2'],
               s=0.5, alpha=0.7, label=ct)
ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left', frameon=False, markerscale=5)
sns.despine(ax=ax)
```

**Use seaborn for heatmaps:**
```python
import seaborn as sns
heatmap = sns.clustermap(
    expr_data,
    cmap='RdBu_r',
    center=0,
    figsize=(10, 8)
)
```

### Figure Export

```python
# SVG for scalability
plt.savefig('figure.svg', dpi=300, bbox_inches='tight')

# PNG for presentations
plt.savefig('figure.png', dpi=300, bbox_inches='tight')
```

---

## Common Pitfalls

### 1. Not Storing Raw Counts
```python
# ALWAYS store raw counts before normalization
adata.layers['counts'] = adata.X.copy()
```

### 2. Over-filtering
- Don't be too aggressive with QC thresholds
- Check retention rate (>70% is good)
- Visualize QC distributions before filtering

### 3. Using Too Few PCs
- Using <15 PCs almost always loses biological variation
- **Do NOT use heuristics like "last PC where variance > X% of PC1"** — this often yields too few PCs
- Use `suggest_n_pcs()` from `scale_and_pca.py`, or default to 30 PCs
- For PBMC: 20 PCs is the community standard (Luecken & Theis 2019)

### 4. Not Testing Multiple Resolutions
- Optimal clustering resolution varies by dataset
- Always test multiple resolutions
- Biological interpretation should guide choice

### 5. Ignoring Batch Effects
- Always check for batch effects in PCA/UMAP
- Color by sample/batch to identify issues
- Use appropriate batch correction if needed

---

## Performance Tips

### Speed Optimization
- Use sparse matrices
- Subset to HVGs before scaling/PCA
- Use `n_jobs` parameter for parallelization:
  ```python
  sc.tl.rank_genes_groups(adata, groupby='leiden', n_jobs=4)
  ```

### Memory Optimization
- Use backed mode for large datasets
- Delete intermediate results:
  ```python
  del adata.uns['rank_genes_groups']
  ```
- Subset early and often

---

## Workflow Checklist

- [ ] Load data and create AnnData object
- [ ] Calculate and visualize QC metrics
- [ ] Filter low-quality cells
- [ ] Store raw counts in layer
- [ ] Normalize data
- [ ] Identify highly variable genes
- [ ] Scale data and regress out unwanted variation
- [ ] Run PCA and determine dimensionality
- [ ] Build neighbor graph
- [ ] Cluster cells (test multiple resolutions)
- [ ] Run UMAP
- [ ] Visualize and evaluate clustering
- [ ] Find marker genes
- [ ] Annotate cell types
- [ ] Export results

---

## Additional Resources

- **Official documentation:** https://scanpy.readthedocs.io/
- **Best practices book:** https://www.sc-best-practices.org/
- **Tutorials:** https://scanpy-tutorials.readthedocs.io/
- **scverse ecosystem:** https://scverse.org/
- **Scanpy GitHub:** https://github.com/scverse/scanpy

---

**Last Updated:** January 2026
