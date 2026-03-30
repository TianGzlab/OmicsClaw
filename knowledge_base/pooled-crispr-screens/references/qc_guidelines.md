# Quality Control Guidelines

Detailed QC thresholds and filtering criteria for pooled CRISPR screens with single-cell RNA-seq readout.

---

## Cell-Type Specific QC Thresholds

### Primary Neurons

**Characteristics:**
- High gene complexity (large cells, complex transcriptome)
- Lower mitochondrial tolerance (metabolically active)
- Sensitive to culture stress

**Recommended thresholds:**
```python
min_genes = 2500-3500
min_counts = 8000-12000
max_mito_pct = 0.10-0.15
```

**Rationale:**
- Neurons express 8,000-12,000 genes typically
- Mitochondrial % >15% indicates apoptosis/stress
- High complexity filters out debris and doublets

### iPSC-Derived Neurons

**Characteristics:**
- Variable differentiation states
- Intermediate gene complexity
- More tolerant of culture conditions

**Recommended thresholds:**
```python
min_genes = 2000-2500
min_counts = 5000-8000
max_mito_pct = 0.15-0.20
```

**Rationale:**
- Differentiation heterogeneity requires broader thresholds
- Less strict mito% due to metabolic variability
- Still filter low-quality cells effectively

### Immune Cells (Macrophages, T cells, B cells)

**Characteristics:**
- Smaller cells with lower complexity
- Dynamic metabolic states (especially macrophages)
- Higher mito% in activated states

**Recommended thresholds:**
```python
min_genes = 1000-1500
min_counts = 3000-5000
max_mito_pct = 0.15-0.25
```

**Rationale:**
- Immune cells are smaller, express fewer genes
- Activated macrophages have higher mito% (oxidative metabolism)
- Balance keeping activated cells while removing dying cells

### Cancer Cell Lines (HEK293T, K562, HeLa, etc.)

**Characteristics:**
- Highly variable metabolic states
- Fast-growing, stress-tolerant
- Variable gene expression profiles

**Recommended thresholds:**
```python
min_genes = 1500-2500
min_counts = 5000-8000
max_mito_pct = 0.15-0.25
```

**Rationale:**
- Cancer cells tolerate higher stress (higher mito% OK)
- Variable complexity depending on cell line
- Err on side of inclusion to avoid losing perturbation phenotypes

---

## sgRNA Mapping QC

### Mapping Rate Assessment

**Expected mapping rates by technology:**

| Technology | Expected Mapping Rate | Good | Acceptable | Poor |
|------------|----------------------|------|------------|------|
| 10X Feature Barcoding | 50-70% | >60% | 40-60% | <40% |
| Direct capture (Replogle 2020) | 60-80% | >70% | 50-70% | <50% |
| Separate sgRNA-seq | 70-90% | >80% | 60-80% | <60% |

**Troubleshooting low mapping rates (<40%):**
1. **Check sgRNA amplification**: Run Bioanalyzer/TapeStation on sgRNA library
2. **Verify sgRNA reference**: Ensure mapping file matches library
3. **Check for barcode quality**: High N content or low quality scores
4. **MOI too low**: Insufficient viral transduction

### Singlet Assignment Criteria

**Strict singlet calling** (recommended):
```python
# Cell is singlet if >70% of sgRNA UMI from single sgRNA
singlet_threshold = 0.70

# Example calculation:
# Cell A: sgRNA1 = 8 UMI, sgRNA2 = 2 UMI
# Fraction = 8/10 = 0.80 → Singlet (sgRNA1)

# Cell B: sgRNA1 = 5 UMI, sgRNA2 = 4 UMI
# Fraction = 5/9 = 0.56 → Doublet (remove)
```

**Relaxed singlet calling** (for low capture efficiency):
```python
# Cell is singlet if >60% of sgRNA UMI from single sgRNA
singlet_threshold = 0.60

# Use only if mapping rate <40% and data is limited
```

**Minimum UMI per sgRNA:**
```python
min_umi_per_sgrna = 2  # Reduces ambient RNA noise
```

### Expected Doublet Rates

| MOI | Theoretical Doublet Rate | Typical Observed Rate | Acceptable Threshold |
|-----|-------------------------|----------------------|---------------------|
| 0.3 | 4% | 5-8% | <10% |
| 0.5 | 7% | 8-12% | <15% |
| 0.8 | 13% | 15-20% | <20% |

