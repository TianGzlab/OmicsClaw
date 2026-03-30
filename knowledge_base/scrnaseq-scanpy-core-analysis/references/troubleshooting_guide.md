# Scanpy Troubleshooting Guide

Common issues and their solutions when analyzing single-cell RNA-seq data with scanpy.

---

## Data Loading Issues

### Issue: Import fails with "no module named scanpy"

**Solution:**
```bash
pip install scanpy numpy pandas matplotlib seaborn
```

### Issue: Can't read 10X data - directory structure error

**Symptoms:**
```
FileNotFoundError: barcodes.tsv.gz not found
```

**Solution:**
Check that your directory contains:
- `barcodes.tsv.gz` (or `.tsv`)
- `features.tsv.gz` (or `genes.tsv.gz` for older versions)
- `matrix.mtx.gz` (or `.mtx`)

```python
import os
print(os.listdir("path/to/filtered_feature_bc_matrix/"))
```

### Issue: Out of memory when loading large dataset

**Solution:**
Use backed mode:
```python
adata = sc.read_h5ad('large_data.h5ad', backed='r')
```

Or downsample during initial exploration:
```python
# Load only first N cells for testing
adata = sc.read_10x_mtx('path/', make_unique=True)
adata = adata[:10000, :].copy()  # First 10k cells
```

---

## Quality Control Issues

### Issue: Too many cells filtered out (>30%)

**Possible causes:**
1. Thresholds too stringent
2. Poor sample quality
3. Wrong tissue-specific thresholds

**Solutions:**

**Visualize before filtering:**
```python
sc.pl.violin(adata, ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'],
             jitter=0.4, multi_panel=True)
```

**Use adaptive thresholds:**
```python
# MAD-based filtering
median_genes = adata.obs['n_genes_by_counts'].median()
mad = np.median(np.abs(adata.obs['n_genes_by_counts'] - median_genes))
upper_limit = median_genes + 3 * mad
lower_limit = median_genes - 3 * mad
```

**Check tissue-specific guidelines:**
- See [qc_guidelines.md](qc_guidelines.md) for tissue-specific thresholds

### Issue: High mitochondrial percentage in all cells

**Possible causes:**
1. Sample degradation
2. Tissue-specific biology (e.g., cardiomyocytes)
3. Harsh dissociation protocol

**Solutions:**

**Check if biological:**
```python
# Plot distribution
import matplotlib.pyplot as plt
plt.hist(adata.obs['pct_counts_mt'], bins=100)
plt.xlabel('% Mitochondrial')
plt.show()
```

If bimodal distribution with lower peak <10% and upper peak >20%, likely mix of good and bad cells.

If unimodal distribution centered at 10-15%, may be tissue-specific:
- Heart tissue: 15-20% normal for cardiomyocytes
- Tumor tissue: Up to 20% tolerable
- Consider more lenient filtering

### Issue: No mitochondrial genes detected

**Symptoms:**
```
Mitochondrial genes identified: 0
```

**Possible causes:**
1. Wrong species pattern
2. Gene names in different format
3. Genes filtered out already

**Solutions:**

**Check gene name format:**
```python
# Human uses "MT-", mouse uses "mt-" or "Mt-"
print(adata.var_names[adata.var_names.str.contains('MT', case=False)][:10])
```

**Try different patterns:**
```python
# Try both patterns
mt_genes_human = adata.var_names.str.startswith('MT-')
mt_genes_mouse = adata.var_names.str.startswith('mt-')
print(f"Human pattern: {mt_genes_human.sum()} genes")
print(f"Mouse pattern: {mt_genes_mouse.sum()} genes")
```

---

## Normalization Issues

### Issue: "ValueError: inplace=True requires raw to be None"

**Cause:**
Trying to normalize when `adata.raw` already exists.

**Solution:**
```python
# Option 1: Don't use inplace
adata = sc.pp.normalize_total(adata, inplace=False)

# Option 2: Remove raw first
adata.raw = None
sc.pp.normalize_total(adata, inplace=True)
```

