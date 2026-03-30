# Quality Control Guidelines for scRNA-seq

This document provides tissue-specific QC thresholds and guidelines for filtering single-cell RNA-seq data.

---

## General Principles

### Three Key QC Metrics

1. **Number of genes detected per cell** (`n_genes_by_counts`)
   - Low values: Low-quality cells, empty droplets
   - High values: Potential doublets

2. **Total UMI counts per cell** (`total_counts`)
   - Correlates with gene count
   - Helps identify empty droplets and doublets

3. **Percentage of mitochondrial genes** (`pct_counts_mt`)
   - High values: Dying/stressed cells
   - Tissue-specific expectations

---

## Tissue-Specific Thresholds

### Peripheral Blood Mononuclear Cells (PBMC)

**Typical characteristics:**
- Relatively homogeneous cell sizes
- Low mitochondrial content
- Well-defined cell types

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 2500
max_pct_mt = 5
```

**Rationale:**
- PBMCs are small cells with lower transcriptome complexity
- Healthy immune cells have low mitochondrial content
- Doublets often exceed 2500 genes

---

### Brain/Neural Tissue

**Typical characteristics:**
- High transcriptome complexity
- Neurons have many genes
- Variable mitochondrial content

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 6000  # Higher for neurons
max_pct_mt = 10
```

**Rationale:**
- Neurons are large, metabolically active cells
- High gene counts are expected and normal
- Some neuronal populations naturally have higher MT%

**Cell type considerations:**
- Neurons: 2000-6000 genes expected
- Glia: 1000-3000 genes expected
- Oligodendrocytes: May have higher MT%

---

### Tumor Tissue

**Typical characteristics:**
- Highly variable cell quality
- Often degraded/stressed cells
- Heterogeneous cell types

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 5000
max_pct_mt = 20  # More lenient
```

**Rationale:**
- Tumor dissociation is harsh, increases MT%
- Some real tumor cells have high MT%
- Being too strict loses valuable data
- Trade-off between quality and quantity

**Special considerations:**
- May need manual curation
- Check for MT-driven clusters after clustering
- Consider doublet detection tools

---

### Kidney

**Typical characteristics:**
- Mix of cell types with different sizes
- Proximal tubule cells are large
- Variable metabolic activity

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 4000
max_pct_mt = 15
```

**Rationale:**
- Proximal tubule cells have high gene counts
- Moderate mitochondrial tolerance
- Podocytes and endothelial cells are smaller

---

### Liver

**Typical characteristics:**
- Hepatocytes are large, metabolically active
- High mitochondrial content
- Variable transcriptome complexity

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 4000
max_pct_mt = 15
```

**Rationale:**
- Hepatocytes naturally have more mitochondria
- Moderate gene count expectations
- Non-parenchymal cells have lower counts

---

### Heart

**Typical characteristics:**
- Cardiomyocytes are large
- Very high mitochondrial content
- Mix with fibroblasts, endothelial cells

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 4000
max_pct_mt = 15-20  # Higher for cardiomyocytes
```

**Rationale:**
- Cardiomyocytes are packed with mitochondria
- High energy demands = high MT%
- May see bimodal MT% distribution

**Cell type considerations:**
- Cardiomyocytes: 10-20% MT typical
- Other cells: 5-10% MT typical
- Consider separate filtering per cell type

---

### Muscle

**Typical characteristics:**
- Large cells (myocytes)
- High mitochondrial content
- Mix of fiber types

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 4000
max_pct_mt = 15
```

**Rationale:**
- Skeletal muscle has high energy demands
- Myocytes naturally have more mitochondria
- Similar to heart tissue

---

### Lung

**Typical characteristics:**
- Many cell types of varying sizes
- Alveolar cells, immune cells, endothelial
- Variable transcriptome complexity

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 4000
max_pct_mt = 10
```

**Rationale:**
- Diverse cell type mixture
- Generally lower MT% expected
- Standard filtering works well

---

### Pancreas

**Typical characteristics:**
- Endocrine and exocrine cells
- Variable cell sizes
- Acinar cells have high complexity

**Recommended thresholds:**
```python
min_genes = 200
max_genes = 5000
max_pct_mt = 10
```

**Rationale:**
- Acinar cells are large with many genes
- Islet cells are smaller
- Moderate MT% tolerance

---

## Platform-Specific Considerations

### 10X Chromium (3' and 5')

**Characteristics:**
- ~1000-5000 genes per cell typical
- ~5000-30000 UMIs per cell
- v3 chemistry: Higher capture efficiency than v2

**Guidelines:**
- v2 chemistry: expect ~1000-2000 genes/cell
- v3 chemistry: expect ~1500-3000 genes/cell
- Very low counts (<200 genes) likely empty droplets

### Smart-seq2

**Characteristics:**
- Full-length transcript coverage
- Higher gene detection than droplet methods
- ~5000-10000 genes per cell typical

**Guidelines:**
- Use higher minimum gene threshold (500-1000)
- Less concerned about doublets (plate-based)
- Better gene coverage = higher counts expected

### Drop-seq

**Characteristics:**
- Similar to 10X but lower efficiency
- ~500-2000 genes per cell typical
- More empty droplets

**Guidelines:**
- More stringent empty droplet filtering
- Lower expected gene counts than 10X
- May need more cells sequenced

---

## Visualization-Based QC

### Before Setting Thresholds

**Always visualize QC metrics first:**

```python
# Violin plots
sc.pl.violin(adata, ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'])

# Scatter plots
sc.pl.scatter(adata, 'total_counts', 'n_genes_by_counts', color='pct_counts_mt')
sc.pl.scatter(adata, 'total_counts', 'pct_counts_mt')
```

