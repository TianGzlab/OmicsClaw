# Quality Control Guidelines for scRNA-seq

Comprehensive guidelines for QC thresholds and filtering decisions across different tissue types and experimental contexts.

---

## General QC Metrics

### Core Metrics

1. **nFeature_RNA (nGene)**
   - Number of unique genes detected per cell
   - **Too low (<200)**: Empty droplets, poor quality
   - **Too high (>6,000)**: Potential doublets

2. **nCount_RNA (nUMI)**
   - Total UMI/read counts per cell
   - Correlates with nFeature_RNA
   - Higher depth = more genes detected

3. **percent.mt**
   - Percentage of reads from mitochondrial genes
   - **High values**: Dying/stressed cells (losing cytoplasmic RNA)
   - Critical QC metric for cell viability

4. **percent.ribo** (optional)
   - Percentage of reads from ribosomal genes
   - Can indicate translation activity
   - Less commonly used for filtering

5. **log10GenesPerUMI (complexity)**
   - Genes detected per UMI
   - Higher = more complex samples (good)
   - Low complexity may indicate poor quality

---

## Tissue-Specific Thresholds

### PBMC (Peripheral Blood Mononuclear Cells)

**Standard thresholds:**
- nFeature_RNA: 200 - 2,500
- percent.mt: < 5%

**Rationale:**
- Relatively uniform cell sizes
- Well-characterized QC profiles
- Low mitochondrial content in healthy immune cells

**Cell type notes:**
- Monocytes: ~1,000-1,500 genes
- T cells: ~800-1,200 genes
- B cells: ~1,000-1,500 genes
- NK cells: ~900-1,300 genes

**Red flags:**
- MT% > 10%: Sample degradation
- Mean genes < 800: Poor capture efficiency

---

### Brain Tissue

**Standard thresholds:**
- nFeature_RNA: 200 - 6,000
- percent.mt: < 10%

**Rationale:**
- Neurons express many genes (large transcriptomes)
- High metabolic activity = more mitochondrial content
- Diverse cell types with wide gene expression ranges

**Cell type notes:**
- Neurons: 2,000-5,000 genes (high complexity)
- Astrocytes: 1,500-3,000 genes
- Oligodendrocytes: 1,000-2,500 genes
- Microglia: 1,000-2,000 genes

**Red flags:**
- Neurons with <1,500 genes: Poor quality
- MT% > 15%: Tissue dissociation stress

**Special considerations:**
- Fresh vs. frozen tissue affects MT%
- Dissociation method impacts viability
- Nuclear RNA-seq (snRNA-seq) has lower counts

---

### Tumor Samples

**Standard thresholds:**
- nFeature_RNA: 200 - 5,000
- percent.mt: < 20% (more permissive)

**Rationale:**
- Hypoxic microenvironment = stressed cells
- Necrotic regions common
- Heterogeneous cell states

**Cell type notes:**
- Tumor cells: Highly variable (1,000-4,000 genes)
- Immune infiltrates: Similar to PBMC
- Stromal cells: 1,000-2,500 genes

**Red flags:**
- Very low gene counts: Extensive necrosis
- Bimodal MT% distribution: Viable vs. dying populations

**Special considerations:**
- May need separate QC for tumor vs. immune compartments
- Consider keeping higher MT% cells for certain analyses
- Watch for copy number artifacts in tumor cells

---

### Kidney

**Standard thresholds:**
- nFeature_RNA: 200 - 4,000
- percent.mt: < 15%

**Rationale:**
- Metabolically active tissue
- Diverse cell types with different gene expression
- Sensitive to ischemia during dissociation

**Cell type notes:**
- Proximal tubule: High MT% (metabolically active)
- Podocytes: 1,500-3,000 genes
- Immune cells: Similar to PBMC thresholds

**Red flags:**
- Proximal tubule cells with MT% > 20%: Stress/damage
- Low overall UMI counts: Poor tissue quality

---

### Liver

**Standard thresholds:**
- nFeature_RNA: 200 - 4,000
- percent.mt: < 15%

**Rationale:**
- Highly metabolic organ
- Hepatocytes have high mitochondrial content
- Mix of parenchymal and non-parenchymal cells

**Cell type notes:**
- Hepatocytes: 2,000-3,500 genes, higher MT%
- Kupffer cells: 1,500-2,500 genes
- Endothelial cells: 1,000-2,000 genes

---

### Heart/Muscle

**Standard thresholds:**
- nFeature_RNA: 200 - 4,000
- percent.mt: < 15-20%

**Rationale:**
- Cardiomyocytes/myocytes are mitochondria-rich
- High metabolic demand
- Difficult dissociation can stress cells

**Cell type notes:**
- Cardiomyocytes: High MT% (10-20%) is normal
- Fibroblasts: 1,000-2,500 genes
- Endothelial cells: 1,000-2,000 genes

**Special considerations:**
- Don't over-filter on MT% for cardiomyocytes
- Consider cell-type specific filtering

---

### Embryonic/Developmental

**Standard thresholds:**
- nFeature_RNA: 200 - 5,000
- percent.mt: < 10%

**Rationale:**
- Dividing cells (cell cycle effects)
- Developmental stage matters
- Smaller cells in early development

**Special considerations:**
- May need to regress out cell cycle scores
- Stage-specific thresholds
- Watch for maternal vs. embryonic transcripts

---

## Technology-Specific Considerations

### 10X Chromium (v2, v3, v3.1)