**High doublet rate troubleshooting (>15%):**
- MOI too high (re-titrate virus)
- Ambient sgRNA RNA (improve dead cell removal)
- Barcode collision (check sgRNA library diversity)

---

## Standard scRNA-seq QC Metrics

### Gene Detection (n_genes)

**Interpretation:**
- **Too low (<1000)**: Empty droplets, debris, lysed cells
- **Expected (1000-5000)**: Healthy cells, varies by cell type
- **Too high (>8000)**: Potential doublets (two cells in one droplet)

**Cell-type specific:**
```python
# Neurons
min_genes = 2500
max_genes = 8000

# Immune cells
min_genes = 1000
max_genes = 5000

# Cancer cell lines
min_genes = 1500
max_genes = 6000
```

### UMI Counts (n_counts)

**Interpretation:**
- **Too low (<2000)**: Low-quality cells, poor capture
- **Expected (3000-30000)**: Varies by cell type and 10X chemistry
- **Too high (>50000)**: Potential doublets

**Sequencing depth relationship:**
| Sequencing Depth | Expected UMI per Cell | Saturation |
|-----------------|---------------------|------------|
| 20,000 reads/cell | 3,000-5,000 UMI | 60-70% |
| 50,000 reads/cell | 8,000-15,000 UMI | 70-80% |
| 100,000 reads/cell | 15,000-30,000 UMI | 80-90% |

### Mitochondrial Percentage (percent_mito)

**Interpretation:**
- **Healthy cells (<10%)**: Intact, viable cells
- **Moderate stress (10-20%)**: Some apoptosis, still usable
- **High stress (>20%)**: Dying cells, compromised transcriptome

**Cell-type specific:**
```python
# Primary neurons (sensitive)
max_mito = 0.10-0.15

# iPSC-derived cells (moderate)
max_mito = 0.15-0.20

# Immune cells, cancer lines (tolerant)
max_mito = 0.20-0.25
```

**Special considerations:**
- Macrophages: Higher mito% in activated state (M1 polarization)
- Cardiomyocytes: Naturally high mito% (>20% can be normal)
- Brown adipocytes: High mito% due to thermogenesis

### Ribosomal Percentage (optional)

**When to use:**
- Helps distinguish dying cells from metabolically active cells
- High ribo% + high mito% → dying cell
- High ribo% + low mito% → active translation (healthy)

**Thresholds:**
```python
# Calculate ribosomal percentage
ribo_genes = adata.var_names.str.startswith(('RPS', 'RPL'))
adata.obs['percent_ribo'] = np.sum(adata[:, ribo_genes].X, axis=1).A1 / adata.obs['n_counts']

# Flag suspicious cells
suspicious = (adata.obs['percent_mito'] > 0.20) & (adata.obs['percent_ribo'] > 0.30)
```

---

## CRISPR-Specific QC Metrics

### Cells per Perturbation

**Minimum viable cells:**
```python
min_cells_for_analysis = 20  # Minimum for statistical tests
ideal_cells_per_perturbation = 50-100  # Good power for DE and outlier detection
```

**Interpretation:**
| Cells per Perturbation | Analysis Capability | Recommended Action |
|------------------------|-------------------|-------------------|
| <10 | Insufficient | Exclude from analysis |
| 10-20 | Low power | Flag as low confidence |
| 20-50 | Moderate power | Include with caution |
| 50-100 | Good power | Standard analysis |
| >100 | High power | Ideal for all analyses |

**Troubleshooting low cell counts (<20):**
1. **Strong lethal phenotype**: Perturbation causes cell death (expected for essential genes)
2. **Poor sgRNA representation**: Check library prep, sequencing depth
3. **Batch effect**: Check if perturbation present in all replicates
4. **sgRNA inactive**: Target gene not expressed or sgRNA ineffective

### sgRNA Representation

**Check library complexity:**
```python
# Calculate cells per sgRNA
cells_per_sgrna = adata.obs.groupby('sgRNA').size()

print(f"Mean cells per sgRNA: {cells_per_sgrna.mean():.1f}")
print(f"Median cells per sgRNA: {cells_per_sgrna.median():.1f}")
print(f"sgRNAs with <10 cells: {(cells_per_sgrna < 10).sum()}")
print(f"sgRNAs with 0 cells: {(cells_per_sgrna == 0).sum()}")
```

