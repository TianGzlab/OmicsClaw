# Troubleshooting Guide for Pooled CRISPR Screens

Common problems encountered during pooled CRISPR screen analysis and their solutions.

---

## Data Loading Issues

### Problem: "ValueError: Variable names are not unique"

**Symptoms:**
```
ValueError: Variable names are not unique. To make them unique, call `.var_names_make_unique`.
```

**Cause:** Duplicate gene symbols in 10X feature matrix (common with gene symbol aliases)

**Solution:**
```python
# Automatically make gene names unique
adata.var_names_make_unique()

# Or manually inspect duplicates
duplicates = adata.var_names[adata.var_names.duplicated()].unique()
print(f"Duplicate genes: {duplicates}")
```

---

### Problem: Low sgRNA Mapping Rate (<30%)

**Symptoms:**
- <30% of cells have assigned sgRNA
- Many cells without sgRNA annotation

**Possible Causes:**
1. **Poor sgRNA capture efficiency**
   - Check Feature Barcoding library quality (Bioanalyzer)
   - Verify sgRNA amplification cycles (12-15 cycles typical)
   - Check sgRNA library concentration

2. **Incorrect sgRNA reference file**
   - Verify sgRNA IDs match library design
   - Check for typos or version mismatches
   - Ensure correct barcode format (10X vs custom)

3. **Low viral MOI**
   - Titrate virus and increase MOI to 0.3-0.5
   - Check viral titer by qPCR or flow cytometry

**Diagnostic Steps:**
```python
# Check mapping file format
df_sg_map = pd.read_table('sgrna_mapping.txt', header=None)
print(df_sg_map.head())
print(f"Total mappings: {len(df_sg_map)}")
print(f"Unique sgRNAs: {df_sg_map[1].nunique()}")

# Check cell barcode overlap
cell_barcodes = set(adata.obs_names)
mapping_barcodes = set(df_sg_map.index)
overlap = cell_barcodes & mapping_barcodes
print(f"Barcode overlap: {len(overlap)}/{len(cell_barcodes)} ({len(overlap)/len(cell_barcodes):.1%})")
```

**Solutions:**
- **If barcode format mismatch**: Reprocess CellRanger with correct feature reference
- **If low viral titer**: Re-transduce at higher MOI
- **If amplification issue**: Increase PCR cycles for Feature Barcode library

---

### Problem: High sgRNA Doublet Rate (>15%)

**Symptoms:**
- >15% of cells have multiple sgRNAs
- Uneven sgRNA representation

**Possible Causes:**
1. **MOI too high** (>0.8)
2. **Ambient RNA contamination**
3. **Barcode collision** (sgRNA barcodes too similar)

**Diagnostic:**
```python
# Calculate doublet rate
def calculate_doublet_rate(adata, sgrna_col='sgRNA', threshold=0.7):
    # For each cell, calculate fraction of UMI from top sgRNA
    # (Requires feature barcode UMI matrix)
    pass  # Implement based on your sgRNA UMI data

# Check sgRNA UMI distribution
import seaborn as sns
sns.histplot(data=adata.obs, x='sgrna_umi_count', bins=50)
```

**Solutions:**
- **Lower MOI**: Titrate to 0.3-0.5 for future experiments
- **Computational doublet removal**: Filter cells with <70% UMI from single sgRNA
- **Dead cell removal**: Use DAPI/7-AAD sorting before 10X capture

---

## Quality Control Issues

### Problem: Too Few Cells After QC (<50% retention)

**Symptoms:**
- >50% of cells filtered out during QC
- Many perturbations with <20 cells remaining

**Possible Causes:**
1. **Too strict QC thresholds**
2. **Poor cell health** at time of capture
3. **CRISPR perturbation causes cell stress**

