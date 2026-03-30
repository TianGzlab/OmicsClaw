# Proteomics DE Analysis Reference (limma + DEqMS)

Detailed documentation for the proteomics differential expression pipeline.

## Pipeline Overview

```
PSM-level data → medianSweeping → protein matrix → filter → impute → normalize → limma → DEqMS → results
```

## DEqMS vs Standard limma

**Why DEqMS?** Standard limma assumes equal variance across all proteins. In mass spectrometry data, proteins with more PSMs have more accurate quantification (lower variance). DEqMS models this relationship explicitly.

- `eBayes()` — standard limma empirical Bayes, same prior for all proteins
- `spectraCounteBayes()` — DEqMS extension, models prior variance as function of PSM count
- **Result:** Better calibrated p-values, more power for well-measured proteins, fewer false positives for poorly measured proteins

**Key columns in DEqMS results:**
- `logFC` — log2 fold change (same as limma)
- `adj.P.Val` — standard limma BH-adjusted p-value
- `sca.adj.pval` — DEqMS spectra-count-adjusted p-value (USE THIS)
- `sca.t` — DEqMS moderated t-statistic
- `count` — PSM count used for variance estimation

## PSM-to-Protein Aggregation

`medianSweeping()` from DEqMS:
1. For each PSM, compute log2 intensity across samples
2. Subtract row median (spectrum-level centering)
3. For each protein, take median across all its PSMs
4. Result: protein-level log2 ratios (relative abundances)

**When to use:** PSM-level input (recommended for full DEqMS workflow)
**Alternative:** If you already have protein-level intensities, skip this step and provide `protein_matrix` directly

## Design Matrix Construction

**Simple two-group comparison:**
```r
design <- model.matrix(~0 + condition, data = metadata)
colnames(design) <- gsub("^condition", "", colnames(design))
contrast <- makeContrasts("Treatment-Control", levels = design)
```

**Multiple comparisons:**
```r
contrasts <- makeContrasts(
    "miR372-ctrl",
    "miR519-ctrl",
    "miR191-ctrl",
    levels = design
)
# Extract specific comparison: coef_col = 1, 2, or 3
```

**Paired design (e.g., patient-matched):**
```r
design <- model.matrix(~0 + condition + patient, data = metadata)
```

**Batch correction:**
```r
design <- model.matrix(~0 + condition + batch, data = metadata)
```

## Missing Value Handling

### Filtering Strategy

Remove proteins with excessive missingness. Default: >50% missing in ALL conditions.

**Rationale:** A protein present in one condition but absent in another may be biologically meaningful (condition-specific expression). Only remove proteins with pervasive missingness.

### Imputation Methods

**MinProb (default — for MNAR):**
- Assumes missing values are low-abundance (Missing Not At Random)
- Draws from left tail of observed distribution
- `rnorm(n, mean = quantile(observed, 0.01), sd = 0.3 * sd(observed))`
- Best for: TMT/LFQ data where missingness correlates with low abundance

**kNN (for MAR):**
- Uses k nearest neighbors to estimate missing values
- Better when missingness is random (e.g., technical dropouts)
- Requires `impute` Bioconductor package

**Decision guide:** See [normalization-guide.md](normalization-guide.md)

## Normalization Methods

**Median centering (default):**
- Subtract column median from each sample
- Assumes most proteins are not changing
- Works well for most TMT and LFQ experiments

**Quantile normalization:**
- Forces all samples to have identical intensity distributions
- More aggressive; use when large systematic biases exist

**VSN (Variance Stabilizing Normalization):**
- Stabilizes variance across the intensity range
- Requires `vsn` Bioconductor package

## TMT vs LFQ Considerations

| Feature | TMT | LFQ |
|---------|-----|-----|
| Missing values | Fewer (~5-15%) | More (~20-50%) |
| Missingness pattern | More MCAR | More MNAR |
| Recommended imputation | MinProb or kNN | MinProb |
| Normalization | Median or quantile | Median |
| PSM counts | From search engine | From MaxQuant |
| medianSweeping | Yes (TMT ratios) | Optional (raw intensities) |

## Interpreting Results

**Significance thresholds:**
- Standard: sca.adj.pval < 0.05, |logFC| > 0.58 (1.5-fold change)
- Relaxed: sca.adj.pval < 0.1, |logFC| > 0 (any fold change)
- Stringent: sca.adj.pval < 0.01, |logFC| > 1 (2-fold change)

**DEqMS vs limma p-values:**
- Compare `sca.adj.pval` vs `adj.P.Val` to see DEqMS correction effect
- Proteins with low PSM counts will have less significant DEqMS p-values
- Proteins with high PSM counts may gain significance

## User Data Format

**MaxQuant proteinGroups.txt:**
```r
data <- read.delim("proteinGroups.txt")
# Intensity columns: "Intensity.SampleName"
# PSM counts: "MS.MS.Count" or "Peptides" column
```

**Proteome Discoverer:**
```r
data <- read.delim("proteins.txt")
# Abundance columns vary by PD version
```

**Generic CSV:**
```r
data <- read.csv("protein_intensities.csv", row.names = 1)
# Rows = proteins, Columns = samples
# Provide metadata separately
```


---
