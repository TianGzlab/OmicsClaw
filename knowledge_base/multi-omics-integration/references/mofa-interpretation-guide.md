# MOFA+ Factor Interpretation Guide

## Understanding MOFA Factors

Each MOFA factor captures an independent axis of variation in the multi-omics data. Factors are ordered by total variance explained (Factor 1 explains the most).

### Shared vs View-Specific Factors

- **Shared factor:** Explains variance in 2+ views. Indicates coordinated biology across omics layers (e.g., a mutation driving both gene expression and drug response changes).
- **View-specific factor:** Explains variance in only 1 view. May indicate technical variation or biology unique to that measurement type.

### Interpreting Variance Decomposition

The variance decomposition heatmap (R² per factor per view) is the most informative MOFA output:

| R² (%) | Interpretation |
|--------|---------------|
| >10% | Major source of variation in that view |
| 5-10% | Moderate signal |
| 1-5% | Minor but potentially meaningful |
| <1% | Factor not active in this view |

**Total R² per view:** How much of each view's variance MOFA captured overall. Low values (<20%) suggest important variation not captured — consider more factors or different feature selection.

## Downstream Analysis with Factor Scores

### Patient Stratification

Factor scores can be used as low-dimensional representations for clustering:

```r
# Extract factor scores
factors <- get_factors(model)[[1]]  # matrix: samples x factors

# K-means on top factors
set.seed(42)
km <- kmeans(factors[, 1:5], centers = 3)
clusters <- km$cluster
```

### Survival Analysis

Test whether factors associate with clinical outcomes:

```r
# Cox regression with factor scores
library(survival)
surv_data <- merge(as.data.frame(factors), clinical_data, by = "sample")
cox_fit <- coxph(Surv(time, event) ~ Factor1 + Factor2 + Factor3, data = surv_data)
summary(cox_fit)
```

### Pathway Enrichment on Factor Weights

For each factor, extract top-weighted genes and run enrichment:

```r
# Get weights for mRNA view
weights <- get_weights(model, views = "mRNA", as.data.frame = TRUE)

# Top genes for Factor 1
w_f1 <- weights[weights$factor == "Factor1", ]
top_genes <- w_f1$feature[order(abs(w_f1$value), decreasing = TRUE)][1:200]

# Use with functional-enrichment-from-degs skill
# or clusterProfiler directly
```

### Data Imputation

MOFA can impute missing values using the learned factor model:

```r
imputed <- impute(model, views = "all")
# Returns complete matrices for all views
```

## CLL Dataset: Known Biology

The CLL example dataset has well-characterized factor structure:

- **Factor 1:** Driven by IGHV mutation status — the strongest source of variation in CLL. Active in mRNA, methylation, and drug response. Separates patients into two major clinical subtypes.
- **Factor 2:** Captures trisomy 12 (chromosome 12 gain). Active primarily in mRNA and methylation.
- **Factor 3:** Associated with drug response heterogeneity beyond IGHV status.

These factors recapitulate known CLL biology, validating the MOFA approach.

## Choosing Number of Factors

| Guideline | Recommendation |
|-----------|---------------|
| Starting point | 15 factors (MOFA auto-drops inactive ones) |
| Small dataset (<50 samples) | 5-10 factors |
| Large dataset (>500 samples) | 15-25 factors |
| Many views (>5) | Increase factors proportionally |

MOFA automatically removes factors that explain <1% variance, so over-specifying is safer than under-specifying.

## Common Pitfalls

1. **Unscaled views:** Always use `scale_views = TRUE` when views have different magnitudes (e.g., RNA counts vs methylation beta values). Without scaling, high-variance views dominate.

2. **Binary data misspecified:** Somatic mutation data (0/1) must use Bernoulli likelihood, not Gaussian. The workflow auto-detects this.

3. **Too few overlapping samples:** While MOFA handles missing data, factors are most reliable when estimated from many samples. Aim for >50% overlap between any two views.

4. **Ignoring factor correlations:** By design, MOFA factors should be uncorrelated. High correlation (|r| > 0.3) in the correlation plot suggests the model may not have converged. Re-run with `convergence_mode = "slow"`.

5. **Over-interpreting low-R² factors:** Factors explaining <1% total variance are likely noise. Focus interpretation on factors with clear variance signal.

## References

- Argelaguet R, et al. (2020) MOFA+: a statistical framework for comprehensive integration of multi-modal single-cell data. *Genome Biology* 21:111.
- MOFA2 tutorials: https://biofam.github.io/MOFA2/tutorials.html
- MOFA2 downstream analysis vignette: https://www.bioconductor.org/packages/release/bioc/vignettes/MOFA2/inst/doc/downstream_analysis.html


---
