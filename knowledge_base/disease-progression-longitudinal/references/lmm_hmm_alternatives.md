# Alternative Methods: Linear Mixed Models and Hidden Markov Models

This document provides detailed methodology, code examples, and parameter tuning for alternative trajectory analysis methods.

For method selection guidance, see [method_comparison.md](method_comparison.md).

---

## Linear Mixed Models (LMM)

### Overview

Linear Mixed Models (also called Linear Mixed-Effects Models or Multilevel Models) extend linear regression to handle repeated measures data. They model both **fixed effects** (population-level trends) and **random effects** (individual variation).

**Model structure:**
```
Y_ij = β₀ + β₁*time_ij + β₂*X₁_ij + ... + b₀i + b₁i*time_ij + ε_ij

Where:
  Y_ij = Feature expression for patient i at timepoint j
  β₀, β₁, β₂ = Fixed effects (population averages)
  b₀i, b₁i = Random effects (patient-specific deviations)
  ε_ij = Residual error
```

### Implementation in R

#### Basic LMM: Random Intercept

Each patient has a different baseline, but same slope:

```R
# Install packages
install.packages(c("lme4", "lmerTest"))
library(lme4)
library(lmerTest)

# Load data
data <- read.csv("longitudinal_data.csv")
# Expected columns: patient_id, timepoint, feature1, feature2, ...

# Fit LMM for a single feature
model <- lmer(feature1 ~ timepoint + (1 | patient_id), data = data)

# View results
summary(model)
# Fixed effects: timepoint coefficient = population trend
# Random effects: SD(Intercept) = between-patient variation

# Extract p-value for timepoint effect
anova(model)  # Type III ANOVA with Satterthwaite approximation
```

#### LMM with Covariates

Adjust for age, sex, treatment, etc.:

```R
# Model with covariates
model <- lmer(feature1 ~ timepoint + age + sex + treatment + (1 | patient_id),
              data = data)

summary(model)
# Interpretation:
#   timepoint coef = change per unit time, adjusted for covariates
#   age coef = effect of age on feature level
#   sex coef = difference between male/female
```

#### LMM with Random Slopes

Allow each patient to progress at different rates:

```R
# Random intercept + random slope
model <- lmer(feature1 ~ timepoint + (timepoint | patient_id), data = data)

summary(model)
# Random effects shows:
#   SD(Intercept) = baseline variation between patients
#   SD(timepoint) = progression rate variation between patients
#   Correlation = relationship between baseline and progression

# Extract patient-specific slopes
patient_slopes <- coef(model)$patient_id
```

#### Fit LMM Across All Features

Parallel processing for thousands of features:

```R
library(future.apply)
plan(multisession, workers = 8)  # Use 8 cores

# Reshape data to long format (if wide)
library(tidyr)
data_long <- pivot_longer(data,
                          cols = starts_with("feature"),
                          names_to = "feature",
                          values_to = "expression")

# Fit LMM for each feature
features <- unique(data_long$feature)

lmm_results <- future_lapply(features, function(feat) {
  # Subset to one feature
  feat_data <- data_long[data_long$feature == feat, ]

  # Fit model
  tryCatch({
    model <- lmer(expression ~ timepoint + (1 | patient_id), data = feat_data)

    # Extract results
    coefs <- fixef(model)
    pval <- anova(model)["timepoint", "Pr(>F)"]

    data.frame(
      feature = feat,
      intercept = coefs["(Intercept)"],
      slope = coefs["timepoint"],
      pvalue = pval
    )
  }, error = function(e) {
    # Return NA if model fails to converge
    data.frame(feature = feat, intercept = NA, slope = NA, pvalue = NA)
  })
}, future.seed = TRUE)

# Combine results
lmm_results <- do.call(rbind, lmm_results)

# FDR correction
library(stats)
lmm_results$padj <- p.adjust(lmm_results$pvalue, method = "fdr")

# Significant features
sig_features <- lmm_results[lmm_results$padj < 0.05, ]
sig_features <- sig_features[order(sig_features$pvalue), ]
```