**Expected distribution:**
- Mean/Median ratio ~1.0-1.5 (balanced representation)
- <10% sgRNAs with <10 cells (good coverage)
- <5% sgRNAs with 0 cells (excellent coverage)

**Troubleshooting skewed representation:**
- Check for growth selection (fast-growing clones dominate)
- Verify library prep (some sgRNAs amplify preferentially)
- Check for bottlenecks during cell culture

### Control Cell Distribution

**Non-targeting control QC:**
```python
# Check control cell counts
n_controls = (adata.obs['gene'] == 'non-targeting').sum()
n_total = adata.n_obs
control_fraction = n_controls / n_total

print(f"Control cells: {n_controls} ({control_fraction:.1%})")

# Expected: 5-15% of total cells (depends on library design)
```

**Ideal control fraction:**
- 5-10% for genome-wide screens (100+ non-targeting sgRNAs in library of 50K-100K sgRNAs)
- 10-20% for targeted screens (proportionally more controls in smaller libraries)

**Troubleshooting control depletion:**
- Selection bias (if controls are under-represented)
- Check library representation at DNA level (sequencing of plasmid pool)
- Verify viral production (some sgRNAs may have lower titer)

---

## Target Gene Validation

### Overview

Target gene validation is a **critical QC step** that verifies perturbations actually affected their intended targets. This filters out ineffective sgRNAs and ensures high-quality hits for downstream analysis.

**Run validation after initial DE screening (Step 9 in workflow)**

### CRISPRi Expected Effects

**Target gene should be downregulated (negative log2FC)**

| Effect Strength | log2FC Range | Fold Change | Interpretation |
|----------------|--------------|-------------|----------------|
| Strong knockdown | < -1.0 | >50% reduction | Excellent sgRNA activity |
| Moderate knockdown | -1.0 to -0.5 | 30-50% reduction | Good sgRNA activity |
| Weak knockdown | -0.5 to 0 | <30% reduction | Poor sgRNA activity, may not be functional |
| No effect / Wrong direction | ≥ 0 | No change or increase | Inactive sgRNA, remove from analysis |

**Validation thresholds:**
```python
min_log2fc = -0.5  # Minimum 30% reduction required
max_pval = 0.05    # Target effect must be significant
```

**Example validation:**
```python
from scripts.validate_perturbations import validate_target_effect

validation = validate_target_effect(
    de_results,
    expected_direction='down',
    min_log2fc=-0.5,
    max_pval=0.05
)

# Check validation rate
validation_rate = (validation['target_affected']).mean()
print(f"Validation rate: {validation_rate:.1%}")
```

### CRISPRa Expected Effects

**Target gene should be upregulated (positive log2FC)**

| Effect Strength | log2FC Range | Fold Change | Interpretation |
|----------------|--------------|-------------|----------------|
| Strong activation | > 2.0 | >4x increase | Excellent sgRNA activity |
| Moderate activation | 1.0 to 2.0 | 2-4x increase | Good sgRNA activity |
| Weak activation | 0.5 to 1.0 | 1.4-2x increase | Moderate activity, may be sufficient |
| No effect / Wrong direction | ≤ 0 | No change or decrease | Inactive sgRNA, remove from analysis |

**Validation thresholds:**
```python
min_log2fc = 0.5   # Minimum 1.4x increase required
max_pval = 0.05    # Target effect must be significant
```

### Validation Rate Expectations

| Validation Rate | Library Quality | Action |
|----------------|----------------|--------|
| 60-80% | ✓ Good | Proceed with analysis |
| 50-60% | ⚠ Acceptable | Proceed but check negative hits |
| <50% | ✗ Poor | Troubleshoot before continuing |

**Interpretation:**
- **Good library (60-80%)**: Most sgRNAs are functional, high-confidence hits
- **Acceptable (50-60%)**: Moderate sgRNA activity, filter to validated only
- **Poor (<50%)**: Systematic issues with perturbation efficiency

### Troubleshooting Low Validation Rates

**If validation rate <50%, check:**

1. **sgRNA Design Quality**
   - On-target score (use tools like CRISPOR, Azimuth)
   - Off-target potential (high off-target = poor specificity)
   - GC content (40-60% optimal)
   - Secondary structure (avoid strong hairpins)

