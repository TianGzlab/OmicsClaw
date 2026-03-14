---
name: met-diff
description: >-
  Metabolomics differential analysis using univariate tests (t-test, FDR),
  multivariate methods (PCA, PLS-DA, OPLS-DA, sPLS-DA), Random Forest,
  and ROC analysis for biomarker discovery.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [metabolomics, differential, PLS-DA, volcano, biomarker, ROC]
metadata:
  omicsclaw:
    domain: metabolomics
    emoji: "📈"
    trigger_keywords: [metabolomics differential, PLS-DA, volcano plot, biomarker, OPLS-DA]
---

# 📈 Metabolomics Differential Analysis

Univariate and multivariate statistical analysis for identifying differentially abundant metabolites and biomarker discovery.

## Core Capabilities

1. **Univariate testing**: t-test, Wilcoxon, ANOVA with BH FDR correction
2. **Fold change**: Log2FC calculation with volcano plot visualization
3. **PCA**: Unsupervised exploration and outlier detection
4. **PLS-DA / sPLS-DA**: Supervised classification with VIP scores and sparse feature selection
5. **OPLS-DA**: Orthogonal PLS-DA with S-plot for predictive features
6. **Random Forest**: Non-linear feature importance ranking
7. **ROC analysis**: Diagnostic performance evaluation of candidate biomarkers

## CLI Reference

```bash
python omicsclaw.py run met-diff --demo
python omicsclaw.py run met-diff --input <feature_table.csv> --output <dir>
```

## Algorithm / Methodology

### Univariate Analysis (R)

```r
library(tidyverse)

data <- read.csv('normalized_data.csv', row.names = 1)
groups <- factor(read.csv('sample_info.csv')$group)

# T-test for each feature
ttest_results <- apply(data, 2, function(x) {
    test <- t.test(x ~ groups)
    c(pvalue = test$p.value,
      fc = mean(x[groups == levels(groups)[2]]) - mean(x[groups == levels(groups)[1]]))
})
ttest_results <- as.data.frame(t(ttest_results))
ttest_results$fdr <- p.adjust(ttest_results$pvalue, method = 'BH')

sig_features <- ttest_results[ttest_results$fdr < 0.05, ]
```

### Volcano Plot (R)

```r
library(ggplot2)

results$significant <- results$fdr < 0.05 & abs(results$log2fc) > 1

ggplot(results, aes(x = log2fc, y = -log10(pvalue), color = significant)) +
    geom_point(alpha = 0.6) +
    scale_color_manual(values = c('gray', 'red')) +
    geom_hline(yintercept = -log10(0.05), linetype = 'dashed') +
    geom_vline(xintercept = c(-1, 1), linetype = 'dashed') +
    labs(x = 'Log2 Fold Change', y = '-log10(p-value)') +
    theme_bw()
```

### PCA (R)

```r
library(pcaMethods)

pca_result <- pca(data, nPcs = 5, method = 'ppca')
scores <- as.data.frame(scores(pca_result))
scores$group <- groups

ggplot(scores, aes(x = PC1, y = PC2, color = group)) +
    geom_point(size = 3) +
    stat_ellipse(level = 0.95) +
    labs(x = paste0('PC1 (', round(pca_result@R2[1] * 100, 1), '%)'),
         y = paste0('PC2 (', round(pca_result@R2[2] * 100, 1), '%)')) +
    theme_bw()
```

### PLS-DA with VIP Scores (mixOmics)

```r
library(mixOmics)

plsda_result <- plsda(as.matrix(data), groups, ncomp = 3)

# Cross-validation
perf_plsda <- perf(plsda_result, validation = 'Mfold', folds = 5, nrepeat = 50)
ncomp_opt <- perf_plsda$choice.ncomp['BER', 'centroids.dist']

# Final model + VIP scores
final_plsda <- plsda(as.matrix(data), groups, ncomp = ncomp_opt)
plotIndiv(final_plsda, group = groups, ellipse = TRUE, legend = TRUE)

vip <- vip(final_plsda)
top_vip <- sort(vip[, ncomp_opt], decreasing = TRUE)[1:20]
```