#### Nonlinear Time Trends

If progression is nonlinear, add polynomial terms:

```R
# Quadratic time trend
model <- lmer(feature1 ~ timepoint + I(timepoint^2) + (1 | patient_id),
              data = data)

# Natural splines (more flexible)
library(splines)
model <- lmer(feature1 ~ ns(timepoint, df = 4) + (1 | patient_id),
              data = data)
```

### Parameter Tuning

**Optimizer convergence issues:**
```R
# If you see "convergence warning", try different optimizer
model <- lmer(feature1 ~ timepoint + (1 | patient_id), data = data,
              control = lmerControl(optimizer = "bobyqa"))

# Or increase iterations
model <- lmer(feature1 ~ timepoint + (1 | patient_id), data = data,
              control = lmerControl(optCtrl = list(maxfun = 20000)))
```

**Model selection (fixed vs random slopes):**
```R
# Compare models with likelihood ratio test
model1 <- lmer(feature1 ~ timepoint + (1 | patient_id), data = data, REML = FALSE)
model2 <- lmer(feature1 ~ timepoint + (timepoint | patient_id), data = data, REML = FALSE)

anova(model1, model2)
# If p < 0.05, random slopes improve fit
```

### Visualization

```R
library(ggplot2)

# Plot fitted trajectories for each patient
predictions <- expand.grid(
  patient_id = unique(data$patient_id),
  timepoint = seq(min(data$timepoint), max(data$timepoint), length.out = 50)
)
predictions$fitted <- predict(model, newdata = predictions)

ggplot(data, aes(x = timepoint, y = feature1)) +
  geom_point(alpha = 0.3) +
  geom_line(data = predictions, aes(y = fitted, group = patient_id),
            color = "blue", alpha = 0.5) +
  theme_minimal() +
  labs(title = "Patient Trajectories (LMM Fitted)",
       x = "Time", y = "Feature Expression")
```

---

## Hidden Markov Models (HMM)

### Overview

Hidden Markov Models assume that patients transition through discrete, unobserved disease states. Observations (feature expression) are generated from these hidden states.

**Model components:**
1. **States:** S1, S2, ..., Sn (hidden disease stages)
2. **Transitions:** P(St+1 | St) (probability of moving between states)
3. **Emissions:** P(Observation | State) (distribution of features in each state)

### Implementation in Python

#### Basic Gaussian HMM

Assume feature expression follows Gaussian distribution in each state:

```python
import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

# Load data (features × samples)
data = pd.read_csv("longitudinal_data.csv", index_col=0)
metadata = pd.read_csv("sample_metadata.csv")

# Transpose to samples × features for HMM
X = data.T.values

# Fit Gaussian HMM with 3 states
n_states = 3
model = GaussianHMM(
    n_components=n_states,
    covariance_type='diag',  # Diagonal covariance (features independent)
    n_iter=100,
    random_state=42
)

model.fit(X)

# Predict most likely state sequence (Viterbi algorithm)
states = model.predict(X)

# Add states to metadata
metadata['hmm_state'] = states
```

#### HMM with Multiple Random Initializations

HMMs can get stuck in local optima, so run multiple times:

```python
from sklearn.model_selection import KFold

def fit_hmm_with_multiple_inits(X, n_states, n_init=20):
    """Fit HMM with multiple random initializations, select best."""
    best_score = -np.inf
    best_model = None

    for i in range(n_init):
        model = GaussianHMM(
            n_components=n_states,
            covariance_type='diag',
            n_iter=100,
            random_state=i
        )

        model.fit(X)
        score = model.score(X)  # Log-likelihood

        if score > best_score:
            best_score = score
            best_model = model

    return best_model, best_score

# Fit with 20 random initializations
model, score = fit_hmm_with_multiple_inits(X, n_states=3, n_init=20)
states = model.predict(X)
```

#### Selecting Number of States

Use cross-validation or information criteria:

