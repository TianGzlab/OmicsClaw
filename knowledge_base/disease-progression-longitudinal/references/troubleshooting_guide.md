# Disease Progression Longitudinal Analysis - Troubleshooting Guide

## Common Issues and Solutions

### Installation and Environment

#### Issue: TimeAx not available
```
R TimeAx not available: TimeAx R package not installed
```

**Solution:** TimeAx is an R package. Install R and the TimeAx package:
```r
install.packages("remotes")
remotes::install_github("amitfrish/TimeAx")
```

**Alternative:** Use LMM or HMM methods if TimeAx installation fails.

---

### Data Loading

#### Issue: Sample IDs don't match between data and metadata
```
ValueError: Sample IDs in metadata don't match data columns
```

**Causes:**
- Column names in data file don't match sample_id in metadata
- Extra/missing samples in one file

**Solutions:**
1. Check column headers in data file
2. Ensure metadata sample_id matches exactly (case-sensitive)
3. Use data loading function with correct sample identifier:
```python
# Ensure sample_id column in metadata matches data columns
metadata['sample_id'] = data.columns
```

#### Issue: Missing required metadata columns
```
ValueError: Metadata missing required columns
```

**Solution:** Metadata must have:
- `sample_id`: Unique sample identifier
- `patient_id`: Patient identifier (for grouping)
- `timepoint`: Numeric time value

---

### Timepoint Validation

#### Issue: Insufficient patients
```
ValueError: Insufficient patients: 5 < 10 required
```

**Causes:**
- Too few patients in dataset
- TimeAx requires ≥10 patients (20+ recommended)

**Solutions:**
1. Combine data from multiple cohorts
2. Use LMM method (works with fewer patients)
3. If <10 patients, consider per-patient analysis instead

#### Issue: Too few timepoints per patient
```
WARNING: X patients have <3 timepoints
```

**Solutions:**
1. Remove patients with <3 timepoints:
```python
from scripts.load_longitudinal_data import filter_patients_by_timepoints
metadata = filter_patients_by_timepoints(metadata, min_timepoints=3)
data = data[metadata['sample_id']]
```
2. Accept warning if most patients have sufficient timepoints

---

### TimeAx Analysis

#### Issue: Low robustness score (<0.5)
```
Robustness score: 0.35
⚠ Low quality trajectory
```

**Causes:**
- Weak temporal signal in data
- Strong batch effects
- Insufficient patients/timepoints
- Noisy data

**Solutions:**
1. **Check batch effects:**
```python
import seaborn as sns
import matplotlib.pyplot as plt

# PCA colored by batch
from sklearn.decomposition import PCA
pca = PCA(n_components=2)
coords = pca.fit_transform(data.T)

plt.scatter(coords[:, 0], coords[:, 1], c=metadata['batch'])
plt.xlabel('PC1')
plt.ylabel('PC2')
plt.title('Check for Batch Effects')
plt.show()
```

2. **Apply batch correction:**
```python
data_corrected = preprocess_omics(
    data, metadata,
    batch_correction=True,
    batch_column='batch'
)
```

3. **Increase feature selection stringency:**
```python
# Use only highly variable features
data_hvf = select_variable_features(data, n_features=3000, method='variance')
```

4. **Try alternative normalization:**
```python
# Instead of log_cpm, try quantile normalization
data_norm = preprocess_omics(data, metadata, normalization='quantile')
```

5. **Increase sample size** if possible

#### Issue: Pseudotime doesn't correlate with clinical stages
```
Pseudotime vs clinical stage: r=0.15, p=0.45
```

**Causes:**
- Clinical stages may not reflect continuous biology
- Batch effects dominating signal
- Wrong trajectory (e.g., treatment response, not disease stage)

**Solutions:**
1. **Check if clinical stages are ordinal:**
   - Some staging systems aren't truly progressive
   - Pseudotime captures continuous biology, not discrete categories

2. **Stratify by subtype:**
```python
# Run separately for each disease subtype
for subtype in metadata['subtype'].unique():
    subtype_data = data[metadata['subtype'] == subtype]
    subtype_meta = metadata[metadata['subtype'] == subtype]
    # Run TimeAx on each subtype
```

