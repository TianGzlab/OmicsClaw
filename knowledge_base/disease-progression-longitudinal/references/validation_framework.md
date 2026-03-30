# Validation Framework for Disease Progression Trajectories

This document provides comprehensive quality control guidelines and validation strategies for trajectory analysis.

---

## Data Quality Requirements

### Minimum Sample Size Requirements

**Absolute minimums (trajectory may be unstable):**
- ✅ **≥10 patients** (20+ strongly recommended)
- ✅ **≥3 timepoints per patient** (5+ recommended for robust trajectories)
- ✅ **≥30 total samples** (50+ recommended)

**Recommended for high-quality trajectories:**
- ✅ **20-50 patients:** Good statistical power, stable trajectories
- ✅ **5-10 timepoints per patient:** Captures progression dynamics
- ✅ **100-500 total samples:** Robust feature identification

**Warning thresholds:**
- ⚠️ **<10 patients:** Trajectory may be unstable, high variance
- ⚠️ **<3 timepoints per patient:** Insufficient temporal resolution
- ⚠️ **<30 total samples:** Underpowered for feature discovery

### Data Quality Metrics

**Technical quality requirements:**
- ✅ **High-quality omics data:** Low technical variation, proper QC passed
- ✅ **Consistent sample processing:** Same protocol across all timepoints
- ✅ **Batch effect assessment:** Check for batch confounding with time
- ✅ **Low missingness:** <10% missing values per feature recommended

**Pre-analysis quality checks:**

1. **Check sequencing/assay quality:**
   ```python
   # For RNA-seq: check alignment rate, gene detection
   alignment_rate = data.sum(axis=0) > 1e6  # Total reads > 1M
   gene_detection = (data > 0).sum(axis=1) > 10  # Gene detected in >10 samples
   ```

2. **Assess batch effects:**
   ```python
   # PCA colored by batch vs. timepoint
   from sklearn.decomposition import PCA
   pca = PCA(n_components=2)
   pcs = pca.fit_transform(data.T)

   # If samples cluster by batch (not time), apply batch correction
   ```

3. **Check missingness patterns:**
   ```python
   # Missingness per feature and sample
   missing_per_feature = data.isnull().sum(axis=1) / data.shape[1]
   missing_per_sample = data.isnull().sum(axis=0) / data.shape[0]

   # Remove features/samples with >20% missingness
   ```

---

## Trajectory Quality Metrics

### TimeAx Robustness Score

The robustness score measures trajectory stability across multiple random initializations.

**Interpretation:**
- **>0.7:** High quality, reliable trajectory
  - Strong agreement across runs
  - Confident ordering of samples
  - Proceed with analysis

- **0.5-0.7:** Moderate quality, interpret cautiously
  - Some variability in sample ordering
  - Check for batch effects or outliers
  - Consider increasing n_iterations or n_seeds

- **<0.5:** Poor quality, consider alternative methods
  - Unstable trajectory, high variance
  - May indicate noisy data or no clear progression
  - Try batch correction, feature filtering, or alternative method

**Improving robustness:**

```python
# If robustness is low, try:

# 1. Increase iterations and seeds
timeax_model, results = run_timeax_alignment(
    data, metadata,
    n_iterations=200,    # Default: 100
    n_seeds=100          # Default: 50
)

# 2. Filter to more variable features
from sklearn.feature_selection import VarianceThreshold
selector = VarianceThreshold(threshold=0.5)  # Keep top 50% variable
data_filtered = selector.fit_transform(data.T).T

# 3. Check and correct batch effects
from combat import combat
data_corrected = combat(data, metadata['batch'])
```

### Cross-Validation Approaches

#### 1. Leave-One-Patient-Out (LOPO)

Test trajectory stability when excluding individual patients:

```python
from scripts.timeax_alignment import run_timeax_alignment
import numpy as np

def leave_one_patient_out_cv(data, metadata):
    """Test trajectory stability across patient subsets."""
    patients = metadata['patient_id'].unique()
    pseudotimes = []

    for patient in patients:
        # Hold out one patient
        train_mask = metadata['patient_id'] != patient
        test_mask = metadata['patient_id'] == patient

        # Fit trajectory on training set
        model, results = run_timeax_alignment(
            data[:, train_mask],
            metadata[train_mask]
        )

        # Project held-out patient onto trajectory
        test_pseudotime = model.transform(data[:, test_mask])
        pseudotimes.append(test_pseudotime)

    # Check consistency across folds
    all_pseudotimes = np.concatenate(pseudotimes)
    return all_pseudotimes

# Run LOPO
lopo_pseudotimes = leave_one_patient_out_cv(data, metadata)

# Correlation with full-cohort pseudotime
from scipy.stats import spearmanr
corr, pval = spearmanr(full_pseudotime, lopo_pseudotimes)
print(f"LOPO correlation: r={corr:.3f}, p={pval:.3e}")
# Expected: r > 0.7 for stable trajectories
```

