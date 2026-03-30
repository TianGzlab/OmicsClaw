# Normalization and Imputation Guide

Decision guide for choosing normalization and missing value imputation methods in proteomics DE analysis.

## Normalization Decision Tree

```
Is there large systematic bias between samples?
├── Yes → Are distributions very different shapes?
│   ├── Yes → Quantile normalization
│   └── No → Median centering
└── No → Is variance intensity-dependent?
    ├── Yes → VSN
    └── No → Median centering (default)
```

### Median Centering (Default)

**When to use:** Most experiments. Safe default.
- Subtracts column median from each sample
- Assumes majority of proteins unchanged between conditions
- Preserves distribution shape

```r
normalization_method <- "median"
```

### Quantile Normalization

**When to use:** Large batch effects, very different sample distributions.
- Forces all samples to identical distributions
- More aggressive — may remove real biological variation
- Good for multi-batch TMT experiments

```r
normalization_method <- "quantile"
```

### VSN (Variance Stabilizing)

**When to use:** Variance increases with intensity (heteroscedastic).
- Transforms data to stabilize variance
- Requires `vsn` package
- Particularly useful for LFQ data

```r
normalization_method <- "vsn"  # Not yet implemented in basic_workflow.R
```

## Missing Value Imputation Decision Tree

```
What is the likely cause of missingness?
├── Low abundance (protein below detection limit)
│   └── MinProb (MNAR assumption)
├── Random technical failure
│   └── kNN (MAR assumption)
└── Unknown
    └── MinProb (safer default for MS data)
```

### MinProb (Default)

**Assumption:** Missing Not At Random (MNAR) — missing because below detection limit.
**Method:** Draw from low-intensity tail of observed distribution.
**Best for:** TMT and LFQ data where missingness correlates with low abundance.

```r
imputation_method <- "MinProb"
```

### kNN

**Assumption:** Missing At Random (MAR) — missingness unrelated to abundance.
**Method:** Estimate from k nearest neighbors in feature space.
**Best for:** Random technical dropouts, samples with isolated missing values.

```r
imputation_method <- "kNN"
```

## Pre-filtering Strategy

Before imputation, filter proteins with excessive missingness:

| Filter | When to Use |
|--------|-------------|
| >50% missing in ALL conditions | Default — keeps condition-specific proteins |
| >30% missing in ANY condition | Stringent — for high-quality quantification |
| No filter | When missingness itself is of interest |

## Quality Checks

After normalization, verify with:
1. **Intensity distribution plot** — samples should have similar medians/spreads
2. **PCA** — samples should cluster by condition, not by batch
3. **Sample correlation** — within-condition correlation > between-condition

If PCA shows batch clustering after normalization, consider:
- Adding batch to the limma design matrix
- More aggressive normalization (quantile)
- ComBat batch correction (sva package)