### sPLS-DA (Sparse — Feature Selection)

```r
tune_splsda <- tune.splsda(as.matrix(data), groups, ncomp = 3,
                            validation = 'Mfold', folds = 5, nrepeat = 50,
                            test.keepX = c(5, 10, 20, 50, 100))
optimal_keepX <- tune_splsda$choice.keepX

splsda_result <- splsda(as.matrix(data), groups, ncomp = ncomp_opt, keepX = optimal_keepX)
selected_features <- selectVar(splsda_result, comp = 1)$name
```

### OPLS-DA (ropls)

```r
library(ropls)

oplsda <- opls(data, groups, predI = 1, orthoI = NA)
plot(oplsda, typeVc = 'x-score')  # Scores plot
plot(oplsda, typeVc = 'x-loading')  # S-plot

vip_scores <- getVipVn(oplsda)
top_vip <- sort(vip_scores, decreasing = TRUE)[1:20]
```

### Random Forest Feature Importance

```r
library(randomForest)

rf_model <- randomForest(x = data, y = groups, importance = TRUE, ntree = 500)
importance <- importance(rf_model)
top_features <- rownames(importance)[order(importance[, 'MeanDecreaseAccuracy'], decreasing = TRUE)[1:20]]
varImpPlot(rf_model, n.var = 20)
```

### ROC Analysis (pROC)

```r
library(pROC)

top_feature <- 'feature_123'
roc_result <- roc(groups, data[, top_feature])
plot(roc_result, main = paste('AUC =', round(auc(roc_result), 3)))
```

### Heatmap

```r
library(pheatmap)

top_features <- rownames(sig_features)[1:50]
annotation_row <- data.frame(Group = groups)
rownames(annotation_row) <- rownames(data)

pheatmap(t(data[, top_features]), annotation_col = annotation_row,
         scale = 'row', clustering_method = 'ward.D2')
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `ttest` | Statistical test method |
| `--fdr-cutoff` | `0.05` | FDR significance threshold |
| `--fc-cutoff` | `1.0` | Log2FC threshold |
| `--multivariate` | `pca` | pca, plsda, oplsda, splsda |

## Why This Exists

- **Without it**: Complex metabolomic variance is hard to parse; minor batch effects can mimic true biological signal
- **With it**: Powerful multivariate (PLS-DA) and univariate testing models separate true biomarkers from noise
- **Why OmicsClaw**: Automates strict R-based multidimensional workflows with single Python calls

## Workflow

1. **Calculate**: Log transformations and scaling.
2. **Execute**: Run PCA/OPLS-DA and extract variable importance (VIP) scores.
3. **Assess**: Execute parallel univariate FDR-corrected models.
4. **Generate**: Output candidate biomarker lists.
5. **Report**: Synthesize VIP plots, score plots, and hierarchical heatmaps.

## Example Queries

- "Run PLS-DA and find significant metabolites"
- "Perform differential analysis on this normalized metabolomics matrix"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── statistics.csv
├── figures/
│   ├── plsda_scores.png
│   ├── vip_plot.png
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
- `met-normalize` — Upstream data scaling
- `met-annotate` — Downstream identification of biomarkers

## Version Compatibility

Reference examples tested with: mixOmics 6.24+, ropls 1.32+

## Dependencies

**Required**: numpy, pandas, scipy, scikit-learn
**Optional**: mixOmics (R), ropls (R), randomForest (R), pROC (R), pheatmap (R)

## Citations

- [mixOmics](https://doi.org/10.1371/journal.pcbi.1005752) — Rohart et al., PLoS Computational Biology 2017
- [ropls](https://doi.org/10.1021/acs.jproteome.5b00354) — Thévenot et al., Journal of Proteome Research 2015
- [MetaboAnalyst](https://doi.org/10.1093/nar/gkab382) — Pang et al., Nucleic Acids Research 2021

## Related Skills

- `met-normalize` — Data normalization before analysis
- `met-pathway` — Pathway enrichment of significant metabolites
- `xcms-preprocess` — Feature extraction upstream
