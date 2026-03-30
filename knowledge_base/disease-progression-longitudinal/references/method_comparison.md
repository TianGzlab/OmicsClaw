# Method Selection Guide: Trajectory Analysis Methods

This document provides detailed comparison and selection criteria for choosing between trajectory reconstruction methods.

---

## Method Comparison Table

| Criterion | TimeAx | Linear Mixed Models | Hidden Markov Models |
|-----------|--------|---------------------|----------------------|
| **Irregular sampling** | ✅ Excellent | ⚠️ Fair | ⚠️ Fair |
| **Cross-sectional data** | ✅ Yes | ❌ No | ❌ No |
| **Continuous trajectory** | ✅ Yes | ✅ Yes | ❌ No (discrete states) |
| **Discrete states** | ❌ No | ❌ No | ✅ Yes |
| **Covariates** | ⚠️ Limited | ✅ Excellent | ⚠️ Post-hoc |
| **Handles noise** | ✅ Robust | ⚠️ Moderate | ⚠️ Moderate |
| **Interpretability** | ⚠️ Moderate | ✅ High | ✅ High |
| **Computational cost** | ⚠️ Moderate | ✅ Fast | ✅ Fast |
| **Sample size** | 10-100 patients | 10-1000 patients | 10-100 patients |
| **Software maturity** | ⚠️ New (2023) | ✅ Mature | ✅ Mature |
| **Missing data handling** | ✅ Good | ⚠️ Moderate | ⚠️ Poor |

---

## TimeAx (Multiple Trajectory Alignment)

### When to Use
- **Best for:**
  - Irregular sampling intervals between and within patients
  - Mixed cross-sectional and longitudinal cohorts
  - Continuous disease progression without clear stages
  - High-dimensional omics data (RNA-seq, proteomics)
  - Noisy data with technical variation

- **Not suitable for:**
  - Discrete disease stages (use HMM instead)
  - Need to model specific covariates (use LMM instead)
  - Very small sample sizes (<10 patients)

### Strengths
- **Robust to irregular sampling:** Works when patients are sampled at different times
- **No assumptions about trajectory shape:** Learns progression pattern from data
- **Cross-sectional + longitudinal:** Can combine cohorts with different designs
- **Noise robust:** Multiple alignment approach averages out noise
- **High-dimensional:** Scales to thousands of features

### Limitations
- **Limited covariate modeling:** Cannot directly adjust for age, sex, etc. (requires pre-correction)
- **Computational cost:** Iterative alignment takes 5-20 minutes for typical datasets
- **Interpretability:** Pseudotime is abstract, not directly clinical
- **New method:** Less established than classical statistical approaches

### Example Use Cases
1. **Cancer progression:** Tumor samples collected at irregular intervals during treatment
2. **COVID-19 severity:** Cross-sectional cohort with varying days since symptom onset
3. **Alzheimer's disease:** Longitudinal cognitive decline with irregular follow-ups
4. **Treatment response:** Pre-treatment + variable post-treatment timepoints

### Parameter Guidance
- `n_iterations`: 100 (default) is usually sufficient; increase to 200 for noisy data
- `n_seeds`: 50-100 seed features; more seeds = more robust but slower
- `validation=True`: Always enable for robustness assessment

---

## Linear Mixed Models (LMM)

### When to Use
- **Best for:**
  - Regular sampling intervals (e.g., monthly visits)
  - Need to model covariates (age, sex, treatment, batch)
  - Classical statistical framework required (p-values, confidence intervals)
  - Large sample sizes (50+ patients)
  - Interpretable fixed and random effects

- **Not suitable for:**
  - Highly irregular sampling
  - Cross-sectional data only
  - Very small sample sizes (<10 patients)

### Strengths
- **Covariate modeling:** Explicitly model age, sex, treatment effects
- **Statistical inference:** P-values, confidence intervals, hypothesis testing
- **Interpretability:** Fixed effects are directly interpretable
- **Computational speed:** Fast fitting even for large datasets
- **Mature software:** Well-established R packages (lme4, nlme)

