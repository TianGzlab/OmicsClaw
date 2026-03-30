# Risk Stratification Guide

## Overview

Risk stratification divides patients into groups based on predicted risk from the Cox model. The linear predictor (`predict(cox_model, type = "lp")`) is used as the risk score.

## Available Methods

| Method | Groups | Best For |
|--------|--------|---------|
| `median` | 2 (High/Low) | Balanced groups, simple interpretation |
| `tertiles` | 3 (High/Medium/Low) | Clinical utility, identifying intermediate-risk patients |
| `quartiles` | 4 (Q1-Q4) | Granular analysis, dose-response relationships |
| `custom` | User-defined | Known clinical cutpoints or external validation thresholds |

**Usage:**
```r
# Default: median split
result <- run_survival_analysis(data)

# Tertile split
result <- run_survival_analysis(data, risk_strata_method = "tertiles")

# Custom cutpoints
result <- run_survival_analysis(data, risk_strata_method = "custom",
                                 risk_strata_col = "my_risk_column")
```

## How Risk Scores Are Computed

1. Cox model fits `Surv(time, event) ~ covariates`
2. Linear predictor = `β₁X₁ + β₂X₂ + ...` (no baseline hazard)
3. Higher linear predictor → higher predicted hazard → worse prognosis
4. Patients split into groups based on linear predictor quantiles

## Log-rank Test for Risk Groups

After stratification, a log-rank test compares survival curves between groups:
- p < 0.05 → Statistically significant separation
- Low p-value + visual separation on KM curves → Risk groups are clinically meaningful

## Downstream Integration

### With lasso-biomarker-panel
Export `risk_scores.csv` and use risk group as a feature or outcome:
```r
# Load survival results
model <- readRDS("results/survival_model.rds")
risk_scores <- model$cox$risk_scores
```

### With disease-progression-longitudinal
Use `clinical_annotated.csv` with risk group assignments for trajectory analysis.

## Clinical Validation Considerations

- **Internal validation:** Bootstrap or cross-validation of the risk score
- **External validation:** Apply risk score thresholds to an independent cohort
- **Calibration:** Compare predicted vs observed event rates per risk group
- **Net reclassification:** Compare risk groups to existing clinical staging


---
