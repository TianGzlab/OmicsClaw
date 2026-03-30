# MR Methods Reference

## Overview

Two-sample Mendelian Randomization uses genetic variants (SNPs) as **instrumental variables** to estimate the causal effect of an exposure on an outcome. The genetic variants must satisfy three core assumptions:

1. **Relevance**: Variants are associated with the exposure (F-statistic > 10)
2. **Independence**: Variants are not associated with confounders
3. **Exclusion restriction**: Variants affect the outcome only through the exposure

## Primary Methods

### Inverse-Variance Weighted (IVW)

The **default primary method**. Combines individual SNP Wald ratio estimates (β_outcome / β_exposure) using inverse-variance meta-analysis.

- **Assumption**: All instruments are valid (no horizontal pleiotropy), or pleiotropy is balanced (equally likely positive/negative)
- **Strengths**: Most statistically efficient method; well-understood properties
- **Limitations**: Biased if directional pleiotropy exists
- **Interpretation**: The causal estimate represents the change in outcome per unit change in genetically-predicted exposure
- **Variants**: Fixed-effects (homogeneous instruments) and multiplicative random-effects (heterogeneous instruments; **recommended by default**)

### MR-Egger Regression

Relaxes the exclusion restriction by allowing **all** instruments to have pleiotropic effects, provided pleiotropy is independent of instrument strength (InSIDE assumption).

- **Assumption**: Instrument Strength Independent of Direct Effect (InSIDE)
- **Strengths**: Provides both a causal estimate and a **pleiotropy test** (intercept ≠ 0 indicates directional pleiotropy)
- **Limitations**: Less efficient than IVW; sensitive to outliers; InSIDE may not hold
- **Intercept interpretation**:
  - Intercept ≈ 0 (p > 0.05): No evidence of directional pleiotropy → IVW likely valid
  - Intercept ≠ 0 (p < 0.05): Directional pleiotropy present → IVW may be biased

### Weighted Median

Provides a consistent estimate if **at least 50% of instruments are valid** (majority valid assumption).

- **Assumption**: Majority of information comes from valid instruments
- **Strengths**: Robust to outliers; less sensitive to individual variant removal
- **Limitations**: Sensitive to addition/removal of variants near the validity boundary
- **When to prefer**: When heterogeneity suggests some instruments may be invalid

### Weighted Mode

Provides a consistent estimate if the **largest group of instruments** identifies the same causal effect (plurality valid assumption).

- **Assumption**: The most common causal estimate across instruments is the correct one
- **Strengths**: Most robust to outliers; weakest assumptions about instrument validity
- **Limitations**: Low precision; conservative confidence intervals
- **When to prefer**: When substantial pleiotropy is suspected

## Sensitivity Analyses

### Cochran's Q Test (Heterogeneity)

Tests whether individual SNP estimates are more variable than expected by chance.

- **Q p > 0.05**: No significant heterogeneity → instruments behave consistently
- **Q p < 0.05**: Significant heterogeneity → some instruments may be invalid or pleiotropic
- **Note**: Some heterogeneity is expected even with valid instruments; use alongside other tests

### MR-Egger Intercept (Directional Pleiotropy)

Tests whether the MR-Egger intercept differs from zero.

- **p > 0.05**: No evidence of directional pleiotropy → IVW estimate likely unbiased
- **p < 0.05**: Directional pleiotropy detected → IVW may be biased; consider MR-Egger slope or robust methods

### Steiger Directionality Test

Tests whether the genetic variants explain more variance in the exposure than the outcome, confirming the hypothesized causal direction.

- **correct_causal_direction = TRUE**: Variants are stronger instruments for exposure → supports proposed direction
- **correct_causal_direction = FALSE**: Variants explain more outcome variance → reverse causation concern
- **Limitation**: Requires sample size information; may fail if metadata is incomplete

### Leave-One-Out Analysis

Removes each SNP in turn and re-estimates the IVW effect.

- **Stable estimates**: No single SNP drives the result → robust finding
- **Estimate changes >20%**: That SNP may be an influential outlier (potentially pleiotropic)
- **Use**: Identify and investigate influential instruments; consider removing if biologically justified

### Single-SNP (Wald Ratio) Analysis

Computes the causal estimate for each SNP individually.

- **Concordant directions**: Most SNPs point the same way → consistent evidence
- **Discordant SNPs**: May indicate pleiotropy or different biological mechanisms
- **Use**: Complement to forest plot visualization

## Diagnostic Plots

### Scatter Plot
- **X-axis**: SNP-exposure associations (β_exposure)
- **Y-axis**: SNP-outcome associations (β_outcome)
- **Lines**: Slopes from each MR method (IVW, Egger, WM, WMode)
- **Interpretation**: Points clustering around lines = concordant estimates; spread = heterogeneity

### Forest Plot
- Each SNP's individual Wald ratio estimate with 95% CI
- Combined estimates from IVW and MR-Egger shown at bottom
- **Interpretation**: Overlapping CIs = consistent instruments; outliers visible

### Funnel Plot
- **X-axis**: Individual SNP causal estimates
- **Y-axis**: Precision (1/SE)
- **Interpretation**: Symmetric funnel = no directional pleiotropy; asymmetry = bias concern

### Leave-One-Out Plot
- IVW estimate when each SNP is removed, with 95% CI
- **Interpretation**: Horizontal line stability = robust; shifts = influential SNP

## Evidence Assessment Framework

**Strong evidence for causality** (all of):
- IVW p < 0.05 with meaningful effect size
- Concordant direction across all 4 methods (including Weighted Mode)
- No significant heterogeneity (Q p > 0.05)
- No directional pleiotropy (Egger intercept p > 0.05)
- Correct Steiger direction (with liability-scale R² for binary outcomes)
- Robust to leave-one-out
- Mean F-statistic > 10 (adequate instrument strength)

**Suggestive evidence** (some of):
- IVW significant but one method non-significant (discuss explicitly)
- Some heterogeneity but consistent direction; MR-PRESSO corrected estimate still significant
- Leave-one-out mostly stable

**Weak/inconclusive** (any of):
- Methods disagree on direction (any method opposite to IVW)
- Strong heterogeneity with discordant outlier SNPs
- Significant pleiotropy
- Few instruments (<10 SNPs)
- Incorrect Steiger direction
- Weak instruments (mean F < 10)

## References

- Sanderson E, et al. (2022). Mendelian randomization. *Nat Rev Methods Primers*. PMC7384151
- Bowden J, et al. (2015). Mendelian randomization with invalid instruments. *Stat Med*. 34(15):2313-25
- Bowden J, et al. (2016). Consistent estimation in MR with some invalid instruments. *Genet Epidemiol*. 40(4):304-14
- Hartwig FP, et al. (2017). Robust inference in summary data MR using the weighted mode. *Int J Epidemiol*. 46(6):1717-26


---
