# Data Preprocessing Guide for Disease Progression Analysis

## Overview

This guide provides detailed recommendations for preprocessing different omics data types before trajectory analysis.

---

## Normalization Methods by Data Type

### RNA-seq (Bulk Transcriptomics)

**Recommended normalization:** log2(CPM + 1)

**Method:**
```python
# Calculate counts per million (CPM)
library_sizes = data.sum(axis=0)
cpm = data.div(library_sizes, axis=1) * 1e6

# Log transform
data_norm = np.log2(cpm + 1)
```

**Alternative:** Variance-stabilizing transformation (VST)
- Use DESeq2's `vst()` in R for true VST
- Provides better variance stability across expression range

**When to use:**
- CPM: Standard normalization, works well for most cases
- VST: When variance heterogeneity is an issue, better for low counts

---

### Proteomics

**Recommended normalization:** log2 + quantile normalization

**Method:**
```python
# Log2 transform
data_log = np.log2(data + 1)

# Quantile normalization
from sklearn.preprocessing import QuantileTransformer
qt = QuantileTransformer(output_distribution='normal')
data_norm = pd.DataFrame(
    qt.fit_transform(data_log.T).T,
    index=data_log.index,
    columns=data_log.columns
)
```

**Why:**
- Log2: Stabilizes variance, makes fold changes symmetric
- Quantile: Equalizes distributions across samples
- Handles missing values better than some alternatives

---

### Metabolomics

**Recommended normalization:** log transformation + scaling

**Method:**
```python
# Log transform (handle zeros)
data_log = np.log(data + 1)  # Natural log or log10

# Scale per feature
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()
data_norm = pd.DataFrame(
    scaler.fit_transform(data_log.T).T,
    index=data_log.index,
    columns=data_log.columns
)
```

**Additional considerations:**
- **Metabolite-specific scaling:** Each metabolite to mean=0, sd=1
- **Sample normalization:** May need to correct for dilution effects
- **Missing values:** Common in metabolomics, use imputation carefully

---

### Clinical Biomarkers

**Recommended normalization:** Z-score per feature

**Method:**
```python
# Z-score normalization
from sklearn.preprocessing import StandardScaler
scaler = StandardScaler()

data_norm = pd.DataFrame(
    scaler.fit_transform(data.T).T,
    index=data.index,
    columns=data.columns
)
```

**Why:**
- Puts all biomarkers on same scale (essential when mixing lab values)
- Preserves relative changes within each biomarker
- Interpretable: values are standard deviations from mean

**Caution:**
- Don't z-score categorical variables
- Be aware of outliers (consider robust scaling)

---

## Feature Filtering

### Low Variance Filtering

**Purpose:** Remove features with little information content

**Method:**
```python
# Calculate variance per feature
variances = data.var(axis=1)
median_var = variances.median()

# Keep features with variance > threshold * median
threshold = 0.1
keep = variances > (threshold * median_var)

data_filtered = data.loc[keep]
```

**Recommended thresholds:**
- **Conservative:** 0.1 (keeps ~80-90% of features)
- **Moderate:** 0.2 (keeps ~60-70%)
- **Aggressive:** 0.5 (keeps ~40-50%)

**When to use:**
- Always recommended before trajectory analysis
- Especially important for large feature sets (>10,000)
- Reduces noise and computational cost

---

### Top Variable Features

**Purpose:** Select most informative features for trajectory

**Method:**
```python
# By variance
variances = data.var(axis=1)
top_features = variances.nlargest(5000).index
data_hvf = data.loc[top_features]

# By MAD (median absolute deviation) - more robust
mad = data.sub(data.median(axis=1), axis=0).abs().median(axis=1)
top_features = mad.nlargest(5000).index

# By coefficient of variation
cv = data.std(axis=1) / data.mean(axis=1).abs()
top_features = cv.nlargest(5000).index
```

**Recommended number of features:**
- **Small datasets (<50 samples):** 2,000-3,000 features
- **Medium datasets (50-200 samples):** 3,000-5,000 features
- **Large datasets (>200 samples):** 5,000-10,000 features

---

## Batch Correction

### When to Apply Batch Correction

**Apply if:**
- ✅ Samples processed in multiple batches
- ✅ Sequencing runs differ
- ✅ PCA shows clustering by batch
- ✅ Different sites/labs

**Don't apply if:**
- ❌ Batch confounded with biology (batch = disease stage)
- ❌ Only one batch
- ❌ Batch effects are minimal

---

### Method 1: ComBat (Recommended)

**Installation:**
```bash
pip install combat
```

**Usage:**
```python
from combat.pycombat import pycombat

# Prepare batch vector
batch = metadata.set_index('sample_id').loc[data.columns, 'batch']

# Run ComBat
data_corrected = pycombat(data, batch)
data_corrected = pd.DataFrame(data_corrected, index=data.index, columns=data.columns)
```

**Pros:**
- Gold standard for batch correction
- Preserves biological variation
- Works well with small batches

**Cons:**
- Can be slow for large datasets
- Requires knowing batch structure

---

### Method 2: Simple Mean Centering (Fallback)