#### 2. Bootstrap Resampling

Test feature selection stability:

```python
def bootstrap_feature_selection(data, metadata, pseudotime, n_bootstrap=100):
    """Assess stability of trajectory-associated features."""
    from scripts.identify_trajectory_features import find_trajectory_features
    import pandas as pd

    feature_counts = {}

    for i in range(n_bootstrap):
        # Resample samples with replacement
        indices = np.random.choice(len(pseudotime), size=len(pseudotime), replace=True)

        # Find trajectory features on bootstrap sample
        boot_features = find_trajectory_features(
            data[:, indices],
            pseudotime[indices],
            fdr_threshold=0.05
        )

        # Count how often each feature is selected
        for feat in boot_features['feature']:
            feature_counts[feat] = feature_counts.get(feat, 0) + 1

    # Features selected in >50% of bootstraps are robust
    robust_features = {k: v for k, v in feature_counts.items() if v > n_bootstrap * 0.5}
    return robust_features

# Run bootstrap
robust_features = bootstrap_feature_selection(data, metadata, pseudotime)
print(f"Robust features: {len(robust_features)} / {data.shape[0]}")
```

#### 3. Independent Cohort Validation

Best validation: replicate trajectory in independent cohort:

```python
# Train on cohort 1
model_cohort1, results1 = run_timeax_alignment(data_cohort1, metadata_cohort1)
pseudotime_cohort1 = results1['pseudotime']

# Project cohort 2 onto cohort 1 trajectory
from scripts.timeax_inference import project_new_samples
pseudotime_cohort2 = project_new_samples(model_cohort1, data_cohort2)

# Validate: check if trajectory features replicate
features_cohort1 = find_trajectory_features(data_cohort1, pseudotime_cohort1)
features_cohort2 = find_trajectory_features(data_cohort2, pseudotime_cohort2)

# Overlap of top 100 features
top100_overlap = len(set(features_cohort1['feature'].head(100)) &
                       set(features_cohort2['feature'].head(100)))
print(f"Top 100 feature overlap: {top100_overlap}%")
# Expected: >30% for replicable trajectories
```

---

## Biological Validation

### 1. Correlation with Clinical Measures

Pseudotime should correlate with established disease markers:

```python
from scipy.stats import spearmanr

# Continuous clinical scores
corr, pval = spearmanr(metadata['pseudotime'], metadata['clinical_severity_score'])
print(f"Pseudotime vs. clinical severity: r={corr:.3f}, p={pval:.3e}")

# Multiple clinical markers
clinical_markers = ['disease_duration', 'symptom_score', 'biomarker_level']
for marker in clinical_markers:
    corr, pval = spearmanr(metadata['pseudotime'], metadata[marker])
    print(f"  {marker}: r={corr:.3f}, p={pval:.3e}")

# Expected: r > 0.4 for moderate agreement, r > 0.6 for strong agreement
```

### 2. Association with Clinical Staging

Compare trajectory pseudotime with discrete clinical stages:

```python
import pandas as pd
from scipy.stats import kruskal

# Compare pseudotime across clinical stages
stage_groups = metadata.groupby('clinical_stage')['pseudotime'].apply(list)

# Kruskal-Wallis test (nonparametric ANOVA)
h_stat, pval = kruskal(*stage_groups)
print(f"Pseudotime differs across stages: H={h_stat:.2f}, p={pval:.3e}")

# Pairwise stage comparisons
from scipy.stats import mannwhitneyu
stages = metadata['clinical_stage'].unique()
for i in range(len(stages)):
    for j in range(i+1, len(stages)):
        u_stat, pval = mannwhitneyu(
            metadata[metadata['clinical_stage'] == stages[i]]['pseudotime'],
            metadata[metadata['clinical_stage'] == stages[j]]['pseudotime']
        )
        print(f"  {stages[i]} vs {stages[j]}: p={pval:.3e}")

# Visualization
from plotnine import ggplot, aes, geom_boxplot, labs
(ggplot(metadata, aes(x='clinical_stage', y='pseudotime', fill='clinical_stage'))
 + geom_boxplot()
 + labs(title='Pseudotime by Clinical Stage', x='Stage', y='Pseudotime')
).save('pseudotime_by_stage.svg', dpi=300)
```

### 3. Survival Analysis

Test if trajectory position predicts clinical outcomes:

```python
from lifelines import CoxPHFitter
from lifelines.statistics import logrank_test

# Cox proportional hazards model: time-to-event ~ pseudotime
cph = CoxPHFitter()
survival_data = metadata[['time_to_event', 'event_occurred', 'pseudotime']]
cph.fit(survival_data, duration_col='time_to_event', event_col='event_occurred')

print("Cox PH Model Results:")
print(cph.summary)
# Hazard ratio for pseudotime should be significant

# Dichotomize by pseudotime median
median_pseudotime = metadata['pseudotime'].median()
metadata['trajectory_group'] = metadata['pseudotime'] > median_pseudotime

# Kaplan-Meier curves by trajectory group
from lifelines import KaplanMeierFitter
kmf = KaplanMeierFitter()

# Plot survival curves
from plotnine import ggplot, aes, geom_step, labs
for group in [True, False]:
    mask = metadata['trajectory_group'] == group
    kmf.fit(metadata[mask]['time_to_event'],
            metadata[mask]['event_occurred'],
            label=f"{'Advanced' if group else 'Early'} progression")

# Log-rank test
early = metadata[metadata['trajectory_group'] == False]
advanced = metadata[metadata['trajectory_group'] == True]
result = logrank_test(
    early['time_to_event'], advanced['time_to_event'],
    early['event_occurred'], advanced['event_occurred']
)
print(f"Log-rank test: p={result.p_value:.3e}")
# Expected: p < 0.05 for significant survival difference
```

### 4. Trajectory Features Make Biological Sense

Manually review top trajectory-associated features:

**Questions to ask:**
- ✅ Do top genes match known disease mechanisms?
- ✅ Are upregulated genes consistent with disease progression?
- ✅ Do gene sets align with biological pathways?
- ✅ Are there known biomarkers in top features?

**Pathway enrichment:**
```python
# Export top features for enrichment analysis
top_features = trajectory_features.nlargest(200, 'correlation')
top_features['feature'].to_csv('trajectory_features_for_enrichment.txt', index=False, header=False)

# Run enrichment analysis (e.g., Enrichr, GSEA, or functional-enrichment-from-degs workflow)
# Expected: enrichment of disease-relevant pathways
```

---

## Statistical Validation

### 1. Multiple Testing Correction

Always use FDR correction for trajectory-associated features:

```python
from statsmodels.stats.multitest import multipletests

# Calculate p-values for all features
from scipy.stats import spearmanr
pvals = []
for feature in data.index:
    corr, pval = spearmanr(data.loc[feature], pseudotime)
    pvals.append(pval)

# FDR correction (Benjamini-Hochberg)
reject, padj, _, _ = multipletests(pvals, alpha=0.05, method='fdr_bh')

# Keep only FDR < 0.05
significant_features = data.index[reject]
print(f"Significant features at FDR<0.05: {len(significant_features)}")
```

### 2. Permutation Testing

Test if trajectory is better than random:

```python
def permutation_test(data, metadata, pseudotime, n_permutations=1000):
    """Test if trajectory is better than random ordering."""

    # Observed: number of significant features
    obs_features = find_trajectory_features(data, pseudotime, fdr_threshold=0.05)
    obs_count = len(obs_features)

    # Null distribution: permute pseudotime
    null_counts = []
    for i in range(n_permutations):
        perm_pseudotime = np.random.permutation(pseudotime)
        perm_features = find_trajectory_features(data, perm_pseudotime, fdr_threshold=0.05)
        null_counts.append(len(perm_features))

    # P-value: fraction of permutations with more features
    pval = (np.array(null_counts) >= obs_count).sum() / n_permutations

    return obs_count, null_counts, pval

obs_count, null_counts, pval = permutation_test(data, metadata, pseudotime)
print(f"Observed features: {obs_count}, Expected: {np.mean(null_counts):.0f}, p={pval:.3f}")
# Expected: p < 0.05 (trajectory better than random)
```

### 3. Effect Size Assessment

Report effect sizes alongside p-values:

```python
# Cohen's d for pseudotime difference between outcome groups
def cohens_d(group1, group2):
    """Calculate Cohen's d effect size."""
    n1, n2 = len(group1), len(group2)
    var1, var2 = np.var(group1, ddof=1), np.var(group2, ddof=1)
    pooled_std = np.sqrt(((n1-1)*var1 + (n2-1)*var2) / (n1+n2-2))
    return (np.mean(group1) - np.mean(group2)) / pooled_std

# Compare pseudotime between outcome groups
responders = metadata[metadata['outcome'] == 'responder']['pseudotime']
non_responders = metadata[metadata['outcome'] == 'non_responder']['pseudotime']

d = cohens_d(responders, non_responders)
print(f"Cohen's d: {d:.2f}")
# Interpretation: 0.2=small, 0.5=medium, 0.8=large effect
```

---

## Common Validation Issues

### Issue 1: Samples Cluster by Batch, Not Trajectory

**Symptom:** PCA colored by batch shows clear clustering