```python
from sklearn.model_selection import KFold

def select_n_states(X, max_states=6, n_splits=5):
    """Select optimal number of states using cross-validation."""

    results = []

    for n_states in range(2, max_states + 1):
        # Cross-validation
        kf = KFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_scores = []

        for train_idx, test_idx in kf.split(X):
            X_train, X_test = X[train_idx], X[test_idx]

            # Fit on train, score on test
            model = GaussianHMM(n_components=n_states, covariance_type='diag', n_iter=100)
            model.fit(X_train)
            score = model.score(X_test)
            cv_scores.append(score)

        # Average CV score
        mean_score = np.mean(cv_scores)
        results.append({'n_states': n_states, 'cv_score': mean_score})

    results_df = pd.DataFrame(results)

    # Select number of states with best CV score
    best_n_states = results_df.loc[results_df['cv_score'].idxmax(), 'n_states']

    return best_n_states, results_df

# Select optimal number of states
best_n_states, cv_results = select_n_states(X, max_states=6)
print(f"Optimal number of states: {best_n_states}")
print(cv_results)
```

#### Order States by Progression

HMM states are arbitrary labels - reorder to match disease progression:

```python
def order_states_by_pseudotime(states, metadata):
    """Reorder HMM states to match temporal progression."""

    # Calculate mean timepoint for each state
    state_means = metadata.groupby(states)['timepoint'].mean()
    state_order = state_means.sort_values().index

    # Create mapping: old state -> new state
    state_mapping = {old: new for new, old in enumerate(state_order)}

    # Relabel states
    states_ordered = np.array([state_mapping[s] for s in states])

    return states_ordered

states_ordered = order_states_by_pseudotime(states, metadata)
metadata['hmm_state_ordered'] = states_ordered
```

#### Extract State Transitions

```python
def get_transition_matrix(model):
    """Extract and visualize transition matrix."""
    import seaborn as sns
    import matplotlib.pyplot as plt

    # Transition probabilities
    trans_mat = model.transmat_

    # Heatmap
    plt.figure(figsize=(6, 5))
    sns.heatmap(trans_mat, annot=True, fmt='.3f', cmap='Blues',
                xticklabels=[f'S{i}' for i in range(trans_mat.shape[0])],
                yticklabels=[f'S{i}' for i in range(trans_mat.shape[0])])
    plt.xlabel('Next State')
    plt.ylabel('Current State')
    plt.title('State Transition Probabilities')
    plt.tight_layout()
    plt.savefig('hmm_transitions.svg', dpi=300)

    return trans_mat

trans_mat = get_transition_matrix(model)
```

#### State-Specific Feature Expression

Find features that distinguish states:

```python
def find_state_specific_features(data, states, top_n=50):
    """Identify features that differ across HMM states."""
    from scipy.stats import f_oneway

    # ANOVA for each feature across states
    results = []
    for feature in data.index:
        # Group expression by state
        groups = [data.loc[feature, states == s].values for s in np.unique(states)]

        # One-way ANOVA
        f_stat, pval = f_oneway(*groups)

        # Mean expression per state
        state_means = {f'state_{s}_mean': data.loc[feature, states == s].mean()
                       for s in np.unique(states)}

        results.append({
            'feature': feature,
            'f_statistic': f_stat,
            'pvalue': pval,
            **state_means
        })

    results_df = pd.DataFrame(results)

    # FDR correction
    from statsmodels.stats.multitest import multipletests
    reject, padj, _, _ = multipletests(results_df['pvalue'], alpha=0.05, method='fdr_bh')
    results_df['padj'] = padj

    # Top features
    top_features = results_df.nsmallest(top_n, 'padj')

    return top_features

state_features = find_state_specific_features(data, states_ordered, top_n=50)
```

### HMM for Longitudinal Data (Time-Series HMM)

For true longitudinal data with patient-specific sequences:

