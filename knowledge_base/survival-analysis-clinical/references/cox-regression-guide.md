# Cox Proportional Hazards Regression Guide

## Model Overview

The Cox PH model is a semi-parametric regression for time-to-event data. It estimates hazard ratios (HR) for covariates without specifying the baseline hazard function.

**Key equation:** `h(t) = h₀(t) × exp(β₁X₁ + β₂X₂ + ...)`

Where `h₀(t)` is the unspecified baseline hazard and `exp(βᵢ)` is the hazard ratio for covariate `Xᵢ`.

## Interpreting Hazard Ratios

| HR Value | Interpretation | Example |
|----------|---------------|---------|
| HR > 1 | Increased hazard (worse prognosis) | HR = 1.5 → 50% higher risk of event |
| HR = 1 | No effect | Variable is not prognostic |
| HR < 1 | Decreased hazard (better prognosis) | HR = 0.7 → 30% lower risk of event |

**95% CI interpretation:** If the CI includes 1.0, the effect is not statistically significant at α = 0.05.

**For categorical variables:** HR compares each level to the reference level. E.g., `stageStage IV` with HR = 3.2 means Stage IV has 3.2× the hazard compared to Stage I (reference).

## Automatic Covariate Selection

The `run_survival_analysis()` function auto-selects covariates:

1. Excludes time, event, sample_id, and risk_group columns
2. Keeps columns with >80% non-missing values
3. Keeps columns with >1 unique value and <90% unique values (excludes IDs)
4. If full model fails to converge, uses stepwise approach (fits each covariate individually, keeps those that converge)

**To specify covariates manually:**
```r
result <- run_survival_analysis(data, covariates = c("age", "stage", "mol_subtype"))
```

## Concordance (C-index)

The C-index measures model discrimination — the probability that for a random pair of patients, the one with higher predicted risk has the earlier event.

| C-index | Interpretation |
|---------|---------------|
| 0.5 | No discrimination (random) |
| 0.6-0.7 | Poor to moderate |
| 0.7-0.8 | Good |
| 0.8-0.9 | Very good |
| > 0.9 | Excellent (verify — may indicate overfitting) |

## Proportional Hazards Assumption

**What it means:** The hazard ratio between any two patients is constant over time. If violated, the HR changes with time and a single HR is misleading.

**Testing:** `cox.zph()` computes scaled Schoenfeld residuals and tests for a time trend:
- Global p < 0.05 → Overall assumption may be violated
- Individual covariate p < 0.05 → That specific covariate's effect varies over time

**Remediation when violated:**
1. **Stratified Cox:** Stratify on the offending variable (`strata(variable)` in formula)
2. **Time-varying coefficients:** Fit separate models for different time windows
3. **Report and acknowledge:** If violation is mild (p near 0.05), report and note in conclusions

## Collinearity Checking (Automated)

The `fit_cox_model()` function automatically checks for collinearity before fitting:

1. **Derived variables:** If a numeric variable's name is a prefix of a categorical variable (e.g., `age` → `age_group`), the categorical derived variable is dropped.
2. **Cramér's V for categorical pairs:** For all pairs of categorical covariates, computes Cramér's V (a chi-square-based association measure). Pairs with V > 0.7 are flagged as collinear, and the variable with more factor levels (less general) is dropped.
3. **Example:** `her2_status` and `molecular_subtype` are highly collinear (HER2 status is embedded in subtype definitions). The check drops `her2_status` and keeps `molecular_subtype` as the more informative variable.

**Dropped covariates are recorded** in `result$dropped_covariates` with the reason, so the agent can accurately report what was modeled.

## Reference Group Selection (Automated)

For categorical covariates, `fit_cox_model()` automatically sets the **largest group as the reference level**. This produces more stable HR estimates because:
- The reference group contributes the baseline hazard
- Small reference groups (N < 50) produce wide CIs and unstable HRs
- Warnings are emitted if any reference group is small

Reference levels and their Ns are stored in `result$reference_levels`.

## Common Pitfalls

- **Multicollinearity:** Highly correlated covariates inflate standard errors. The automated Cramér's V check catches categorical-categorical collinearity (V > 0.7). Derived variables (e.g., age_group from age) are also auto-detected.
- **Overfitting:** With many covariates relative to events, the model is unstable. Rule of thumb: ≥10 events per covariate. If EPV < 10, the C-index is optimistically biased — never call it "good" without this caveat.
- **Small reference groups:** HR estimates are unstable when the reference category has few patients/events. Always check N in the reference group.
- **Informative censoring:** If patients drop out for reasons related to the outcome, KM and Cox estimates are biased.
- **Informative missingness:** If patients with missing covariate values have different event rates than non-missing patients, the Cox model is subject to selection bias. The workflow automatically tests for this via Fisher's exact test (results in `result$diagnostics$missing_assessment`).
- **Competing risks:** Standard Cox treats other causes of death as censored, which can overestimate event probabilities. Consider Fine-Gray model for competing risks.
