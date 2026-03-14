---
name: proteomics-de
description: >-
  Differential protein abundance testing using MSstats, limma, proDA,
  and scipy/statsmodels for Python. Multiple testing correction with BH FDR.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [proteomics, differential, MSstats, limma, volcano]
metadata:
  omicsclaw:
    domain: proteomics
    emoji: "⚖️"
    trigger_keywords: [differential abundance, protein expression, MSstats, limma, volcano]
---

# ⚖️ Differential Protein Abundance

Statistical testing for differentially abundant proteins between experimental conditions.

## Core Capabilities

1. **MSstats**: Feature-level mixed models with group comparison
2. **limma**: Empirical Bayes moderated t-tests on protein-level data
3. **proDA**: Probabilistic handling of missing values
4. **scipy/statsmodels (Python)**: T-test with FDR correction
5. **Visualization**: Volcano plots, heatmaps

## CLI Reference

```bash
python omicsclaw.py run differential-abundance --demo
python omicsclaw.py run differential-abundance --input <protein_matrix.csv> --output <dir>
```

## Algorithm / Methodology

### MSstats Group Comparison (R)

```r
library(MSstats)

comparison_matrix <- matrix(c(1, -1, 0, 0,
                               1, 0, -1, 0,
                               0, 1, -1, 0),
                             nrow = 3, byrow = TRUE)
rownames(comparison_matrix) <- c('Treatment1-Control', 'Treatment2-Control', 'Treatment1-Treatment2')
colnames(comparison_matrix) <- c('Control', 'Treatment1', 'Treatment2', 'Treatment3')

results <- groupComparison(contrast.matrix = comparison_matrix, data = processed)

sig_proteins <- results$ComparisonResult[results$ComparisonResult$adj.pvalue < 0.05 &
                                          abs(results$ComparisonResult$log2FC) > 1, ]
```

### limma for Proteomics (R)

```r
library(limma)

design <- model.matrix(~ 0 + condition, data = sample_info)
colnames(design) <- levels(sample_info$condition)

fit <- lmFit(protein_matrix, design)
contrast_matrix <- makeContrasts(Treatment - Control, levels = design)
fit2 <- contrasts.fit(fit, contrast_matrix)
fit2 <- eBayes(fit2)

results <- topTable(fit2, number = Inf, adjust.method = 'BH')
sig_results <- results[results$adj.P.Val < 0.05 & abs(results$logFC) > 1, ]
```

### proDA (Missing Value-Aware)

```r
library(QFeatures)
library(proDA)

fit <- proDA(protein_matrix, design = ~ condition, data = sample_info)
results <- test_diff(fit, contrast = 'conditionTreatment')
results$adj_pval <- p.adjust(results$pval, method = 'BH')
sig_results <- results[results$adj_pval < 0.05 & abs(results$diff) > 1, ]
```

### Python: scipy/statsmodels

```python
import pandas as pd
import numpy as np
from scipy import stats
from statsmodels.stats.multitest import multipletests

def differential_test(intensities, group1_cols, group2_cols):
    results = []
    for protein in intensities.index:
        g1 = intensities.loc[protein, group1_cols].dropna()
        g2 = intensities.loc[protein, group2_cols].dropna()

        if len(g1) >= 2 and len(g2) >= 2:
            stat, pval = stats.ttest_ind(g1, g2)
            log2fc = g2.mean() - g1.mean()
            results.append({'protein': protein, 'log2FC': log2fc, 'pvalue': pval})

    df = pd.DataFrame(results)
    df['adj_pvalue'] = multipletests(df['pvalue'], method='fdr_bh')[1]
    return df

sig = results[(results['adj_pvalue'] < 0.05) & (abs(results['log2FC']) > 1)]
```

### Volcano Plot (R)

```r
library(ggplot2)

ggplot(results, aes(x = log2FC, y = -log10(adj.P.Val))) +
    geom_point(aes(color = significant), alpha = 0.6) +
    geom_hline(yintercept = -log10(0.05), linetype = 'dashed') +
    geom_vline(xintercept = c(-1, 1), linetype = 'dashed') +
    scale_color_manual(values = c('grey', 'red')) +
    theme_minimal()
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `limma` | limma, msstats, proda, ttest |
| `--fdr-cutoff` | `0.05` | FDR threshold |
| `--fc-cutoff` | `1.0` | Log2FC threshold |

## Why This Exists

- **Without it**: T-tests assume independence and fail on complex experimental designs or missing MS values
- **With it**: Validated mixed-models (MSstats) and empirical Bayes (Limma) correctly handle imputation and variances
- **Why OmicsClaw**: Standardizes notoriously strict R packages into a simple Python wrapper

## Workflow

1. **Calculate**: Prepare contrast matrix and condition vectors.
2. **Execute**: Calculate log ratios and moderated t-statistics per protein.
3. **Assess**: Perform Benjamini-Hochberg FDR correction.
4. **Generate**: Output structured significant hits.
5. **Report**: Synthesize Volcano plots and heatmaps.

## Example Queries

- "Run MSstats differential abundance on this data"
- "Find differentially expressed proteins using limma"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── statistics.csv
├── figures/
│   └── volcano_plot.png
├── tables/
│   └── differential_results.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `quantification` — Upstream normalized expression
- `prot-enrichment` — Downstream pathway enrichment

## Version Compatibility

Reference examples tested with: limma 3.58+, MSstats 4.8+, scipy 1.12+, statsmodels 0.14+

## Dependencies

**Required**: numpy, pandas, scipy, statsmodels
**Optional**: MSstats (R), limma (R), proDA (R), QFeatures (R)

## Citations

- [MSstats](https://doi.org/10.1074/mcp.M113.034728) — Choi et al., MCP 2014
- [limma](https://doi.org/10.1093/nar/gkv007) — Ritchie et al., Nucleic Acids Research 2015
- [proDA](https://doi.org/10.1101/661496) — Ahlmann-Eltze & Anders, bioRxiv 2019

## Related Skills

- `quantification` — Prepare normalized data for testing
- `prot-enrichment` — Pathway enrichment of significant proteins
- `ptm` — PTM-level differential analysis
