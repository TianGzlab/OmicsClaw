# TimeAx Methodology and Best Practices

## Overview

TimeAx (Time-Axis) is an algorithm for multiple trajectory alignment that reconstructs consensus disease trajectories from longitudinal patient data with irregular sampling times.

**Primary Citation:** Frishberg A, van den Munckhof ICL, Ter Horst R, et al. Reconstructing disease dynamics for mechanistic insights and clinical benefit. *Nat Commun*. 2023;14(1):6940.

---

## Algorithm Overview

### Core Concept

TimeAx addresses the challenge of aligning multiple patient trajectories when:
- Patients have different numbers of timepoints
- Sampling times are irregular across patients
- The underlying disease progression varies in speed across individuals
- We want to extract a shared consensus trajectory

### Three-Step Process

```
Step 1: Seed Selection
    ↓ Identify ~50 features with conserved temporal dynamics
Step 2: Consensus Iteration
    ↓ Align patient trajectories (100 iterations)
Step 3: Pseudotime Inference
    ↓ Project all samples onto consensus trajectory
```

---

## Step 1: Seed Selection

**Goal:** Identify features that show coordinated temporal changes across patients.

**Method:**
1. For each feature, compute temporal correlation within each patient
2. Aggregate correlation across patients
3. Select top N features with strongest consensus temporal signal

**Parameters:**
- `n_seeds`: Number of seed features (default: 50, range: 30-100)
  - Too few (<30): May miss important dynamics
  - Too many (>100): Noise dominates, slower computation

**Characteristics of good seed features:**
- High within-patient temporal correlation
- Consistent direction of change across patients
- Low technical noise
- Biological relevance to disease

---

## Step 2: Consensus Trajectory Alignment

**Goal:** Align all patient trajectories to construct a consensus disease progression timeline.

**Method:**
1. Initialize with raw time as pseudotime
2. For each iteration:
   - Smooth feature values along current pseudotime
   - Compute optimal warping to align patients
   - Update pseudotime based on alignment
3. Converge to stable consensus trajectory

**Parameters:**
- `n_iterations`: Number of consensus iterations (default: 100, range: 50-200)
  - Too few (<50): May not converge
  - Too many (>200): Overfitting, diminishing returns

**Convergence criteria:**
- Pseudotime assignments stabilize
- Alignment score plateaus
- Typically converges in 50-100 iterations

---

## Step 3: Pseudotime Inference

**Goal:** Assign disease pseudotime to each sample based on consensus trajectory.

**Output:**
- **Pseudotime:** Continuous value (0-1) representing disease stage
  - 0 = Early disease / baseline
  - 1 = Advanced disease / endpoint
  - Intermediate values = disease progression stage

- **Uncertainty:** Confidence in pseudotime assignment
  - Low uncertainty: Sample clearly positioned on trajectory
  - High uncertainty: Ambiguous position (often intermediate stages)

**Interpretation:**
- Pseudotime ≠ calendar time
- Reflects disease stage, not age of disease
- Fast progressors reach high pseudotime quickly
- Slow progressors remain at low pseudotime longer

---

## Robustness Assessment

TimeAx includes a built-in validation metric to assess trajectory quality.

### Robustness Score

**Computation:**
1. Leave-one-patient-out cross-validation
2. Rebuild trajectory without each patient
3. Project left-out patient onto reconstructed trajectory
4. Compute consistency across all leave-one-out iterations

**Interpretation:**
- **>0.7:** High quality, reliable trajectory
  - Trajectory is stable and generalizable
  - Proceed with confidence

- **0.5-0.7:** Moderate quality
  - Trajectory captures some signal
  - Interpret results cautiously
  - Consider increasing sample size or filtering noisy features

- **<0.5:** Low quality, unreliable
  - Weak temporal signal
  - May be driven by batch effects or noise
  - Consider alternative methods or more data

---

## Parameter Tuning Guidelines

### n_seeds (Number of Seed Features)

**Default: 50**

**When to increase (70-100):**
- Large datasets (>10,000 features)
- Complex disease with multiple processes
- Weak individual feature signals

**When to decrease (30-40):**
- Small datasets (<5,000 features)
- Strong, clear temporal signal
- Focus on core disease mechanisms

**How to choose:**
Examine seed feature list - should be enriched for biologically relevant genes/proteins.

### n_iterations (Consensus Iterations)

**Default: 100**

**When to increase (150-200):**
- Robustness score improving but not plateaued
- Large number of patients (>50)
- Complex trajectory structure

**When to decrease (50-75):**
- Quick exploratory analysis
- Robustness score plateaus early
- Small dataset (<20 patients)

**Monitor:** Track alignment score across iterations - should converge.

---

## Best Practices

### Data Preparation

1. **Normalization:**
   - RNA-seq: log2(CPM + 1) or VST
   - Proteomics: log2 + quantile normalization
   - Clinical: Z-score per feature

2. **Batch correction:**
   - Apply ComBat or similar before TimeAx
   - Ensure correction doesn't remove biological signal

