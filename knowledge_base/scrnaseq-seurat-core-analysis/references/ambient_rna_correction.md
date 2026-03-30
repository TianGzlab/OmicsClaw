# Ambient RNA Correction Guide

## Overview

Ambient RNA (also called "soup" or "background RNA") is cell-free RNA present in the suspension during droplet-based single-cell RNA-seq library preparation. This contamination can lead to false-positive gene detection and misidentification of cell types.

This guide covers when, why, and how to perform ambient RNA correction using CellBender and SoupX.

---

## Why Correct Ambient RNA?

### The Problem

During 10X Chromium and similar droplet-based scRNA-seq protocols:
1. Cells are lysed within droplets
2. Some cellular material leaks into the surrounding solution
3. This "ambient RNA" gets captured in droplets containing other cells
4. All cells receive a background of this ambient RNA

**Consequences:**
- False expression of cell-type-specific genes in wrong cell types
- Inflated gene detection rates
- Contamination of differential expression analyses
- Misidentification of cell types (e.g., neurons expressing immune genes)

### When to Correct

**Always correct for:**
- ✅ **Raw CellRanger output** (raw_feature_bc_matrix/)
- ✅ **High-soup tissues:** Brain, lung, tumor, lymph nodes, dissociated tissues
- ✅ **Poor sample quality:** Increased cell death during preparation
- ✅ **Long processing times:** Extended time between dissociation and droplet generation

**May skip for:**
- ❌ **Pre-filtered data** that was already corrected
- ❌ **Low-soup tissues:** Blood (PBMCs collected fresh)
- ❌ **Nuclei-based methods:** snRNA-seq (less ambient RNA)

---

## Methods Comparison

### CellBender

**Pros:**
- State-of-the-art deep learning approach
- Automatically estimates contamination
- Handles complex contamination patterns
- Provides uncertainty estimates

**Cons:**
- Requires GPU for practical speed (10-20x faster than CPU)
- Takes longer to run (~30-60 min per sample)
- Black-box model (less interpretable)

**Best for:** Most use cases, especially brain/tumor samples

**Installation:**
```bash
pip install cellbender
```

### SoupX

**Pros:**
- Fast (minutes per sample)
- Interpretable method
- Works well for straightforward contamination
- No GPU required

**Cons:**
- Requires filtered matrix (needs cell calling first)
- Less effective for complex contamination patterns
- Manual threshold selection sometimes needed

**Best for:** Quick analysis, when CellBender not available, interpretability needed

**Installation:**
```r
# R
install.packages("SoupX")
```

```bash
# Python (via existing implementation)
# See scripts/remove_ambient_rna.py
```

---

## CellBender Usage

### Basic Command

```bash
cellbender remove-background \
    --input raw_feature_bc_matrix.h5 \
    --output cellbender_output.h5 \
    --expected-cells 10000 \
    --total-droplets-included 30000 \  # 2-3x expected cells
    --epochs 200 \
    --cuda  # Use GPU
```

### Key Parameters

**--expected-cells**
- Approximate number of real cells
- Get from CellRanger web summary
- Or estimate from knee plot

**--total-droplets-included**
- Total droplets to analyze (cells + empty)
- **Critical parameter:** Should be 2-3x expected cells
- Too low: Poor ambient profile estimation
- Too high: Slower, may include low-quality cells
- **High-soup tissues:** Use 3x expected cells

**--epochs**
- Training iterations
- Default: 150
- Increase to 200-300 for better results on complex data

**--fpr**
- False positive rate for cell calling
- Default: 0.01 (1%)
- Lower values: More conservative cell calling

### Output Files

- `cellbender_output_filtered.h5`: Corrected counts (filtered cells)
- `cellbender_output_cell_barcodes.csv`: Called cell barcodes
- `cellbender_output_metrics.csv`: QC metrics
- `cellbender_output.pdf`: Diagnostic plots

### Python Wrapper

```python
from scripts.remove_ambient_rna import run_cellbender

adata = run_cellbender(
    raw_h5="raw_feature_bc_matrix.h5",
    expected_cells=10000,
    total_droplets=30000,
    output_dir="results/cellbender",
    epochs=200,
    use_cuda=True
)
```

---

## SoupX Usage

### Basic R Workflow

```r
library(SoupX)
source("scripts/remove_ambient_rna.R")

# Load raw and filtered matrices
seurat_corrected <- run_soupx_correction(
  raw_matrix_dir = "raw_feature_bc_matrix/",
  filtered_matrix_dir = "filtered_feature_bc_matrix/",
  output_dir = "results/soupx"
)

# Check contamination
contamination <- estimate_soup_fraction(seurat_corrected)
cat(sprintf("Estimated contamination: %.1f%%\n", contamination * 100))
```

### Python Wrapper

```python
from scripts.remove_ambient_rna import run_soupx_python

adata = run_soupx_python(
    raw_matrix_dir="raw_feature_bc_matrix/",
    filtered_matrix_dir="filtered_feature_bc_matrix/"
)
```

### SoupX Parameters

**auto_estimate**
- Automatically estimate contamination (default: TRUE)
- Alternative: Manual estimation with specified genes

**contamination_range**
- Expected contamination range
- Default: c(0.01, 0.5)
- High-soup tissues: c(0.05, 0.5)

---

## Interpreting Results

### Contamination Levels