**Expected metrics:**
- **v2**: ~1,000-2,000 genes/cell, 2,000-5,000 UMIs/cell
- **v3**: ~1,500-3,000 genes/cell, 5,000-20,000 UMIs/cell
- **v3.1 (5')**: Similar to v3 but may have 3' bias

**Doublet rate:**
- ~1% per 1,000 cells loaded
- 10,000 cells loaded = ~10% doublets expected

### Drop-seq / inDrop

**Expected metrics:**
- Lower capture efficiency than 10X
- ~500-1,500 genes/cell typical
- Higher doublet rate

### Smart-seq2 (Full-length)

**Expected metrics:**
- Much higher gene detection: 3,000-6,000 genes/cell
- Higher total counts
- More even gene body coverage

**Special considerations:**
- Different normalization (not UMI-based)
- Higher complexity
- Lower throughput = fewer cells

---

## Doublet Detection

### Signs of Doublets

- Very high nFeature_RNA (>6,000 for droplet methods)
- Express markers from multiple cell types
- Intermediate expression profiles

### Recommended Tools

**DoubletFinder (R/Seurat):**
```r
library(DoubletFinder)

# Find optimal parameters
sweep_res <- paramSweep_v3(seurat_obj, PCs = 1:20)
sweep_stats <- summarizeSweep(sweep_res, GT = FALSE)
bcmvn <- find.pK(sweep_stats)

# Run DoubletFinder
seurat_obj <- doubletFinder_v3(
  seurat_obj,
  PCs = 1:20,
  pN = 0.25,
  pK = optimal_pK,  # From bcmvn
  nExp = expected_doublets  # e.g., 0.08 * ncol(seurat_obj)
)
```

**scDblFinder (Bioconductor):**
```r
library(scDblFinder)
library(SingleCellExperiment)

sce <- as.SingleCellExperiment(seurat_obj)
sce <- scDblFinder(sce)

# Add back to Seurat
seurat_obj$doublet_score <- sce$scDblFinder.score
seurat_obj$doublet_class <- sce$scDblFinder.class
```

---

## Adaptive/Data-Driven Thresholding

### MAD-Based Approach

Use Median Absolute Deviation (MAD) for automatic threshold detection:

```r
# For nFeature_RNA
median_features <- median(seurat_obj$nFeature_RNA)
mad_features <- mad(seurat_obj$nFeature_RNA)

lower_bound <- max(200, median_features - 3 * mad_features)
upper_bound <- median_features + 3 * mad_features

# For percent.mt
median_mt <- median(seurat_obj$percent.mt)
mad_mt <- mad(seurat_obj$percent.mt)

mt_threshold <- min(20, median_mt + 3 * mad_mt)

# Apply filters
seurat_filtered <- subset(
  seurat_obj,
  subset = nFeature_RNA > lower_bound &
           nFeature_RNA < upper_bound &
           percent.mt < mt_threshold
)
```

### Mixture Model Approach

Fit Gaussian mixture models to identify outlier populations:

```r
library(mclust)

# Fit mixture model to nFeature_RNA
fit <- Mclust(log10(seurat_obj$nFeature_RNA), G = 2:5)

# Identify low-quality cluster
# (implementation depends on specific case)
```

---

## QC Visualization Checklist

### Essential Plots

1. **Violin plots**: Distribution of each QC metric
2. **Scatter plots**: Relationships between metrics
   - nCount vs. nFeature (should be correlated)
   - nFeature vs. percent.mt (dying cells have low genes, high MT%)
3. **Histograms**: Identify outlier populations
4. **Before/after filtering**: Compare distributions

### Red Flags to Watch For

- **Bimodal distributions**: Two populations (good vs. bad quality)
- **No correlation between nCount and nFeature**: Technical issues
- **Very high MT% in majority of cells**: Sample degradation
- **Extreme outliers**: Check for technical artifacts

---

## Iterative QC Approach

### Recommended Workflow

1. **Initial liberal filtering**: Remove obvious outliers only
2. **Run analysis**: Clustering, marker identification
3. **Check results**: Are any clusters driven by QC metrics?
4. **Refine filtering**: Adjust thresholds if needed
5. **Re-run analysis**: Verify improvements

### When to Stop

- Clusters have clear biological identity
- QC metrics don't drive clustering
- Reasonable number of cells retained (>70% ideally)

---

## Sample-Specific Notes

### Fresh vs. Frozen Tissue

**Fresh:**
- Lower MT% expected
- Better RNA quality
- Faster processing critical

**Frozen:**
- Higher MT% acceptable (up to +5%)
- More batch variation
- May need less stringent thresholds

### Dissociation Method Impact

**Enzymatic:**
- Can stress cells (higher MT%)
- Consider tissue-specific enzymes
- Temperature and time critical

**Mechanical:**
- Less stress but lower yield
- Better for fragile cell types

**Nuclear RNA-seq:**
- Lower total counts
- Different QC metrics (nuclear genes)
- Less MT% (no cytoplasmic contamination)

---

## Final Recommendations

### General Strategy

1. **Start conservative**: Remove only clear outliers
2. **Be tissue-aware**: Use appropriate thresholds
3. **Visualize extensively**: Plot QC metrics in multiple ways
4. **Iterate**: QC is part of the analysis loop
5. **Document decisions**: Record thresholds and rationale

### Don't Forget

- QC is iterative, not one-time
- Context matters (tissue, technology, research question)
- Some biological signal may look like technical artifacts
- When in doubt, compare to published datasets from similar tissue

---

**Last Updated:** January 2026
**Reference datasets:** Based on HCA, PBMC, brain, tumor scRNA-seq studies