### Issue: Negative values after normalization

**Cause:**
Using regression before log transformation.

**Solution:**
Ensure correct order:
```python
# CORRECT order
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)
sc.pp.regress_out(adata, ['total_counts', 'pct_counts_mt'])
sc.pp.scale(adata)
```

### Issue: Memory error during scaling

**Cause:**
Scaling creates dense matrix, requires lots of memory.

**Solution:**

**Subset to HVGs first:**
```python
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
adata_hvg = adata[:, adata.var['highly_variable']].copy()
sc.pp.scale(adata_hvg)
```

**Use backed mode:**
```python
adata.write('temp.h5ad')
adata = sc.read_h5ad('temp.h5ad', backed='r+')
```

---

## PCA and Dimensionality Reduction Issues

### Issue: PCA variance explained is very low

**Symptoms:**
```
PC1-30 explain only 20% of variance
```

**Possible causes:**
1. Too many lowly expressed genes
2. Batch effects dominating
3. Not using highly variable genes

**Solutions:**

**Use HVGs:**
```python
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
sc.tl.pca(adata, use_highly_variable=True)
```

**Check for batch effects:**
```python
sc.pl.pca(adata, color='sample_id')  # Color by batch
```

**Increase number of HVGs:**
```python
sc.pp.highly_variable_genes(adata, n_top_genes=3000)
```

### Issue: UMAP all cells in one blob

**Possible causes:**
1. Not enough PCs used
2. Poor neighbor graph
3. Need more variable features

**Solutions:**

**Increase PCs:**
```python
sc.pp.neighbors(adata, n_pcs=50)  # Instead of 30
sc.tl.umap(adata)
```

**Adjust neighbor graph:**
```python
sc.pp.neighbors(adata, n_neighbors=15)  # Increase neighbors
```

**Check resolution:**
```python
sc.tl.leiden(adata, resolution=1.0)  # Increase resolution
```

### Issue: UMAP looks different every time

**Cause:**
UMAP is stochastic.

**Solution:**
Set random seed:
```python
sc.tl.umap(adata, random_state=42)
```

---

## Clustering Issues

### Issue: Too many small clusters

**Symptoms:**
- 50+ clusters with 5-10 cells each
- Hard to interpret biologically

**Solutions:**

**Lower resolution:**
```python
sc.tl.leiden(adata, resolution=0.4)  # Instead of 1.0
```

**Reduce number of neighbors:**
```python
sc.pp.neighbors(adata, n_neighbors=5)  # Instead of 10
sc.tl.leiden(adata, resolution=0.6)
```

### Issue: Clusters driven by QC metrics

**Symptoms:**
- Clusters correlate with `pct_counts_mt`
- Clusters correlate with `total_counts`
- No clear biological markers

**Solutions:**

**Tighten QC thresholds:**
```python
# More stringent MT filtering
adata = adata[adata.obs['pct_counts_mt'] < 5, :].copy()
```

**Regress out QC metrics:**
```python
sc.pp.regress_out(adata, ['total_counts', 'pct_counts_mt', 'n_genes_by_counts'])
sc.pp.scale(adata)
```

**Remove problem clusters:**
```python
# After identifying cluster "10" is driven by QC
adata = adata[adata.obs['leiden'] != '10', :].copy()
```

### Issue: Known cell types not separating

**Possible causes:**
1. Resolution too low
2. Not enough PCs
3. Batch effects

**Solutions:**

**Increase resolution:**
```python
for res in [0.6, 0.8, 1.0, 1.2]:
    sc.tl.leiden(adata, resolution=res, key_added=f'leiden_{res}')
```

**Use more PCs:**
```python
sc.pp.neighbors(adata, n_pcs=50)
sc.tl.leiden(adata, resolution=0.8)
```

**Check for batch effects:**
```python
sc.pl.umap(adata, color='sample_id')
# If batch-driven, use batch correction
```