**Diagnostic:**
```python
# Plot QC distributions
import matplotlib.pyplot as plt

fig, axes = plt.subplots(1, 3, figsize=(15, 4))

axes[0].hist(adata.obs['n_genes'], bins=50)
axes[0].axvline(2000, color='red', linestyle='--', label='Threshold')
axes[0].set_xlabel('Genes per cell')

axes[1].hist(adata.obs['n_counts'], bins=50)
axes[1].axvline(8000, color='red', linestyle='--', label='Threshold')
axes[1].set_xlabel('UMI per cell')

axes[2].hist(adata.obs['percent_mito'], bins=50)
axes[2].axvline(0.15, color='red', linestyle='--', label='Threshold')
axes[2].set_xlabel('Mitochondrial %')

plt.tight_layout()
plt.show()

# Check if thresholds are appropriate
print(f"% cells above gene threshold: {(adata.obs['n_genes'] > 2000).mean():.1%}")
print(f"% cells above count threshold: {(adata.obs['n_counts'] > 8000).mean():.1%}")
print(f"% cells below mito threshold: {(adata.obs['percent_mito'] < 0.15).mean():.1%}")
```

**Solutions:**
- **Relax QC thresholds**: Use cell-type appropriate thresholds (see qc_guidelines.md)
- **Two-stage QC**: Apply strict QC to controls, relaxed QC to perturbed cells
- **Improve cell health**: Optimize culture conditions, dead cell removal

**Two-stage QC approach:**
```python
# Strict QC for controls
control_cells = adata[adata.obs['gene'] == 'non-targeting'].copy()
control_qc = apply_qc_filters(control_cells, min_genes=2500, max_mito_pct=0.12)

# Relaxed QC for perturbed cells
perturbed_cells = adata[adata.obs['gene'] != 'non-targeting'].copy()
perturbed_qc = apply_qc_filters(perturbed_cells, min_genes=2000, max_mito_pct=0.20)

# Combine
adata_filtered = ad.concat([control_qc, perturbed_qc])
```

---

### Problem: Specific Perturbations Have Very Few Cells (<10)

**Symptoms:**
- Most perturbations have 50+ cells
- A few perturbations have <10 cells

**Possible Causes:**
1. **Lethal phenotype** (expected for essential genes)
2. **sgRNA under-represented** in library
3. **Batch-specific dropout**

**Diagnostic:**
```python
# Check cells per perturbation
cells_per_gene = adata.obs.groupby('gene').size().sort_values()
print("Bottom 10 perturbations:")
print(cells_per_gene.head(10))

# Check if low-count genes are essential
essential_genes = ['RPS19', 'RPL5', 'POLR2A']  # Example essential genes
low_count_genes = cells_per_gene[cells_per_gene < 10].index.tolist()
essential_overlap = set(low_count_genes) & set(essential_genes)
print(f"Overlap with essential genes: {essential_overlap}")

# Check batch distribution
crosstab = pd.crosstab(adata.obs['gene'], adata.obs['batch'])
print("Perturbations missing from batches:")
print(crosstab[crosstab.min(axis=1) == 0])
```

**Solutions:**
- **Essential genes**: Expected depletion, exclude from analysis or note in results
- **Library representation**: Check plasmid library by NGS, remake virus if needed
- **Batch dropout**: Exclude batch-specific perturbations or analyze batches separately

---

## Normalization Issues

### Problem: "MALAT1" or ribosomal genes dominate total counts

**Symptoms:**
```
Normalizing counts per cell. The following highly-expressed genes are not considered:
['MALAT1', 'RPS19', 'RPL5', ...]
```

**Cause:** Some genes are extremely highly expressed and dominate normalization

**Solution:**
```python
# Exclude highly expressed genes from normalization (scanpy does this automatically)
sc.pp.normalize_total(adata, target_sum=1e6, exclude_highly_expressed=True)

# Or manually exclude specific genes
exclude_genes = ['MALAT1', 'NEAT1']
adata_norm = adata[:, ~adata.var_names.isin(exclude_genes)].copy()
sc.pp.normalize_total(adata_norm, target_sum=1e6)
```

---

## Outlier Detection Issues

