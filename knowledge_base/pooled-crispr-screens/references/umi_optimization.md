# UMI Cutoff Optimization for sgRNA Assignment

Advanced technique for optimizing sgRNA-to-cell assignment sensitivity in large-scale CRISPR screens.

---

## Overview

The UMI threshold for assigning sgRNAs to cells affects the trade-off between sensitivity (capturing more cells per perturbation) and specificity (avoiding false assignments from ambient RNA). Testing multiple thresholds helps identify the optimal balance for your specific screen.

**Based on:** Wang et al. (2025) "Integrative analysis of pooled CRISPR screens provide functional insights into AD GWAS risk genes"

---

## When to Use UMI Optimization

### Use this approach when:
- ✅ Large screens (>500 perturbations) where optimization has high payoff
- ✅ Low guide capture efficiency (<40% mapping rate)
- ✅ Sufficient computational resources for multiple parallel analyses
- ✅ Critical screens where maximizing statistical power is essential

### Skip this step when:
- ❌ Small screens (<100 perturbations)
- ❌ High guide capture (>60% mapping rate with standard thresholds)
- ❌ Standard 10X Feature Barcoding with good quality metrics
- ❌ Time-limited pilot studies

---

## Optimization Approach

### Step 1: Generate Multiple sgRNA Assignments

Test a range of UMI cutoffs to identify the optimal threshold:

```python
# Test multiple UMI thresholds
umi_thresholds = [3, 5, 10, 15, 20]
results_by_threshold = {}

for threshold in umi_thresholds:
    # Assign sgRNAs with this threshold
    adata_temp = assign_guides_with_threshold(
        adata,
        mapping_file,
        min_umi=threshold
    )

    # Count cells per perturbation
    cells_per_gene = adata_temp.obs.groupby('gene').size()

    # Store results
    results_by_threshold[threshold] = {
        'n_cells': adata_temp.n_obs,
        'mean_cells_per_gene': cells_per_gene.mean(),
        'median_cells_per_gene': cells_per_gene.median(),
        'genes_with_sufficient_cells': (cells_per_gene >= 50).sum(),
        'genes_with_low_cells': (cells_per_gene < 20).sum()
    }
```

### Step 2: Run QC and DE Analysis

For each UMI threshold, run the full analysis pipeline:

```python
for threshold, adata_temp in adata_by_threshold.items():
    # Apply QC filters
    adata_filtered = apply_qc_filters(adata_temp)

    # Normalize and scale
    adata_norm = normalize_and_scale_data(adata_filtered)

    # Run initial DE screening
    de_results = screen_all_perturbations(
        adata_norm,
        control_group='non-targeting'
    )

    # Count hits (perturbations with significant DE)
    n_hits = sum(1 for gene, df in de_results.items()
                 if len(df[df['qval'] < 0.05]) >= 10)

    results_by_threshold[threshold]['n_hits'] = n_hits
```

### Step 3: Select Optimal Threshold

Choose the threshold that maximizes hits while maintaining sufficient cells per perturbation:

```python
import pandas as pd

# Create summary table
summary = pd.DataFrame(results_by_threshold).T
summary.index.name = 'UMI_threshold'

print(summary)

# Selection criteria:
# 1. Maximize hits
# 2. Maintain ≥50 cells per perturbation for most genes
# 3. Balance between sensitivity and specificity

# Typical result: 5 UMI is optimal for most screens
optimal_threshold = 5
```

---

## Expected Results

### Typical Optimization Outcome

| UMI Threshold | Total Cells | Mean Cells/Gene | Genes ≥50 Cells | Hits Detected |
|---------------|-------------|-----------------|-----------------|---------------|
| 3 | 45,000 | 65 | 850 | 125 |
| **5** | **42,000** | **58** | **820** | **148** |
| 10 | 35,000 | 48 | 720 | 142 |
| 15 | 28,000 | 38 | 580 | 118 |
| 20 | 22,000 | 30 | 450 | 95 |

**Optimal:** UMI threshold = 5 maximizes hits (148) while maintaining good coverage (820 genes with ≥50 cells)

### Interpretation Guidelines

**Lower thresholds (3-5 UMI):**
- ✅ Higher sensitivity (more cells captured)
- ✅ Better statistical power (more cells per perturbation)
- ⚠️ Risk of false assignments from ambient RNA
- **Use when:** Capture efficiency is low, need maximum power