2. **Perturbation System**
   - **CRISPRi**: Check dCas9-KRAB expression level
   - **CRISPRa**: Check dCas9-VP64 fusion expression
   - **CRISPRko**: Check Cas9 cutting efficiency
   - Verify perturbation system is working with positive controls

3. **Viral Transduction**
   - MOI too low (insufficient perturbation)
   - MOI too high (toxicity, multiple sgRNAs per cell)
   - Uneven transduction across cell types
   - Verify transduction efficiency with fluorescent reporter

4. **Selection Stringency**
   - Insufficient selection (non-transduced cells remain)
   - Over-selection (loss of perturbations with growth effects)
   - Balance: select enough to enrich transduced cells

5. **Gene Expression Levels**
   - Target gene not expressed in cell type (cannot detect knockdown)
   - Target gene too lowly expressed (below detection limit)
   - Filter to genes with mean expression >1 UMI/cell

### Quick Validation Check

```python
# Quick check: median target log2FC across all perturbations
target_log2fc = []
for gene, de_df in de_results.items():
    if gene in de_df['gene'].values:
        target_row = de_df[de_df['gene'] == gene].iloc[0]
        target_log2fc.append(target_row['log2fc'])

import numpy as np
median_target_fc = np.median(target_log2fc)
print(f"Median target gene log2FC: {median_target_fc:.2f}")

# CRISPRi: should be ~ -0.8 to -1.5
# CRISPRa: should be ~ +1.0 to +2.0
```

### Per-Perturbation Validation Examples

**Valid CRISPRi example:**
```
Perturbation: TREM2
Target gene: TREM2
log2FC: -1.24 (58% reduction)
p-value: 2.3e-15
Status: ✓ Valid
```

**Invalid CRISPRi example (insufficient effect):**
```
Perturbation: SOX5
Target gene: SOX5
log2FC: -0.23 (15% reduction)
p-value: 0.08
Status: ✗ Invalid (insufficient_effect)
```

**Invalid CRISPRi example (wrong direction):**
```
Perturbation: APOE
Target gene: APOE
log2FC: +0.45 (37% increase!)
p-value: 0.003
Status: ✗ Invalid (wrong_direction)
```

### Integration with Hit Calling

**Always filter to validated perturbations before final hit calling:**

```python
# Step 1: Run initial DE screening
de_results = screen_all_perturbations(adata)

# Step 2: Validate target effects
validation = validate_target_effect(de_results, expected_direction='down')

# Step 3: Filter to validated only
validated_genes = validation[validation['target_affected']]['perturbation'].tolist()
de_results_validated = {g: de_results[g] for g in validated_genes}

# Step 4: Call hits from validated perturbations only
hits = call_hits(de_results_validated, min_de_genes=10)
```

---

## Batch Effect QC

### PCA-Based Assessment

**Check for batch effects:**
```python
# Compute PCA
sc.tl.pca(adata, n_comps=50)

# Plot PCA colored by batch
sc.pl.pca(adata, color=['batch', 'gene'], dimensions=[(0,1), (1,2), (2,3)])

# Calculate variance explained by batch
from sklearn.decomposition import PCA
import pandas as pd

# Regress batch on PCs
import statsmodels.api as sm

r2_scores = []
for pc in range(10):
    X = pd.get_dummies(adata.obs['batch'])
    y = adata.obsm['X_pca'][:, pc]
    model = sm.OLS(y, X).fit()
    r2_scores.append(model.rsquared)

print(f"Variance explained by batch (PC1-10): {sum(r2_scores[:10])/10:.1%}")
```

**Interpretation:**
- <5% variance explained by batch: No correction needed
- 5-15% variance: Consider correction, check if biological signal preserved
- >15% variance: Correction recommended

### Per-Perturbation Batch Balance

**Check if perturbations are balanced across batches:**
```python
import pandas as pd

# Cross-tabulation
crosstab = pd.crosstab(adata.obs['gene'], adata.obs['batch'])

# Calculate coefficient of variation (CV) per gene
cv = crosstab.std(axis=1) / crosstab.mean(axis=1)

# Flag imbalanced perturbations
imbalanced = cv[cv > 1.0].sort_values(ascending=False)

print(f"Perturbations with high batch imbalance (CV > 1.0): {len(imbalanced)}")
print(imbalanced.head(10))
```

**Troubleshooting batch imbalance:**
- Exclude highly imbalanced perturbations from cross-batch analysis
- Perform within-batch analysis separately
- Use mixed-effects models that account for batch