### Problem: Too Many Outliers Detected (>50% of cells)

**Symptoms:**
- Most perturbations called as "hits"
- High outlier fraction in non-targeting controls (>10%)

**Possible Causes:**
1. **Contamination parameter too relaxed**
2. **Batch effects** driving outlier calls
3. **Too few control cells** (overfitting)

**Diagnostic:**
```python
# Check control outlier rate
control_outlier_rate = results['perturbation_summary'][
    results['perturbation_summary']['gene'] == 'non-targeting'
]['outlier_fraction'].values[0]

print(f"Control outlier rate: {control_outlier_rate:.1%}")
# Should be <5%, ideally 1-3%

# Check PCA for batch effects
sc.tl.pca(adata)
sc.pl.pca(adata, color=['batch', 'gene'])
# If PC1/PC2 driven by batch → batch effect problem
```

**Solutions:**
- **Adjust contamination**: Lower to 0.03-0.05
  ```python
  clf = LocalOutlierFactor(novelty=True, contamination=0.03)
  ```
- **Batch correction**: Apply Harmony or Seurat integration
  ```python
  import scanpy.external as sce
  sce.pp.harmony_integrate(adata, 'batch')
  ```
- **More control cells**: Ensure ≥100 control cells per batch

---

### Problem: Too Few Outliers Detected (<1% of perturbations)

**Symptoms:**
- Few or no perturbations called as hits
- Known positive controls not detected

**Possible Causes:**
1. **Weak perturbation effects** (insufficient knockdown/activation)
2. **Contamination parameter too strict**
3. **Insufficient DE genes** for PCA

**Diagnostic:**
```python
# Check DE genes per perturbation
de_gene_counts = results['perturbation_summary']['n_de_genes']
print(f"Median DE genes: {de_gene_counts.median()}")
print(f"Perturbations with <10 DE genes: {(de_gene_counts < 10).sum()}")

# Check target gene expression (CRISPRi should reduce target)
target_gene = 'SOX5'
if target_gene in adata.var_names:
    control_expr = adata[adata.obs['gene'] == 'non-targeting', target_gene].X.mean()
    perturbed_expr = adata[adata.obs['gene'] == target_gene, target_gene].X.mean()
    fold_change = perturbed_expr / control_expr
    print(f"{target_gene} expression (perturbed/control): {fold_change:.2f}")
    # Should be <0.5 for CRISPRi, >2 for CRISPRa
```

**Solutions:**
- **Lower contamination**: Increase to 0.10-0.15
  ```python
  clf = LocalOutlierFactor(novelty=True, contamination=0.10)
  ```
- **Lower min_de_genes threshold**: Try 5 instead of 10
  ```python
  results = detect_perturbed_cells(adata, min_de_genes=5)
  ```
- **Try different outlier method**: Switch to IsolationForest
  ```python
  results = detect_perturbed_cells(adata, method='IsolationForest')
  ```
- **Check sgRNA activity**: Validate target gene knockdown by qPCR

---

## Differential Expression Issues

### Problem: No DE genes for most perturbations

**Symptoms:**
- Most perturbations have 0 DE genes (p < 0.05)
- Positive controls show no DE

**Possible Causes:**
1. **Insufficient cells per perturbation** (<20)
2. **High noise** (low sequencing depth)
3. **Weak perturbation effects**

**Diagnostic:**
```python
# Check cells per perturbation
cells_per_gene = adata.obs.groupby('gene').size()
print(f"Median cells per perturbation: {cells_per_gene.median()}")

# Check sequencing depth
print(f"Median UMI per cell: {adata.obs['n_counts'].median()}")

# Check variance in data
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
print(f"Highly variable genes: {adata.var['highly_variable'].sum()}")
```

**Solutions:**
- **Aggregate cells**: Pseudobulk approach if <50 cells per perturbation
  ```python
  # Create pseudobulk by summing counts
  pseudobulk = adata.to_df().groupby(adata.obs['gene']).sum()
  ```