```python
def fit_hmm_per_patient_sequences(data, metadata, n_states=3):
    """Fit HMM on patient-specific time series."""

    # Organize data by patient
    patients = metadata['patient_id'].unique()

    # Concatenate patient sequences with lengths
    X_concat = []
    lengths = []

    for patient in patients:
        patient_mask = metadata['patient_id'] == patient
        patient_data = data.loc[:, patient_mask].T.values

        # Sort by timepoint
        patient_metadata = metadata[patient_mask].sort_values('timepoint')
        patient_data = patient_data[patient_metadata.index, :]

        X_concat.append(patient_data)
        lengths.append(len(patient_data))

    X_concat = np.vstack(X_concat)

    # Fit HMM with sequence lengths
    model = GaussianHMM(n_components=n_states, covariance_type='diag', n_iter=100)
    model.fit(X_concat, lengths=lengths)

    # Predict states for each patient sequence
    states_all = model.predict(X_concat, lengths=lengths)

    return model, states_all, lengths

model, states, lengths = fit_hmm_per_patient_sequences(data, metadata, n_states=3)

# Map states back to samples
sample_states = []
idx = 0
for length in lengths:
    sample_states.extend(states[idx:idx+length])
    idx += length

metadata['hmm_state'] = sample_states
```

### Parameter Tuning

**Covariance type:**
```python
# Options:
# 'spherical': same variance for all features (simplest)
# 'diag': different variance per feature (recommended)
# 'full': full covariance matrix (most flexible, computationally expensive)
# 'tied': same covariance for all states

model = GaussianHMM(n_components=3, covariance_type='diag')
```

**Convergence:**
```python
# Increase iterations if not converging
model = GaussianHMM(n_components=3, n_iter=200, tol=1e-4)

# Check convergence
model.fit(X)
print(f"Converged: {model.monitor_.converged}")
print(f"Iterations: {model.monitor_.iter}")
```

### Visualization

```python
from plotnine import ggplot, aes, geom_point, labs, theme_minimal
from plotnine_prism import theme_prism

# PCA colored by HMM states
from sklearn.decomposition import PCA

pca = PCA(n_components=2)
pcs = pca.fit_transform(data.T)

plot_data = pd.DataFrame({
    'PC1': pcs[:, 0],
    'PC2': pcs[:, 1],
    'State': [f'State {s}' for s in states_ordered],
    'Timepoint': metadata['timepoint']
})

(ggplot(plot_data, aes(x='PC1', y='PC2', color='State', size='Timepoint'))
 + geom_point(alpha=0.7)
 + labs(title='HMM States in PCA Space', x='PC1', y='PC2')
 + theme_prism()
).save('hmm_pca.svg', dpi=300, width=8, height=6)
```

---

## Comparing LMM and HMM Results

### Convert Between Representations

**HMM states → Continuous pseudotime:**
```python
# Use state order as pseudotime proxy
metadata['pseudotime_from_hmm'] = states_ordered

# Or use state posterior probabilities
posteriors = model.predict_proba(X)
# Weighted average of state indices
metadata['pseudotime_from_hmm'] = np.sum(
    posteriors * np.arange(n_states), axis=1
)
```

**LMM predicted values → States:**
```R
# Predict from LMM
data$predicted <- predict(model)

# Discretize into states using quantiles
data$state <- cut(data$predicted,
                   breaks = quantile(data$predicted, probs = seq(0, 1, length.out = 4)),
                   labels = c("State1", "State2", "State3"),
                   include.lowest = TRUE)
```

### Agreement Between Methods

```python
from scipy.stats import spearmanr

# Correlation between LMM predicted time and HMM pseudotime
corr, pval = spearmanr(lmm_predicted_time, hmm_pseudotime)
print(f"LMM vs HMM correlation: r={corr:.3f}, p={pval:.3e}")

# Expected: r > 0.6 for good agreement
```

---

## When to Use Which Method

**Use LMM when:**
- ✅ You need to model specific covariates (age, sex, treatment)
- ✅ You want interpretable population-level effects
- ✅ You have regular sampling intervals
- ✅ Classical statistical framework is required (p-values, CIs)

**Use HMM when:**
- ✅ You expect discrete disease stages
- ✅ You want to model state transitions
- ✅ You need to identify subpopulations with different trajectories
- ✅ Clinical staging validation is the goal