**Diagnosis:**
```python
# Check batch effect strength
from sklearn.decomposition import PCA
pca = PCA(n_components=10)
pcs = pca.fit_transform(data.T)

# ANOVA: PC1 ~ batch
from scipy.stats import f_oneway
batches = metadata['batch'].unique()
batch_groups = [pcs[metadata['batch'] == b, 0] for b in batches]
f_stat, pval = f_oneway(*batch_groups)
print(f"Batch effect on PC1: F={f_stat:.2f}, p={pval:.3e}")
```

**Solution:** Apply batch correction before trajectory analysis
```python
from combat import combat
data_corrected = combat(data, metadata['batch'])
```

### Issue 2: Low Robustness Score (<0.5)

**Possible causes:**
1. Noisy data (high technical variation)
2. No clear progression pattern
3. Too few features selected
4. Batch effects

**Solutions:**
```python
# 1. Filter to more informative features
from sklearn.feature_selection import VarianceThreshold
selector = VarianceThreshold(threshold=0.5)
data_filtered = selector.fit_transform(data.T).T

# 2. Increase TimeAx parameters
model, results = run_timeax_alignment(
    data, metadata,
    n_iterations=200,
    n_seeds=100
)

# 3. Try alternative method (LMM or HMM)
from scripts.lmm_trajectory import fit_lmm_trajectories
lmm_results = fit_lmm_trajectories(data, metadata)
```

### Issue 3: Trajectory Doesn't Match Clinical Expectations

**Example:** Patients expected to progress over time show no pseudotime change

**Diagnosis:**
```python
# Check pseudotime range per patient
pseudotime_range = metadata.groupby('patient_id')['pseudotime'].apply(lambda x: x.max() - x.min())
print(f"Mean pseudotime range per patient: {pseudotime_range.mean():.3f}")
# Low range suggests no progression detected
```

**Possible causes:**
1. Sampling timeframe too short to capture progression
2. Features measured don't reflect disease progression
3. Incorrect normalization

**Solutions:**
- Check that timepoints span sufficient disease progression
- Verify features are relevant to disease (not batch-specific markers)
- Try alternative normalization methods

### Issue 4: Unstable Feature Selection

**Symptom:** Bootstrap analysis shows <30% of features consistently selected

**Diagnosis:**
```python
# Run bootstrap feature selection (see above)
robust_features = bootstrap_feature_selection(data, metadata, pseudotime, n_bootstrap=100)
stability = len(robust_features) / len(trajectory_features)
print(f"Feature stability: {stability:.1%}")
```

**Solutions:**
- Focus on top 50-100 most stable features
- Use ensemble feature selection (combine correlation + GAM + LOESS)
- Increase sample size if possible

---

## Validation Checklist

Before finalizing trajectory analysis, verify:

### Data Quality
- [ ] Sample size meets minimum requirements (≥10 patients, ≥3 timepoints each)
- [ ] Sequencing/assay quality is high (check QC metrics)
- [ ] Batch effects assessed and corrected if needed
- [ ] Missingness is low (<10% per feature)

### Trajectory Quality
- [ ] TimeAx robustness score >0.7 (or justify if lower)
- [ ] Leave-one-patient-out correlation >0.7
- [ ] Bootstrap feature selection shows stability (>30% features consistent)

### Biological Validation
- [ ] Pseudotime correlates with clinical measures (r >0.4)
- [ ] Trajectory stages predict outcomes (survival analysis p<0.05)
- [ ] Top features make biological sense (pathway enrichment)
- [ ] Pseudotime differs across clinical stages (Kruskal-Wallis p<0.05)

### Statistical Rigor
- [ ] FDR correction applied to all features (FDR <0.05)
- [ ] Permutation test shows trajectory better than random (p<0.05)
- [ ] Effect sizes reported (not just p-values)
- [ ] Independent cohort validation performed (if available)

---

## Reporting Standards

When publishing trajectory analysis, report:

**Methods:**
- Sample size (patients, timepoints, total samples)
- Feature preprocessing (normalization, filtering)
- Trajectory method and parameters
- Validation approaches used

**Results:**
- Robustness/quality metrics
- Number of trajectory-associated features
- Correlation with clinical measures
- Survival analysis results
- Feature enrichment pathways

**Figures (minimum):**
1. PCA/UMAP of samples colored by pseudotime
2. Heatmap of top trajectory features
3. Kaplan-Meier curves by trajectory group
4. Validation plot (cross-validation or independent cohort)

---

## References

1. **Trajectory validation methods:** Saelens et al. *Nat Biotechnol* 2019 (comprehensive benchmarking)
2. **Statistical validation:** Noble WS. *Nat Biotechnol* 2009 (statistics best practices)
3. **Cross-validation approaches:** Hastie et al. *The Elements of Statistical Learning* (Chapter 7)
4. **Survival analysis:** Kleinbaum & Klein *Survival Analysis* 3rd edition

---

**Last Updated:** 2026-01-28