| Contamination | Interpretation | Action |
|---------------|----------------|--------|
| <5% | Low | Continue with analysis |
| 5-15% | Moderate | Expected for many tissues |
| 15-25% | High | Review sample quality |
| >25% | Very high | Consider excluding sample |

### Quality Checks

**1. Before/After Comparison**
- Total UMI counts should decrease 5-20%
- Gene detection should decrease slightly
- Cell type markers should be more specific

**2. Marker Gene Expression**
- Check cell-type-specific genes
- Contamination should reduce expression in wrong cells
- Example: Check if neurons still express immune genes

**3. Contamination Profile**
- Most contaminated genes: High abundance, highly expressed
- Typical: Hemoglobin genes, ribosomal genes, mitochondrial genes
- Tissue-specific: Brain (e.g., SYT1), Blood (HBA1, HBB)

---

## Tissue-Specific Guidelines

### Brain Tissue

**Contamination:** HIGH (15-30%)
- Neurons are fragile and lyse easily
- High synaptic vesicle content
- Common contaminants: SYT1, SNAP25, NRXN genes

**Recommendation:**
- Always use CellBender
- Set `--total-droplets-included` to 3x expected cells
- Increase epochs to 250-300

### Lung Tissue

**Contamination:** HIGH (10-25%)
- Dissociation releases surfactant proteins
- Type II pneumocytes contribute abundant RNA
- Common contaminants: SFTPC, SFTPB genes

**Recommendation:**
- Use CellBender or hybrid SoupX approach
- Higher contamination estimates expected

### Tumor Tissue

**Contamination:** VARIABLE (10-30%)
- Depends on necrosis and dissociation method
- Dead/dying cells release RNA
- Common contaminants: Cell-cycle genes, stress response

**Recommendation:**
- Always correct
- CellBender preferred for complex contamination

### PBMC (Peripheral Blood)

**Contamination:** LOW (2-8%)
- Fresh blood has minimal ambient RNA
- Mostly hemoglobin contamination
- Common contaminants: HBA1, HBB, HBG genes

**Recommendation:**
- Optional correction
- SoupX sufficient if correction needed
- Skip if fresh blood processed immediately

---

## Common Issues

### Issue 1: CellBender Fails to Converge

**Symptoms:** Training loss doesn't decrease, poor fit

**Solutions:**
- Increase `--epochs` to 300-400
- Adjust `--total-droplets-included` (try 2.5x instead of 3x)
- Check if input is truly raw matrix (not filtered)

### Issue 2: Over-Correction

**Symptoms:** Too much signal removed, biological variation lost

**Solutions:**
- Check contamination estimate (<25% is reasonable)
- For SoupX: Lower contamination fraction manually
- For CellBender: Use `--fpr 0.005` (more conservative)

### Issue 3: GPU Out of Memory

**Symptoms:** CUDA out of memory error

**Solutions:**
- Reduce `--total-droplets-included`
- Use CPU (slower): remove `--cuda` flag
- Use smaller batch size (if option available)

---

## Validation

### Check 1: Marker Gene Specificity

```python
# Before correction
sc.pl.umap(adata_before, color=['CD3D', 'MS4A1'], cmap='Reds')

# After correction
sc.pl.umap(adata_after, color=['CD3D', 'MS4A1'], cmap='Reds')
```

**Expected:** Cell type markers more restricted to correct cell types

### Check 2: Total UMI Reduction

```python
before_counts = adata_before.X.sum(axis=1).mean()
after_counts = adata_after.X.sum(axis=1).mean()
reduction_pct = (1 - after_counts/before_counts) * 100

print(f"Average UMI reduction: {reduction_pct:.1f}%")
```

**Expected:** 5-20% reduction

### Check 3: Cell Type Separation

```python
# Compute cell type purity before/after
# Should see improved separation in UMAP/clustering
```

---

## Best Practices

1. ✅ **Always start with raw matrices** for correction
2. ✅ **Document contamination levels** in your analysis
3. ✅ **Compare before/after** using marker genes
4. ✅ **Use tissue-appropriate parameters** (high-soup vs low-soup)
5. ✅ **Run correction per batch** if multiple samples
6. ❌ **Don't double-correct** (check if data already corrected)
7. ❌ **Don't use normalized counts** as input
8. ❌ **Don't skip for high-soup tissues** (brain, tumor, lung)

---

## Key References

1. **CellBender**: Fleming SJ, et al. Unsupervised removal of systematic background noise from droplet-based single-cell experiments using CellBender. *bioRxiv*. 2019.
   - https://github.com/broadinstitute/CellBender

2. **SoupX**: Young MD, Behjati S. SoupX removes ambient RNA contamination from droplet-based single-cell RNA sequencing data. *GigaScience*. 2020;9(12):giaa151.
   - https://github.com/constantAmateur/SoupX

3. **Benchmark**: Xi NM, Li JJ. Benchmarking computational doublet-detection methods for single-cell RNA sequencing data. *Cell Syst*. 2021;12(2):176-194.e6.
   - Includes ambient RNA correction comparison

---

## Summary

- **Always correct for high-soup tissues** (brain, lung, tumor)
- **CellBender is the gold standard** (requires GPU)
- **SoupX is a good alternative** (faster, interpretable)
- **Check contamination levels** (5-15% is typical)
- **Validate results** with marker genes
- **Document methods** clearly in your analysis

Following these guidelines ensures cleaner data and more accurate biological conclusions from your single-cell RNA-seq experiments.