**Use both:**
- Run LMM to adjust for covariates, then HMM on residuals
- Use HMM states as grouping variable in LMM
- Cross-validate using both methods

---

## Complete Pipeline Examples

### Example 1: LMM Pipeline (R)

```R
# Full LMM analysis pipeline

# 1. Load data
data <- read.csv("longitudinal_data.csv")

# 2. Fit LMM across all features
library(lme4)
library(future.apply)
plan(multisession, workers = 8)

features <- colnames(data)[!colnames(data) %in% c("patient_id", "timepoint", "age", "sex")]

lmm_results <- future_lapply(features, function(feat) {
  formula <- as.formula(paste(feat, "~ timepoint + age + sex + (1 | patient_id)"))
  model <- lmer(formula, data = data)

  coefs <- fixef(model)
  pval <- anova(model)["timepoint", "Pr(>F)"]

  data.frame(
    feature = feat,
    slope = coefs["timepoint"],
    pvalue = pval
  )
}, future.seed = TRUE)

lmm_results <- do.call(rbind, lmm_results)
lmm_results$padj <- p.adjust(lmm_results$pvalue, method = "fdr")

# 3. Export significant features
sig_features <- lmm_results[lmm_results$padj < 0.05, ]
write.csv(sig_features, "lmm_trajectory_features.csv", row.names = FALSE)
```

### Example 2: HMM Pipeline (Python)

```python
# Full HMM analysis pipeline

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM

# 1. Load data
data = pd.read_csv("longitudinal_data.csv", index_col=0)
metadata = pd.read_csv("sample_metadata.csv")

# 2. Select optimal number of states
from sklearn.model_selection import KFold

best_n_states, cv_results = select_n_states(data.T.values, max_states=6)

# 3. Fit HMM with multiple initializations
model, score = fit_hmm_with_multiple_inits(
    data.T.values,
    n_states=best_n_states,
    n_init=20
)

# 4. Predict and order states
states = model.predict(data.T.values)
states_ordered = order_states_by_pseudotime(states, metadata)
metadata['hmm_state'] = states_ordered

# 5. Find state-specific features
state_features = find_state_specific_features(data, states_ordered, top_n=100)

# 6. Export results
metadata.to_csv("sample_with_states.csv", index=False)
state_features.to_csv("hmm_state_features.csv", index=False)
```

---

## Troubleshooting

### LMM Convergence Issues

**Problem:** "Model failed to converge"

**Solutions:**
```R
# 1. Scale predictors
data$timepoint_scaled <- scale(data$timepoint)
model <- lmer(feature1 ~ timepoint_scaled + (1 | patient_id), data = data)

# 2. Use different optimizer
model <- lmer(feature1 ~ timepoint + (1 | patient_id), data = data,
              control = lmerControl(optimizer = "bobyqa"))

# 3. Simplify random effects (remove random slopes)
# Instead of: (timepoint | patient_id)
# Use: (1 | patient_id)
```

### HMM Local Optima

**Problem:** Different runs give different states

**Solution:** Always use multiple random initializations and select best likelihood

```python
# Run 20 times, select best
best_score = -np.inf
for i in range(20):
    model = GaussianHMM(n_components=3, random_state=i)
    model.fit(X)
    if model.score(X) > best_score:
        best_model = model
        best_score = model.score(X)
```

---

## Software Requirements

### R Packages

```R
install.packages(c("lme4", "lmerTest", "ggplot2", "future.apply"))
```

### Python Packages

```bash
pip install hmmlearn numpy pandas scipy scikit-learn statsmodels plotnine plotnine-prism seaborn
```

---

## References

1. **LMM:** Bates D et al. *J Stat Softw* 2015 (lme4 package)
2. **HMM:** Rabiner LR. *Proc IEEE* 1989 (HMM tutorial)
3. **hmmlearn documentation:** [https://hmmlearn.readthedocs.io/](https://hmmlearn.readthedocs.io/)
4. **lme4 documentation:** [https://cran.r-project.org/web/packages/lme4/](https://cran.r-project.org/web/packages/lme4/)

---

**Last Updated:** 2026-01-28