**Usage:**
```python
batch = metadata.set_index('sample_id').loc[data.columns, 'batch']
data_corrected = data.copy()

for batch_id in batch.unique():
    batch_mask = (batch == batch_id).values
    batch_mean = data.loc[:, batch_mask].mean(axis=1)
    overall_mean = data.mean(axis=1)

    # Center batch to overall mean
    data_corrected.loc[:, batch_mask] = (
        data.loc[:, batch_mask].sub(batch_mean, axis=0).add(overall_mean, axis=0)
    )
```

**When to use:**
- ComBat not available
- Quick exploratory analysis
- As a sanity check

---

## Missing Value Handling

### Strategy Selection

**Drop features (recommended if <10% missing):**
```python
missing_per_feature = data.isna().sum(axis=1) / data.shape[1]
keep_features = missing_per_feature < 0.1
data_clean = data.loc[keep_features]
```

**Drop samples (if few samples affected):**
```python
missing_per_sample = data.isna().sum(axis=0) / data.shape[0]
keep_samples = missing_per_sample < 0.2
data_clean = data.loc[:, keep_samples]
```

**Median imputation (simple):**
```python
data_imputed = data.apply(lambda x: x.fillna(x.median()), axis=1)
```

**KNN imputation (better):**
```python
from sklearn.impute import KNNImputer

imputer = KNNImputer(n_neighbors=5)
data_imputed = pd.DataFrame(
    imputer.fit_transform(data.T).T,
    index=data.index,
    columns=data.columns
)
```

---

## Quality Control Checks

### Pre-processing QC

**Check 1: Distribution visualization**
```python
import matplotlib.pyplot as plt
import seaborn as sns

# Before normalization
plt.figure(figsize=(10, 4))
plt.subplot(1, 2, 1)
data.iloc[:, 0].hist(bins=50)
plt.title('Before normalization')

# After normalization
plt.subplot(1, 2, 2)
data_norm.iloc[:, 0].hist(bins=50)
plt.title('After normalization')
plt.show()
```

**Check 2: Sample correlation**
```python
# Samples should correlate well
import seaborn as sns

correlation_matrix = data_norm.T.corr()
sns.clustermap(correlation_matrix, cmap='RdBu_r', center=0,
               figsize=(10, 10), cbar_kws={'label': 'Correlation'})
```

**Check 3: Batch effects**
```python
from sklearn.decomposition import PCA

pca = PCA(n_components=2)
coords = pca.fit_transform(data_norm.T)

plt.scatter(coords[:, 0], coords[:, 1],
           c=metadata['batch'].astype('category').cat.codes)
plt.xlabel(f'PC1 ({pca.explained_variance_ratio_[0]*100:.1f}%)')
plt.ylabel(f'PC2 ({pca.explained_variance_ratio_[1]*100:.1f}%)')
plt.title('Check for Batch Effects')
plt.colorbar(label='Batch')
plt.show()
```

---

## Preprocessing Workflow Template

### Complete Pipeline

```python
from scripts.preprocess_features import (
    preprocess_omics,
    select_variable_features
)

# Step 1: Normalize
data_norm = preprocess_omics(
    data,
    metadata,
    data_type='rnaseq',           # Choose your data type
    normalization='log_cpm',       # Choose appropriate method
    batch_correction=True,
    batch_column='batch',
    filter_low_variance=True,
    variance_threshold=0.1,
    handle_missing='drop'          # Or 'impute'
)

# Step 2: Select variable features
data_processed = select_variable_features(
    data_norm,
    n_features=5000,
    method='variance'
)

# Step 3: Visual QC
# ... run QC checks above ...

# Ready for trajectory analysis!
```

---

## Troubleshooting

### Issue: Features have very different scales

**Symptom:** Some features dominate (e.g., ribosomal genes in RNA-seq)

**Solution:**
1. Ensure proper normalization
2. Consider robust scaling instead of standard scaling
3. Remove problematic feature classes before analysis

---

### Issue: Batch correction removes biological signal

**Symptom:** No trajectory detected after batch correction

**Solution:**
1. Check if batch is confounded with biology
2. Use `preserve_biology=True` in ComBat
3. Try weaker batch correction (mean centering)
4. If batch = disease stage, don't correct (model batch instead)

---

### Issue: Too many features after filtering

**Symptom:** Analysis is very slow or runs out of memory

**Solution:**
1. Reduce to top 3,000-5,000 variable features
2. Increase variance threshold for filtering
3. Consider dimensionality reduction (PCA)

---

### Issue: High missing rate after filtering

**Symptom:** Lost too many features (>50%)

**Solution:**
1. Relax filtering thresholds
2. Use imputation instead of dropping
3. Consider if missing is informative (MNAR vs MAR)

---

## References

1. **ComBat:** Johnson WE, et al. Adjusting batch effects in microarray expression data using empirical Bayes methods. *Biostatistics*. 2007;8(1):118-127.

2. **VST:** Anders S, Huber W. Differential expression analysis for sequence count data. *Genome Biol*. 2010;11:R106.

3. **Quantile normalization:** Bolstad BM, et al. A comparison of normalization methods for high density oligonucleotide array data. *Bioinformatics*. 2003;19(2):185-193.

4. **Missing value imputation:** Troyanskaya O, et al. Missing value estimation methods for DNA microarrays. *Bioinformatics*. 2001;17(6):520-525.

---

**Last Updated:** 2026-01-28