- **Use outlier cells only**: Restrict DE to cells with phenotypes
  ```python
  de_results = run_de_analysis(adata, use_outliers_only=True, outlier_cells=outlier_cells)
  ```
- **Relax p-value**: Use p < 0.10 for initial screening

---

### Problem: Memory Error During DE Analysis

**Symptoms:**
```
MemoryError: Unable to allocate array with shape (100000, 20000)
```

**Cause:** Dataset too large for in-memory operations

**Solutions:**

**1. Process in chunks:**
```python
# Process perturbations in batches of 100
genes = adata.obs['gene'].unique()
batch_size = 100

for i in range(0, len(genes), batch_size):
    batch_genes = genes[i:i+batch_size]
    adata_batch = adata[adata.obs['gene'].isin(batch_genes)]
    de_results_batch = run_de_analysis(adata_batch)
    # Save results incrementally
```

**2. Use backed mode:**
```python
# Load data in backed mode (on-disk storage)
adata = sc.read_h5ad('data.h5ad', backed='r')

# Operations will use disk instead of RAM
```

**3. Downsample data:**
```python
# Randomly sample 1000 cells per perturbation
adata_downsampled = adata.copy()
for gene in adata.obs['gene'].unique():
    cells = adata[adata.obs['gene'] == gene].obs_names
    if len(cells) > 1000:
        keep = np.random.choice(cells, 1000, replace=False)
        adata_downsampled = adata_downsampled[
            (adata_downsampled.obs['gene'] != gene) |
            (adata_downsampled.obs_names.isin(keep))
        ]
```

---

## Batch Effect Issues

### Problem: Strong Batch Effects in PCA

**Symptoms:**
- PC1-2 driven by batch, not biology
- Different QC metrics across batches
- Perturbation effects not visible in PCA

**Diagnostic:**
```python
# Compute PCA
sc.tl.pca(adata)
sc.pl.pca(adata, color=['batch', 'gene'])

# Calculate variance explained by batch
from sklearn.linear_model import LinearRegression
X = pd.get_dummies(adata.obs['batch'])
y = adata.obsm['X_pca'][:, 0]  # PC1

model = LinearRegression().fit(X, y)
r2 = model.score(X, y)
print(f"Variance in PC1 explained by batch: {r2:.1%}")
# >20% suggests strong batch effect
```

**Solutions:**

**1. Harmony integration (recommended):**
```python
import scanpy.external as sce

# Run Harmony (fast, preserves biology)
sce.pp.harmony_integrate(adata, 'batch', basis='X_pca')

# Use corrected PCA for downstream analysis
# Harmony stores corrected PCA in adata.obsm['X_pca_harmony']
```

**2. Seurat integration:**
```python
# For small datasets (<50k cells)
import scanpy as sc

# Split by batch
adata_batches = [adata[adata.obs['batch'] == b].copy() for b in adata.obs['batch'].unique()]

# Integrate
adata_integrated = sc.external.pp.seurat_v3_integrate(adata_batches, basis='X_pca')
```

**3. Regress out batch:**
```python
# For linear batch effects
sc.pp.regress_out(adata, ['batch'])
sc.pp.scale(adata)
```

**4. Analyze batches separately:**
```python
# If batch effects are too strong
for batch in adata.obs['batch'].unique():
    adata_batch = adata[adata.obs['batch'] == batch].copy()
    results_batch = detect_perturbed_cells(adata_batch)
```

---

## Visualization Issues

### Problem: UMAP plots show scattered, unstructured clouds

**Symptoms:**
- No clear structure in UMAP
- Perturbations don't separate from controls

**Possible Causes:**
1. **Insufficient preprocessing** (not normalized/scaled)
2. **Too few PCs** used for neighbors
3. **High noise-to-signal ratio**

**Solutions:**

**1. Increase PCs for UMAP:**
```python
# Use more PCs (30-50 instead of default 10-20)
sc.pp.neighbors(adata, n_pcs=50)
sc.tl.umap(adata)
```

