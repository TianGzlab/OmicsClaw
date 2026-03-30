# Spatial Transcriptomics Analysis Guide

Detailed parameter tuning and interpretation guide for 10x Visium spatial analysis using Squidpy and Scanpy.

---

## Spatial Neighbors Graph

The spatial neighbors graph defines which spots are considered "neighbors" in tissue space. This graph underpins all downstream spatial analyses (SVGs, neighborhood enrichment, co-occurrence).

### Coordinate Types

| `coord_type` | When to Use | Description |
|--------------|-------------|-------------|
| `'grid'` | **Visium** (hexagonal grid) | Uses array row/col indices. Default `n_neighs=6` for hexagonal layout. |
| `'generic'` | Slide-seq, MERFISH, custom | Uses spatial coordinates directly. Requires `n_neighs` or `radius`. |

**Visium default:** `sq.gr.spatial_neighbors(adata, coord_type='grid', n_neighs=6)` — each spot connects to its 6 hexagonal neighbors.

### Parameters

- **`n_neighs`** (default: 6 for grid): Number of neighbors per spot. For Visium, 6 matches the hexagonal geometry. Increase to 12-18 for second-ring neighbors.
- **`n_rings`** (default: 1): Number of hexagonal rings around each spot (Visium only). `n_rings=2` captures broader spatial context.
- **`radius`** (generic only): Fixed distance radius for neighborhood definition. Used when `coord_type='generic'`.

---

## Spatially Variable Genes (Moran's I)

### What Is Moran's I?

Moran's I measures spatial autocorrelation — whether a gene's expression is spatially clustered, dispersed, or random across the tissue.

| Moran's I Value | Interpretation |
|-----------------|----------------|
| Close to **+1** | **Clustered** — high values near high, low near low (strong spatial pattern) |
| Close to **0** | **Random** — no spatial structure |
| Close to **-1** | **Dispersed** — checkerboard pattern (high near low) |

### Statistical Significance

- **`n_perms`** (default: 100): Number of permutations for the null distribution. Higher = more accurate p-values but slower.
  - **Quick exploration:** `n_perms=100` (~1-2 min)
  - **Publication quality:** `n_perms=1000` (~10-15 min)
- **FDR correction:** Uses Benjamini-Hochberg (`pval_norm_fdr_bh`). Standard threshold: FDR < 0.05.
- **Alternative method:** Geary's C (`mode='geary'`) — similar but more sensitive to local differences. Use when Moran's I misses fine-grained patterns.

### Interpreting SVG Results

The output DataFrame (`adata.uns['moranI']`) contains:

| Column | Description |
|--------|-------------|
| `I` | Moran's I statistic (higher = more spatially structured) |
| `pval_norm` | P-value from normal approximation |
| `pval_norm_fdr_bh` | FDR-corrected p-value |
| `var_norm` | Variance under normality assumption |

**Top SVGs** typically include:
- Tissue-specific markers (e.g., cardiomyocyte genes in heart)
- Extracellular matrix genes at tissue boundaries
- Immune markers in infiltrated regions

---

## Neighborhood Enrichment

### What It Measures

Neighborhood enrichment quantifies whether two cluster types are **spatially co-localized** (positive z-score) or **spatially segregated** (negative z-score) beyond what's expected by chance.

### Interpreting Z-Scores

| Z-score | Interpretation |
|---------|----------------|
| **> 2** | Significantly co-localized (clusters tend to be adjacent) |
| **-2 to 2** | No significant spatial preference |
| **< -2** | Significantly segregated (clusters avoid each other) |

### Biological Examples (Cardiac Tissue)

- **Cardiomyocyte ↔ Fibroblast:** Positive enrichment at infarct border zone
- **Endothelial ↔ Cardiomyocyte:** Positive enrichment (vascular proximity)
- **Immune ↔ Remote myocardium:** Negative enrichment (immune infiltration localized to injury)