3. **Feature filtering:**
   - Remove low-variance features (bottom 50%)
   - Keep 5,000-10,000 most variable features
   - Exclude features with high missingness (>20%)

### Quality Control

1. **Before TimeAx:**
   - ≥10 patients (20+ ideal)
   - ≥3 timepoints per patient (5+ ideal)
   - Adequate temporal coverage
   - Low batch effects

2. **After TimeAx:**
   - Check robustness score (aim for >0.7)
   - Validate seed features biologically
   - Pseudotime should correlate with clinical measures
   - Visualize on PCA/UMAP - should show progression

### Validation Strategies

1. **Cross-validation:**
   - Leave-one-patient-out (built into robustness)
   - Leave-one-timepoint-out
   - Bootstrap resampling

2. **External validation:**
   - Independent cohort
   - Different tissue/sample type
   - Different technology

3. **Biological validation:**
   - Known early markers at low pseudotime
   - Known late markers at high pseudotime
   - Trajectory features enriched in disease pathways

---

## Troubleshooting

### Low Robustness Score (<0.5)

**Possible causes:**
- Insufficient temporal signal
- Strong batch effects
- Too few patients or timepoints
- Noisy data

**Solutions:**
1. Increase sample size
2. Apply batch correction
3. Filter to most variable features
4. Check for outlier patients
5. Try alternative normalization

### Unexpected Seed Features

**Possible causes:**
- Batch effects
- Technical artifacts (ribosomal, mitochondrial genes)
- Wrong normalization

**Solutions:**
1. Examine seed features for technical contamination
2. Exclude artifact genes before TimeAx
3. Improve batch correction
4. Validate with biological knowledge

### Pseudotime Doesn't Match Clinical Stages

**Possible causes:**
- Clinical stages may not reflect continuous biology
- Batch effects confounding trajectory
- Heterogeneous disease subtypes

**Solutions:**
1. Check if clinical stages are truly ordinal
2. Stratify by disease subtype
3. Use pseudotime as continuous measure, not discrete stages
4. Validate trajectory genes independently

### High Uncertainty Scores

**Expected:**
- Intermediate disease stages naturally have higher uncertainty
- Samples at branch points (if multiple trajectories exist)

**Problematic:**
- Uniformly high uncertainty across all samples
- Indicates weak trajectory signal or noisy data

---

## Comparison to Alternative Methods

| Method | Strengths | Weaknesses |
|--------|-----------|------------|
| **TimeAx** | Handles irregular sampling; robust to noise; works with cross-sectional data | Assumes single continuous trajectory; moderate computational cost |
| **Linear Mixed Models** | Classical statistics; covariate modeling; interpretable | Requires regular sampling; assumes linear dynamics; less robust |
| **Hidden Markov Models** | Identifies discrete states; probabilistic; good for staged diseases | Doesn't capture continuous progression; requires state number specification |

**When to use TimeAx:**
- ✅ Irregular or sparse sampling
- ✅ Mix of longitudinal and cross-sectional samples
- ✅ Continuous disease progression
- ✅ Need robust alignment across patients

**When to use alternatives:**
- ❌ Need discrete disease states → HMM
- ❌ Need covariate modeling → LMM
- ❌ Need causal inference → Structural equations

---

## Advanced Topics

### Multiple Trajectories

If your disease has distinct progression subtypes:

1. **Cluster patients first:**
   - Cluster by baseline features or trajectory shape
   - Run TimeAx separately per cluster

2. **Stratified analysis:**
   - Stratify by known subtype (e.g., tumor grade)
   - Compare trajectories across subtypes

### Integration with Clinical Data

**Outcome prediction:**
```python
# Use pseudotime as predictor
from lifelines import CoxPHFitter

cph = CoxPHFitter()
cph.fit(df[['pseudotime', 'survival_time', 'event']],
        duration_col='survival_time',
        event_col='event')
```

**Group comparison:**
```python
from scipy.stats import mannwhitneyu

# Compare pseudotime between outcome groups
good_outcome = metadata[metadata['outcome'] == 'good']['pseudotime']
poor_outcome = metadata[metadata['outcome'] == 'poor']['pseudotime']

stat, pval = mannwhitneyu(good_outcome, poor_outcome)
```

### Feature Dynamics Analysis

**Identify genes changing along trajectory:**
```python
from scipy.stats import spearmanr

correlations = []
for gene in data.index:
    corr, pval = spearmanr(data.loc[gene], pseudotime)
    correlations.append({'gene': gene, 'correlation': corr, 'pvalue': pval})
```

---

## References

1. **TimeAx Paper:** Frishberg A, et al. Reconstructing disease dynamics for mechanistic insights and clinical benefit. *Nat Commun*. 2023;14:6940.

2. **TimeAx GitHub:** [https://github.com/amitfrish/TimeAx](https://github.com/amitfrish/TimeAx)

3. **Disease Trajectory Review:** Schmidt AF, et al. *Annu Rev Biomed Data Sci*. 2024;7:329-348.

---

**Last Updated:** 2026-01-28