### Limitations
- **Requires repeated measures:** Each patient needs multiple timepoints
- **Assumes linearity:** Or requires manual specification of nonlinear terms
- **Regular sampling preferred:** Irregular timing reduces power
- **Missing data:** Complete case analysis or imputation needed

### Example Use Cases
1. **Clinical trial with scheduled visits:** Monthly follow-ups for 12 months
2. **Cohort study with regular biomarker collection:** Annual blood draws
3. **Controlled experiment:** Patients sampled at 0, 3, 6, 12 months
4. **Need to adjust for treatment:** Compare progression on drug A vs. drug B

### Model Formula Examples

**Basic trajectory model:**
```R
# Time as fixed effect, random intercept per patient
lmer(expression ~ timepoint + (1 | patient_id), data = data)
```

**With covariates:**
```R
# Age, sex, treatment as covariates
lmer(expression ~ timepoint + age + sex + treatment + (1 | patient_id), data = data)
```

**Random slopes:**
```R
# Allow each patient to have different progression rate
lmer(expression ~ timepoint + (timepoint | patient_id), data = data)
```

**Nonlinear time:**
```R
# Quadratic time trend
lmer(expression ~ timepoint + I(timepoint^2) + (1 | patient_id), data = data)
```

### Parameter Guidance
- Include random intercept `(1 | patient_id)` at minimum
- Add random slope `(timepoint | patient_id)` if patients progress at different rates
- Use restricted maximum likelihood (REML) for inference
- Check model assumptions: residuals should be normally distributed

---

## Hidden Markov Models (HMM)

### When to Use
- **Best for:**
  - Discrete disease states or stages (e.g., mild, moderate, severe)
  - State transition analysis (probability of moving between states)
  - Clinical staging validation
  - Sparse data with clear clustering
  - Identifying subpopulations with different trajectories

- **Not suitable for:**
  - Continuous, gradual progression without clear stages
  - Very small sample sizes (<20 patients)
  - Need continuous pseudotime

### Strengths
- **Discrete states:** Directly models disease stages
- **Transition probabilities:** Quantifies likelihood of state changes
- **Interpretability:** States often match clinical staging
- **Handles missingness:** Probabilistic framework robust to missing data
- **Subpopulation discovery:** Can identify patients with different trajectories

### Limitations
- **Assumes discrete states:** Not suitable for continuous progression
- **State number selection:** Need to choose number of states (2-6 typical)
- **Local optima:** Multiple random initializations needed
- **Longitudinal data required:** Needs repeated measures to estimate transitions

### Example Use Cases
1. **Cancer staging:** Model transitions between tumor grades
2. **Cognitive decline:** Healthy → MCI → mild AD → moderate AD → severe AD
3. **Infection states:** Acute → recovery → chronic → resolved
4. **Treatment response:** Non-responder → partial response → complete response

### Model Structure

**Standard HMM:**
```
States: S1 (early) → S2 (intermediate) → S3 (advanced)
Observations: Feature expression at each timepoint
Transitions: P(S1→S2), P(S2→S3), P(state → same state)
```

**Number of states:**
- 2 states: Binary classification (e.g., stable vs. progressive)
- 3-4 states: Most common for disease staging
- 5-6 states: Fine-grained staging, requires large sample size
- >6 states: Usually overfitting

### Parameter Guidance
- Use Baum-Welch algorithm for parameter estimation
- Initialize with k-means clustering on first timepoint
- Run 10-20 random initializations and select best log-likelihood
- Validate state assignments against clinical staging

---

## Decision Tree for Method Selection

```
Start: Do you have longitudinal data?
│
├─ NO (cross-sectional only)
│   └─ Use TimeAx (only method that works with cross-sectional)
│
└─ YES (repeated measures per patient)
    │
    ├─ Is sampling regular (same times for all patients)?
    │   ├─ YES → Do you need covariate modeling?
    │   │   ├─ YES → Use LMM
    │   │   └─ NO → Use TimeAx or LMM
    │   │
    │   └─ NO (irregular sampling) → Use TimeAx
    │
    └─ Are there discrete disease stages?
        ├─ YES → Use HMM
        └─ NO (continuous progression) → Use TimeAx or LMM
```

---

## Combining Methods

You can use multiple methods for complementary insights:

### TimeAx + LMM
1. **TimeAx:** Order samples by pseudotime
2. **LMM:** Model feature changes over pseudotime with covariates
3. **Benefit:** Combines TimeAx's flexible alignment with LMM's covariate modeling

```python
# Step 1: Get pseudotime from TimeAx
pseudotime = run_timeax_alignment(data, metadata)

# Step 2: Add to metadata and fit LMM in R
metadata['pseudotime'] = pseudotime
# In R: lmer(expression ~ pseudotime + age + sex + (1|patient_id))
```

### TimeAx + HMM
1. **TimeAx:** Order samples by pseudotime
2. **HMM:** Discretize pseudotime into disease states
3. **Benefit:** Continuous trajectory + interpretable staging

```python
# Step 1: Get pseudotime from TimeAx
pseudotime = run_timeax_alignment(data, metadata)

# Step 2: Fit HMM on pseudotime-ordered samples
states = fit_hmm_on_ordered_samples(data, pseudotime, n_states=4)
```

### LMM + HMM
1. **LMM:** Model temporal trends adjusted for covariates
2. **HMM:** Identify discrete states from LMM residuals
3. **Benefit:** Accounts for covariates before state identification

---

## Validation Across Methods

### Cross-method validation
If your data allows, run multiple methods and check for consistency:

**Agreement metrics:**
- **Pseudotime correlation:** TimeAx pseudotime vs. LMM predicted time
- **State concordance:** HMM states vs. TimeAx pseudotime bins
- **Feature overlap:** Do methods identify same trajectory-associated features?

**Expected agreement:**
- High correlation (r > 0.7): Methods agree on trajectory order
- Moderate correlation (r = 0.4-0.7): Methods capture different aspects
- Low correlation (r < 0.4): Data may not have clear trajectory

---

## Computational Considerations

### Runtime Estimates (typical dataset: 30 patients, 100 samples, 5000 features)

| Method | Runtime | Memory | Scalability |
|--------|---------|--------|-------------|
| **TimeAx** | 5-20 min | 4-8 GB | 5,000-10,000 features max |
| **LMM** | 10-60 sec per feature | 2-4 GB | 10,000+ features (parallel) |
| **HMM** | 1-5 min | 2-4 GB | 5,000-10,000 features max |

### Computational optimization

**TimeAx:**
- Reduce features to 5,000 most variable genes
- Use fewer seeds (n_seeds=20) for initial exploration
- Parallelize validation runs

**LMM:**
- Fit models in parallel across features (R: `future.apply`)
- Use sparse matrix representation for large datasets
- Consider approximations (lmerTest with Satterthwaite)

**HMM:**
- Use k-means initialization for faster convergence
- Parallelize multiple random starts
- Reduce features to informative subset

---

## Software and Implementation

### TimeAx
```r
# R package (primary implementation)
install.packages("remotes")
remotes::install_github("amitfrish/TimeAx")

# Usage in R
library(TimeAx)
model <- modelCreation(trainData = data_matrix, sampleNames = sample_names,
                       numOfIter = 100, numOfTopFeatures = 50)
pseudo_stats <- predictByConsensus(model = model, testData = data_matrix)
```

The Python workflow calls TimeAx via R subprocess (see `scripts/timeax_r_wrapper.py`).

### LMM
```R
# R packages
install.packages(c("lme4", "lmerTest"))

library(lme4)
model <- lmer(expression ~ timepoint + (1|patient_id), data=data)
```

### HMM
```python
# Python package
pip install hmmlearn

from hmmlearn.hmm import GaussianHMM
model = GaussianHMM(n_components=4, covariance_type='diag')
states = model.fit_predict(data)
```

---

## Further Reading

- **TimeAx paper:** Frishberg et al. *Nat Commun* 2023 (main methodology)
- **LMM tutorial:** Bates et al. *J Stat Softw* 2015 (lme4 package)
- **HMM for disease:** Sukkar et al. *BMC Bioinformatics* 2012 (biomedical applications)
- **Method comparison:** Qi et al. *Brief Bioinform* 2022 (trajectory inference methods)

---

**Last Updated:** 2026-01-28