**Look for:**
1. Clear outlier populations
2. Bimodal distributions (good vs bad cells)
3. Correlation between metrics
4. Unusual patterns suggesting technical issues

### Identifying Appropriate Thresholds

**For maximum genes:**
- Look for upper outliers in violin plot
- Expect doublets at 2-3× median gene count
- Sharp increase in counts suggests doublets

**For mitochondrial percentage:**
- Most cells should be in low-MT peak
- High-MT shoulder suggests dying cells
- Tissue-specific expectations apply

**For minimum genes:**
- Clear separation between real cells and empty droplets
- Usually around 200 genes
- Visualize as histogram to see distribution

---

## Advanced Filtering Strategies

### Adaptive Thresholds (MAD-based)

Instead of fixed thresholds, use median absolute deviations:

```python
# Calculate MAD-based thresholds
def is_outlier(adata, metric, nmads=3):
    metric_values = adata.obs[metric]
    median = metric_values.median()
    mad = np.median(np.abs(metric_values - median))
    threshold_low = median - nmads * mad
    threshold_high = median + nmads * mad
    return (metric_values < threshold_low) | (metric_values > threshold_high)

# Apply
adata.obs['outlier'] = (
    is_outlier(adata, 'n_genes_by_counts') |
    is_outlier(adata, 'total_counts') |
    is_outlier(adata, 'pct_counts_mt')
)
```

**Advantages:**
- Data-driven, adapts to dataset
- Less arbitrary than fixed thresholds
- Better for unusual datasets

### Cell Type-Specific Filtering

For tissues with diverse cell types:

1. Initial permissive filtering
2. Cluster cells
3. Identify major cell types
4. Apply cell type-specific thresholds

```python
# Example: Different thresholds for cardiomyocytes vs other cells
cardiomyocyte_mask = adata.obs['cell_type'] == 'Cardiomyocyte'
adata.obs.loc[cardiomyocyte_mask, 'pass_qc'] = (
    adata.obs.loc[cardiomyocyte_mask, 'pct_counts_mt'] < 20
)
adata.obs.loc[~cardiomyocyte_mask, 'pass_qc'] = (
    adata.obs.loc[~cardiomyocyte_mask, 'pct_counts_mt'] < 10
)
```

---

## Doublet Detection

### When to use doublet detection

- **Always recommended** for droplet-based methods
- Less important for plate-based (Smart-seq2)
- Critical for high cell density samples

### Tools

**Scrublet (Recommended):**
```python
import scrublet as scr
scrub = scr.Scrublet(adata.X, expected_doublet_rate=0.06)
doublet_scores, predicted_doublets = scrub.scrub_doublets()
adata.obs['doublet_score'] = doublet_scores
adata.obs['predicted_doublet'] = predicted_doublets
```

**DoubletFinder (via rpy2):**
- More sophisticated but requires R
- Better performance on some datasets

**Manual inspection:**
- Check for clusters with mixed markers
- Unusually high gene counts
- Biologically implausible populations

---

## Post-Filtering QC

### After filtering, always check:

1. **Retention rate:**
   ```python
   retention = 100 * adata_filtered.n_obs / adata.n_obs
   print(f"Retained {retention:.1f}% of cells")
   ```
   - Target: >70% retention
   - <50% suggests too aggressive filtering

2. **Cell type representation:**
   - Did you lose entire cell populations?
   - Are rare cell types depleted?

3. **Batch effects:**
   - Do filtered samples have similar QC distributions?
   - Are some samples disproportionately filtered?

---

## Troubleshooting

### Issue: Too few cells passing QC (<50%)

**Possible causes:**
1. Thresholds too stringent
2. Poor sample quality
3. Inappropriate tissue-specific thresholds

**Solutions:**
- Relax thresholds based on tissue type
- Check if sample degradation is real issue
- Consider if biological signal overlaps with "bad" cells

### Issue: Clusters driven by QC metrics

**Symptoms:**
- Clusters correlated with MT%
- Clusters correlated with total counts
- No clear biological markers

**Solutions:**
1. Tighten QC thresholds
2. Regress out QC metrics during scaling
3. Remove problem clusters if truly technical

### Issue: Unexpectedly high mitochondrial percentage

**Possible causes:**
1. Sample degradation
2. Tissue-specific biology
3. Harsh dissociation protocol

**Solutions:**
- Check if all samples affected or just some
- Research tissue-specific MT expectations
- Consider if biology (e.g., stress) is real
- May need more lenient filtering

---

## Quality Control Checklist

- [ ] Visualize QC distributions before filtering
- [ ] Use tissue-specific thresholds
- [ ] Check cell retention rate (>70%)
- [ ] Verify no entire cell types lost
- [ ] Run doublet detection for droplet data
- [ ] Check for batch-specific QC issues
- [ ] Verify clusters aren't driven by QC metrics
- [ ] Document filtering decisions and rationale

---

## References

1. Luecken MD, Theis FJ. Current best practices in single-cell RNA-seq analysis: a tutorial. *Mol Syst Biol*. 2019;15(6):e8746.

2. Osorio D, Cai JJ. Systematic determination of the mitochondrial proportion in human and mice tissues for single-cell RNA-sequencing data quality control. *Bioinformatics*. 2021;37(7):963-967.

3. Germain PL, et al. Doublet identification in single-cell sequencing data using scDblFinder. *F1000Research*. 2021;10:979.

---

**Last Updated:** January 2026