---

## Co-occurrence Analysis

### What It Measures

Co-occurrence computes the probability of observing two cluster types within increasing spatial distances. Unlike neighborhood enrichment (binary adjacent/not), co-occurrence captures **distance-dependent** spatial relationships.

### Interpreting Co-occurrence Curves

- **Probability > expected:** Clusters co-occur more than random at that distance
- **Probability < expected:** Clusters avoid each other at that distance
- **Distance-dependent patterns:** Clusters may co-occur at short range but segregate at long range (e.g., border zone cell types)

### Known Issues

- `n_splits` parameter can cause NaN values in some squidpy versions — use the default value
- Very small clusters (< 10 spots) produce noisy co-occurrence estimates

---

## Parameter Tuning Guide

### QC Filtering

| Parameter | Typical Range | Heart Tissue | Notes |
|-----------|--------------|--------------|-------|
| `min_genes` | 200-500 | 200 | Lower for sparse tissues |
| `min_cells` | 3-20 | 10 | Higher removes noise genes |
| `max_pct_mito` | 10-30% | 50% | Cardiac tissue has naturally high MT (~30-40%) |

**Cardiac-specific:** Heart tissue has naturally high mitochondrial content (~30-40% median) due to the energy demands of cardiomyocytes. The default `max_pct_mito=50%` retains >95% of spots. For non-cardiac tissues (brain, liver, immune), use 20% instead.

### Clustering

| Parameter | Range | Default | Effect |
|-----------|-------|---------|--------|
| `resolution` | 0.2-2.0 | 0.8 | Higher = more clusters |
| `n_neighbors` | 5-30 | 15 | Higher = smoother clusters |
| `n_pcs` | 10-50 | 30 | Higher captures more variance |

**Spatial data:** Lower resolution (0.5-0.8) often produces more biologically interpretable spatial domains than high resolution. Check that clusters correspond to visible tissue regions in the H&E image.

### HVG Selection

| Parameter | Range | Default | Notes |
|-----------|-------|---------|-------|
| `n_top_genes` | 1000-3000 | 2000 | Standard for Visium (~33K genes) |
| `flavor` | `seurat_v3` | `seurat_v3` | Works on raw counts; recommended for spatial data |

---

## Advanced Options

### Alternative Autocorrelation: Geary's C

```python
sq.gr.spatial_autocorr(adata, mode='geary', n_perms=100)
# Results in adata.uns['gearyC']
```

Geary's C is more sensitive to **local** spatial differences while Moran's I captures **global** spatial patterns. Consider running both for comprehensive SVG detection.

### Custom Spatial Graphs

For non-standard spatial layouts (e.g., multiple tissue sections merged):

```python
# Fixed radius neighbors
sq.gr.spatial_neighbors(adata, coord_type='generic', radius=150)

# KNN on coordinates
sq.gr.spatial_neighbors(adata, coord_type='generic', n_neighs=10)

# Delaunay triangulation
sq.gr.spatial_neighbors(adata, coord_type='generic', delaunay=True)
```

### Subsetting for Performance

For datasets with >10K spots, consider analyzing regions of interest:

```python
# Subset to a spatial region
mask = (adata.obsm['spatial'][:, 0] > x_min) & (adata.obsm['spatial'][:, 0] < x_max)
adata_subset = adata[mask].copy()
```

---

## Downstream Analysis Suggestions

1. **Cell type deconvolution:** Use SVG results + scRNA-seq reference to estimate cell type proportions per spot (cell2location, RCTD, STdeconvolve)
2. **Receptor-ligand analysis:** Identify spatially co-localized ligand-receptor pairs using CellChat or COMMOT
3. **Spatial gene-gene correlation:** Compute spatially-weighted correlation between SVGs to identify co-regulated programs
4. **Multi-sample comparison:** Integrate multiple Visium sections (e.g., MI vs control) using batch correction + differential spatial analysis


---