---

## Marker Gene Identification Issues

### Issue: No significant markers found

**Possible causes:**
1. Clusters too similar
2. Thresholds too strict
3. Wrong statistical test

**Solutions:**

**Check cluster similarity:**
```python
# Plot dendrogram
sc.tl.dendrogram(adata, groupby='leiden')
sc.pl.dendrogram(adata, groupby='leiden')
```

**Relax thresholds:**
```python
sc.tl.rank_genes_groups(adata, groupby='leiden', method='wilcoxon')
sc.tl.filter_rank_genes_groups(
    adata,
    min_in_group_fraction=0.10,  # Lower from 0.25
    min_fold_change=0.5  # Lower from 1.0
)
```

**Try different test:**
```python
# Try t-test instead of wilcoxon
sc.tl.rank_genes_groups(adata, groupby='leiden', method='t-test_overestim_var')
```

### Issue: Top markers are ribosomal/mitochondrial genes

**Cause:**
These genes have high expression and variability.

**Solution:**

**Filter before marker identification:**
```python
# Remove MT and ribo genes
adata_filtered = adata[:, ~adata.var_names.str.startswith('MT-')].copy()
adata_filtered = adata_filtered[:, ~adata_filtered.var_names.str.match('^RP[SL]')].copy()

# Then find markers
sc.tl.rank_genes_groups(adata_filtered, groupby='leiden')
```

---

## Visualization Issues

### Issue: Seaborn/matplotlib plotting errors

**Error:**
```
ModuleNotFoundError: No module named 'seaborn'
```

**Solution:**
```bash
pip install seaborn matplotlib
```

If still issues, fall back to scanpy plotting:
```python
# Use scanpy plotting instead
sc.pl.umap(adata, color='leiden')
```

### Issue: Figures are blurry/low resolution

**Solution:**
```python
# Set DPI globally
import matplotlib.pyplot as plt
plt.rcParams['figure.dpi'] = 300

# Or for individual plots
plt.savefig('figure.svg', dpi=300, bbox_inches='tight')
```

### Issue: Can't see cluster labels on UMAP

**Solution:**
```python
sc.pl.umap(adata, color='leiden',
          legend_loc='on data',
          legend_fontsize='x-small',
          legend_fontoutline=2)
```

---

## Memory and Performance Issues

### Issue: "MemoryError" or kernel crash

**Solutions:**

**1. Use sparse matrices:**
```python
from scipy.sparse import issparse
print(f"Is sparse: {issparse(adata.X)}")

# Convert to sparse if needed
from scipy.sparse import csr_matrix
adata.X = csr_matrix(adata.X)
```

**2. Subset to HVGs:**
```python
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
adata = adata[:, adata.var['highly_variable']].copy()
```

**3. Use backed mode:**
```python
adata.write('temp.h5ad')
adata = sc.read_h5ad('temp.h5ad', backed='r+')
```

**4. Process in batches:**
```python
# For very large datasets
n_cells = adata.n_obs
batch_size = 10000
for i in range(0, n_cells, batch_size):
    adata_batch = adata[i:i+batch_size, :].copy()
    # Process batch
```

### Issue: Analysis is very slow

**Solutions:**

**Use multiprocessing:**
```python
sc.settings.n_jobs = 4  # Use 4 cores

# Or in specific functions
sc.tl.rank_genes_groups(adata, groupby='leiden', n_jobs=4)
```

**Optimize neighbor computation:**
```python
# Use approximate nearest neighbors (faster)
sc.pp.neighbors(adata, method='rapids')  # If RAPIDS available
```

---

## Integration and Batch Correction Issues

### Issue: Batch effects visible after "integration"

**Symptoms:**
- Clusters by sample/batch, not biology
- Can't find cross-batch markers

**Solutions:**

**Try different integration method:**