**2. Feature selection:**
```python
# Use highly variable genes only
sc.pp.highly_variable_genes(adata, n_top_genes=2000)
adata_hvg = adata[:, adata.var['highly_variable']].copy()
sc.tl.pca(adata_hvg)
sc.pp.neighbors(adata_hvg)
sc.tl.umap(adata_hvg)
```

**3. Adjust UMAP parameters:**
```python
# Increase min_dist for more global structure
sc.tl.umap(adata, min_dist=0.5)

# Increase n_neighbors for smoother embedding
sc.pp.neighbors(adata, n_neighbors=30)
sc.tl.umap(adata)
```

---

### Problem: Can't visualize target gene (not in matrix)

**Symptoms:**
```
KeyError: 'SOX5' not found in var_names
```

**Cause:** Gene name mismatch between sgRNA target and expression matrix

**Solution:**
```python
# Detect mismatches
from scripts.gene_name_corrections import detect_mismatches, suggest_corrections

mismatches = detect_mismatches(adata, gene_col='gene')

# Apply corrections
corrections = {
    'TMEM55A': 'PIP4P2',
    'ATP5C1': 'ATP5F1C',
    'ATP5H': 'ATP5PD'
}

adata = correct_gene_names(adata, corrections)

# Or use automated synonym lookup
corrections = suggest_corrections(adata, use_synonyms=True)
adata = correct_gene_names(adata, corrections)
```

---

## Export Issues

### Problem: Excel file too large (>100 MB)

**Symptoms:**
- Excel export fails or file is huge
- "Maximum file size exceeded"

**Solution:**
```python
# Split into multiple Excel files
for i, batch_genes in enumerate(np.array_split(list(de_results.keys()), 10)):
    excel_path = f'de_results_batch_{i+1}.xlsx'
    with pd.ExcelWriter(excel_path) as writer:
        for gene in batch_genes:
            de_results[gene].head(50).to_excel(writer, sheet_name=gene[:31])

# Or export as CSV (more compact)
for gene, de_df in de_results.items():
    de_df.to_csv(f'DEG/{gene}_de_results.csv')
```

---

## Experimental Design Issues (For Future Screens)

### Problem: Uneven sgRNA Representation

**Prevention:**
- Sequence plasmid library before lentiviral production
- Check sgRNA representation by NGS (should be uniform)
- Use balanced library design tools (e.g., CRISPick, Azimuth)

### Problem: Population Drift (Strong Selection)

**Prevention:**
- Limit culture time post-transduction (<14 days)
- Harvest cells early if strong phenotypes expected
- Consider using early time points for lethal perturbations

### Problem: Low sgRNA Capture Efficiency

**Prevention:**
- Optimize Feature Barcoding library prep
- Increase sgRNA amplification cycles (15-18 instead of 12)
- Use higher input cell numbers for 10X capture
- Consider direct guide capture methods (Replogle 2020)

---

## Getting Help

If issues persist after troubleshooting:

1. **Check data quality at source:**
   - Review CellRanger output logs
   - Check sequencing depth and saturation
   - Verify library QC (Bioanalyzer, qPCR)

2. **Consult references:**
   - [10X Feature Barcoding protocol](https://support.10xgenomics.com/single-cell-gene-expression/software/pipelines/latest/algorithms/crispr)
   - [Perturb-seq analysis guide](https://github.com/sanjanalab/ScreenProcessing)
   - Original method papers (Dixit 2016, Replogle 2020)

3. **Community resources:**
   - [Seurat CRISPR vignettes](https://satijalab.org/seurat/)
   - [scanpy tutorials](https://scanpy.readthedocs.io/en/stable/tutorials.html)
   - [Bioconductor support forum](https://support.bioconductor.org/)

4. **Experimental validation:**
   - Always validate top hits independently
   - Check target gene knockdown/activation by qPCR/Western
   - Replicate hits in bulk culture with individual sgRNAs