**Higher thresholds (10-20 UMI):**
- ✅ Higher specificity (fewer false assignments)
- ✅ Reduced ambient RNA contamination
- ⚠️ Lower sensitivity (fewer cells per perturbation)
- **Use when:** High ambient RNA, need high confidence assignments

**Balanced thresholds (5-8 UMI):**
- ✅ Good balance of sensitivity and specificity
- ✅ Typical optimal range for most screens
- **Recommended for:** Standard 10X Feature Barcoding screens

---

## Quality Metrics to Monitor

### Assignment Quality

```python
# Calculate assignment quality metrics
for threshold, adata in adata_by_threshold.items():
    # Mapping rate
    mapping_rate = adata.n_obs / total_cells_before_filtering

    # sgRNA doublet rate
    doublet_rate = doublets_detected / cells_with_sgrna

    # Cells per perturbation distribution
    cells_per_gene = adata.obs.groupby('gene').size()
    cv = cells_per_gene.std() / cells_per_gene.mean()

    print(f"UMI threshold {threshold}:")
    print(f"  Mapping rate: {mapping_rate:.1%}")
    print(f"  Doublet rate: {doublet_rate:.1%}")
    print(f"  Coverage CV: {cv:.2f}")
```

### DE Quality

```python
# Check control outlier rates (should be <5%)
for threshold, de_results in results_by_threshold.items():
    control_de = de_results.get('non-targeting', pd.DataFrame())
    n_control_de = len(control_de[control_de['qval'] < 0.05])

    print(f"UMI threshold {threshold}:")
    print(f"  Control DE genes: {n_control_de} (should be <500)")

    # If control shows excessive DE, threshold may be too permissive
```

---

## Implementation Notes

### Computational Considerations

**Runtime:** Testing 5 thresholds increases analysis time by ~5x
- Small screen (100 genes): +30 minutes
- Large screen (1000 genes): +2-3 hours

**Memory:** Each threshold creates independent AnnData object
- Estimate: ~2-5 GB per threshold for 50k cells
- Consider processing thresholds sequentially if memory-limited

**Parallelization:**
```python
from concurrent.futures import ProcessPoolExecutor

# Run thresholds in parallel (if resources available)
with ProcessPoolExecutor(max_workers=5) as executor:
    futures = {
        executor.submit(analyze_threshold, adata, t): t
        for t in umi_thresholds
    }

    for future in futures:
        threshold = futures[future]
        results_by_threshold[threshold] = future.result()
```

### Validation Checks

After selecting optimal threshold, validate the choice:

1. **Check target gene validation rate** (should be >60%)
2. **Compare hit overlap** with adjacent thresholds (should be >70% overlap)
3. **Inspect cell count distributions** (should be balanced across genes)
4. **Review control outlier rates** (should be <5%)

---

## Alternative Approaches

### Adaptive UMI Thresholding

Instead of a single global threshold, use gene-specific thresholds based on expression:

```python
# Higher threshold for highly expressed genes (more ambient RNA)
# Lower threshold for lowly expressed genes (maximize capture)

def adaptive_threshold(gene_expression_level):
    if gene_expression_level > 100:
        return 10  # High expression
    elif gene_expression_level > 10:
        return 5   # Medium expression
    else:
        return 3   # Low expression
```

**Pros:** Balances sensitivity and specificity per gene
**Cons:** More complex, harder to validate

### Probabilistic Assignment

Use UMI counts to assign probabilities rather than hard cutoffs:

```python
# Assign probability based on UMI count distribution
p_assignment = umi_count / (umi_count + background_umi)

# Include cells with p > 0.7 (70% confidence)
```

**Pros:** Retains more information, accounts for uncertainty
**Cons:** Requires careful downstream handling of probabilities

---

## References

**Method Source:**
- Wang et al. (2025) "Integrative analysis of pooled CRISPR screens provide functional insights into AD GWAS risk genes" *bioRxiv*
  - GitHub: https://github.com/Alector-BIO/CRISPR_PerturbSeq_pHM_publication

**Related Methods:**
- Replogle et al. (2020) "Combinatorial single-cell CRISPR screens by direct guide RNA capture and targeted sequencing" *Nature Biotechnology*
  - Discusses guide capture efficiency optimization

**Statistical Considerations:**
- Storey & Tibshirani (2003) "Statistical significance for genomewide studies" *PNAS*
  - Multiple testing correction with variable sample sizes


---