**scVI (Recommended):**
```python
import scvi
scvi.model.SCVI.setup_anndata(adata, batch_key='sample')
model = scvi.model.SCVI(adata)
model.train()
adata.obsm['X_scVI'] = model.get_latent_representation()

# Use scVI embedding for downstream analysis
sc.pp.neighbors(adata, use_rep='X_scVI')
sc.tl.umap(adata)
```

**Harmony:**
```python
import scanpy.external as sce
sce.pp.harmony_integrate(adata, key='sample')
```

### Issue: Lost biological variation after batch correction

**Cause:**
Over-correction removed real biology.

**Solution:**
- Use less aggressive correction
- Check if batch and biology are confounded
- May need to adjust parameters or use different method

---

## File Export Issues

### Issue: H5AD export hangs or is very slow

**Cause:**
Large AnnData objects (>10k cells, multiple layers) can take 10-60+ seconds to write, especially with gzip compression. The write appears to "hang" with no progress feedback.

**Solutions:**

**1. Use lzf compression (default in export_results.py):**
```python
# lzf is ~5-10x faster than gzip, ~10-20% larger files
save_h5ad(adata, "output.h5ad")  # default: compression='lzf'
```

**2. Skip compression for fastest writes:**
```python
save_h5ad(adata, "output.h5ad", compression=None)
```

**3. Compression comparison:**

| Method | Speed | File Size | Best For |
|--------|-------|-----------|----------|
| `lzf` | Fast (default) | Medium | Interactive/notebook use |
| `gzip` | Slow (5-10x slower) | Smallest | Archival, sharing |
| `None` | Fastest | Largest | Debugging, local work |

**Expected write times (approximate):**

| Dataset Size | lzf | gzip | None |
|-------------|-----|------|------|
| 3k cells | 2-5s | 10-30s | 1-2s |
| 10k cells | 5-15s | 30-90s | 3-8s |
| 50k cells | 15-45s | 2-5 min | 10-30s |
| 100k+ cells | 30-90s | 5-15 min | 20-60s |

**4. If export is interrupted:**
Re-run the export step only — no need to re-run the entire pipeline. The export function is idempotent.

**5. For very large datasets (>100k cells):**
Consider saving without the raw counts layer:
```python
# Remove counts layer before saving (if not needed downstream)
if 'counts' in adata.layers:
    del adata.layers['counts']
save_h5ad(adata, "output.h5ad")
```

### Issue: CSV files are too large

**Solution:**
Save as H5AD instead:
```python
adata.write('results.h5ad', compression='gzip')
```

Or export only normalized counts:
```python
# Export sparse matrix efficiently
import scipy.io
scipy.io.mmwrite('normalized_counts.mtx', adata.X)
```

### Issue: Can't open H5AD file in R

**Solution:**
Use Seurat conversion:
```r
library(Seurat)
library(SeuratDisk)

# Convert H5AD to H5Seurat
Convert("data.h5ad", dest = "h5seurat")
seurat_obj <- LoadH5Seurat("data.h5seurat")
```

---

## Environment and Installation Issues

### Issue: Conflicting package versions

**Solution:**
Create fresh conda environment:
```bash
conda create -n scanpy-env python=3.10
conda activate scanpy-env
pip install scanpy[leiden] python-igraph leidenalg
```

### Issue: Can't import umap

**Error:**
```
ImportError: cannot import name 'UMAP' from 'umap'
```

**Solution:**
```bash
pip uninstall umap umap-learn
pip install umap-learn
```

---

## Getting Help

If you still have issues:

1. **Check scanpy documentation:** https://scanpy.readthedocs.io/
2. **Search GitHub issues:** https://github.com/scverse/scanpy/issues
3. **Ask on Discourse:** https://discourse.scverse.org/
4. **Stack Overflow:** Tag with `scanpy` and `single-cell`

When asking for help, include:
- Scanpy version: `sc.__version__`
- Python version
- Full error traceback
- Minimal reproducible example

---

**Last Updated:** January 2026