---

## Outlier Detection QC

### False Positive Rate in Controls

**Expected outlier rate in non-targeting controls:**
```python
# After running outlier detection
control_cells = adata_full[adata_full.obs['gene'] == 'non-targeting']
control_outlier_rate = (control_cells.obs['classification'] == -1).mean()

print(f"Control outlier rate: {control_outlier_rate:.1%}")
```

**Interpretation:**
- ✅ <5%: Good, expected false positive rate
- ⚠️ 5-10%: Elevated, consider adjusting contamination parameter
- ❌ >10%: High false positives, troubleshoot (batch effects, technical artifacts)

**Adjusting LocalOutlierFactor contamination:**
```python
# Default: contamination='auto' (typically 5-10%)
# If too many false positives:
clf = LocalOutlierFactor(novelty=True, contamination=0.03).fit(x)  # Stricter (3%)
```

### Hit Rate Expectations

**Expected hit rates by screen type:**
| Screen Type | Expected Hit Rate | Interpretation |
|-------------|-----------------|---------------|
| Genome-wide essential genes | 5-10% | Well-characterized hits |
| Targeted pathway screen | 10-30% | Enriched for functional genes |
| Candidate gene screen | 20-50% | Pre-selected for relevance |
| Unbiased discovery | 1-5% | True discovery rate |

**Troubleshooting abnormal hit rates:**
- **Too many hits (>50%)**: False positives, overly sensitive thresholds, technical artifacts
- **Too few hits (<1%)**: Insensitive thresholds, poor sgRNA activity, insufficient phenotype

---

## Recommended QC Workflow

### Step-by-Step QC Pipeline

```python
# 1. Load data
adata = sc.read_10x_h5("raw_feature_bc_matrix.h5")

# 2. Calculate QC metrics
sc.pp.calculate_qc_metrics(adata, inplace=True)

# 3. Plot QC distributions
sc.pl.violin(adata, ['n_genes_by_counts', 'total_counts', 'pct_counts_mt'])
sc.pl.scatter(adata, x='total_counts', y='pct_counts_mt')
sc.pl.scatter(adata, x='total_counts', y='n_genes_by_counts')

# 4. Identify thresholds visually
# Look for inflection points in distributions

# 5. Apply filters (cell-type specific)
adata = adata[adata.obs['n_genes_by_counts'] > 2000, :]
adata = adata[adata.obs['total_counts'] > 8000, :]
adata = adata[adata.obs['pct_counts_mt'] < 15, :]

# 6. Filter genes (optional)
sc.pp.filter_genes(adata, min_cells=10)

# 7. Check cells per perturbation
cells_per_gene = adata.obs.groupby('gene').size()
print(cells_per_gene[cells_per_gene < 20])  # Flag low-coverage perturbations

# 8. Check batch effects
sc.tl.pca(adata)
sc.pl.pca(adata, color='batch')

# 9. Save filtered data
adata.write('adata_filtered.h5ad')
```

### QC Report Checklist

Before proceeding to analysis, verify:

- [ ] Mapping rate >40% (sgRNA to cells)
- [ ] Doublet rate <15%
- [ ] Mean cells per perturbation >30
- [ ] <10% perturbations with <20 cells
- [ ] Control cells >5% of total
- [ ] Batch variance <15% (PC1-10)
- [ ] QC metrics distributions reasonable for cell type
- [ ] No obvious technical artifacts in PCA

---

## Cell-Type Specific Example Thresholds

### Complete Parameter Sets

**Primary cortical neurons:**
```python
qc_params = {
    'min_genes': 2500,
    'max_genes': 8000,
    'min_counts': 8000,
    'max_counts': 50000,
    'max_mito_pct': 0.12,
    'max_ribo_pct': 0.40
}
```

**PBMCs:**
```python
qc_params = {
    'min_genes': 500,
    'max_genes': 5000,
    'min_counts': 1000,
    'max_counts': 30000,
    'max_mito_pct': 0.20,
    'max_ribo_pct': 0.50
}
```

**K562 cells:**
```python
qc_params = {
    'min_genes': 2000,
    'max_genes': 6000,
    'min_counts': 5000,
    'max_counts': 40000,
    'max_mito_pct': 0.20,
    'max_ribo_pct': 0.45
}
```

Use these as starting points and adjust based on your specific data distributions.