3. **Validate with alternative measures:**
   - Check correlation with quantitative clinical scores
   - Test association with outcomes (survival, response)

#### Issue: High uncertainty scores for all samples
```
Mean uncertainty: 0.85 (should be <0.5)
```

**Causes:**
- Trajectory model is unstable
- Ambiguous sample positioning

**Solutions:**
1. Check robustness score (if <0.5, trajectory unreliable)
2. Increase n_iterations:
```python
model, results = run_timeax_alignment(
    data, metadata,
    n_iterations=200  # Increase from 100
)
```
3. Consider alternative method (LMM, HMM)

#### Issue: Seed features don't make biological sense
```
Top seeds: RPL3, RPS5, MT-CO1...
```

**Causes:**
- Technical artifacts (ribosomal, mitochondrial genes)
- Batch effects
- Wrong normalization

**Solutions:**
1. **Exclude artifact genes:**
```python
# Remove ribosomal and mitochondrial genes
exclude_patterns = ['RPL', 'RPS', 'MT-']
feature_mask = ~data.index.str.startswith(tuple(exclude_patterns))
data_clean = data.loc[feature_mask]
```

2. **Check normalization:**
   - Ensure proper normalization for your data type
   - RNA-seq: log2(CPM+1) or VST
   - Proteomics: log2 + quantile

---

### Visualization

#### Issue: Memory error during plotting
```
MemoryError: Unable to allocate array
```

**Solutions:**
1. Reduce to most variable features before plotting
2. Use PCA instead of UMAP (faster, less memory)
3. Sample subset of cells for visualization

#### Issue: Plots show clustering by batch, not time
```
PCA separates by batch, not pseudotime
```

**Solution:** Apply batch correction before analysis:
```python
data_corrected = preprocess_omics(
    data, metadata,
    batch_correction=True,
    batch_column='batch'
)
```

---

### Alternative Methods

#### Issue: TimeAx R installation fails

**Solution:** Use Linear Mixed Models instead:
```python
from scripts.lmm_trajectory import fit_lmm_trajectories

lmm_results = fit_lmm_trajectories(
    data, metadata,
    time_column='timepoint',
    patient_column='patient_id'
)
```

#### Issue: Need discrete disease states

**Solution:** Use Hidden Markov Models:
```python
from scripts.hmm_states import fit_hmm_model

hmm_model, states = fit_hmm_model(
    data, metadata,
    n_states=3,  # Early, Intermediate, Late
    state_names=['Early', 'Intermediate', 'Late']
)
```

---

### Performance Issues

#### Issue: Analysis is very slow
```
TimeAx running for >30 minutes
```

**Solutions:**
1. **Reduce features:**
```python
data_reduced = select_variable_features(data, n_features=2000)
```

2. **Reduce iterations:**
```python
model, results = run_timeax_alignment(
    data, metadata,
    n_iterations=50  # Reduce from 100
)
```

3. **Use fewer seeds:**
```python
model, results = run_timeax_alignment(
    data, metadata,
    n_seeds=30  # Reduce from 50
)
```

---

### Missing Data

#### Issue: Many missing values
```
WARNING: 25% missing values in data
```

**Solutions:**
1. **Drop features with >20% missing:**
```python
missing_per_feature = data.isna().sum(axis=1) / data.shape[1]
keep_features = missing_per_feature < 0.2
data_clean = data.loc[keep_features]
```

2. **Impute missing values:**
```python
data_imputed = preprocess_omics(
    data, metadata,
    handle_missing='impute'  # Use median imputation
)
```

---

## Getting Help

If you continue to have issues:

1. Check TimeAx documentation: [https://github.com/amitfrish/TimeAx](https://github.com/amitfrish/TimeAx)
2. Review TimeAx paper methods: Frishberg et al., Nat Commun 2023
3. Consult [timeax_methodology.md](timeax_methodology.md) for algorithm details
4. Try alternative methods (LMM, HMM) if TimeAx isn't suitable

---

**Last Updated:** 2026-01-28
