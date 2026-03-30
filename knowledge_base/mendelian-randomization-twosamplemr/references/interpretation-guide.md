# MR Results Interpretation Guide

## Quick Decision Tree

```
1. Is the IVW estimate significant (p < 0.05)?
   ├── YES → Go to step 2
   └── NO  → No evidence for causal effect (check power)

2. Do all methods agree on direction?
   ├── YES → Go to step 3
   └── NO  → Caution: methods disagree, investigate pleiotropy

3. Is there significant heterogeneity (Q p < 0.05)?
   ├── YES → Some instruments may be invalid; rely more on robust methods
   └── NO  → Go to step 4

4. Is there directional pleiotropy (Egger intercept p < 0.05)?
   ├── YES → IVW may be biased; prefer MR-Egger or weighted median estimate
   └── NO  → Go to step 5

5. Is the Steiger direction correct?
   ├── YES → Evidence supports proposed causal direction
   └── NO  → Reverse causation concern; test bidirectional MR

6. Is leave-one-out stable?
   ├── YES → Strong evidence for causality
   └── NO  → Investigate influential SNPs; result may be driven by one locus
```

## Reading the Results Table

The `mr_results.csv` contains one row per method:

| Column | Description |
|--------|-------------|
| method | MR method name |
| nsnp | Number of instruments used |
| b | Causal effect estimate (beta) |
| se | Standard error of the estimate |
| pval | P-value for the causal effect |

**Interpreting the beta:**
- **Continuous exposure → continuous outcome**: 1-unit increase in genetically-predicted exposure → b units change in outcome
- **Continuous exposure → binary outcome (log-OR)**: 1-unit increase in exposure → exp(b) odds ratio for outcome
- **Binary exposure (log-OR) → continuous outcome**: 1 log-OR increase in liability → b units change in outcome

## Reading the Sensitivity Results

### Heterogeneity (heterogeneity_results.csv)

| Column | What it means |
|--------|---------------|
| Q | Cochran's Q statistic (larger = more heterogeneity) |
| Q_df | Degrees of freedom (number of SNPs - 1 for IVW) |
| Q_pval | P-value (< 0.05 means significant heterogeneity) |

### Pleiotropy (pleiotropy_results.csv)

| Column | What it means |
|--------|---------------|
| egger_intercept | MR-Egger intercept (should be ~0 if no pleiotropy) |
| se | Standard error of intercept |
| pval | P-value (< 0.05 means directional pleiotropy detected) |

### Directionality (directionality_results.csv)

| Column | What it means |
|--------|---------------|
| snp_r2.exposure | Variance in exposure explained by SNPs |
| snp_r2.outcome | Variance in outcome explained by SNPs |
| correct_causal_direction | TRUE if exposure R² > outcome R² |
| steiger_pval | P-value for directionality test |

## Reading the Plots

### Scatter Plot
- **What to look for**: Points should cluster around the IVW line
- **Good sign**: All method lines have similar slopes
- **Bad sign**: MR-Egger line has very different slope from IVW (suggests pleiotropy)
- **Bad sign**: Points scattered widely (heterogeneity)

### Forest Plot
- **What to look for**: Individual SNP estimates should overlap with the combined estimate
- **Good sign**: Most CIs cross the combined estimate line
- **Bad sign**: One or two SNPs far from the rest (potential outliers/pleiotropic instruments)

### Funnel Plot
- **What to look for**: Symmetric distribution around the IVW estimate
- **Good sign**: Symmetric funnel shape, most precise estimates near center
- **Bad sign**: Asymmetry suggests directional pleiotropy or bias

### Leave-One-Out Plot
- **What to look for**: Estimates should be stable regardless of which SNP is removed
- **Good sign**: All points within a narrow range, CIs overlap
- **Bad sign**: Removing one SNP dramatically shifts the estimate (that SNP is influential)

## Instrument Strength (F-statistics)

Each instrument's strength is measured by its F-statistic: F = (beta_exposure / se_exposure)^2.

- **F > 10 per instrument**: Rule of thumb for sufficient instrument strength
- **Mean F > 10**: Overall instruments are adequately strong
- **F < 10**: Weak instrument — biases MR estimate toward the confounded observational estimate (toward null for two-sample MR)
- **Report**: Always report mean F-statistic, minimum F, and number of weak instruments

## MR-PRESSO (Outlier Detection)

MR-PRESSO (Mendelian Randomization Pleiotropy RESidual Sum and Outlier) formally tests for and removes outlier instruments.

- **When to run**: When Cochran's Q test shows significant heterogeneity (p < 0.05)
- **Global test p < 0.05**: Significant outliers exist among instruments
- **Outlier test**: Identifies which specific SNPs are outliers
- **Distortion test**: Tests whether removing outliers significantly changes the IVW estimate
- **Outlier-corrected estimate**: IVW re-estimated after removing identified outliers
- **Important**: MR-PRESSO only detects outliers; biological investigation of flagged SNPs is still required

## Method Disagreement

When MR methods disagree, this warrants explicit discussion — not dismissal.

**Weighted Mode non-significant but others significant:**
- Weighted Mode has lower power than IVW or Weighted Median
- Non-significance may reflect low power rather than absence of effect
- However, if Weighted Mode points in the **opposite direction**, this is a stronger concern
- Always report and discuss — do not omit non-significant methods from the summary

**Discordant directions across methods:**
- If any method shows effect in the opposite direction to IVW, this is a red flag for pleiotropy
- Investigate the specific instruments driving the disagreement
- Consider MR-PRESSO to identify and remove pleiotropic outliers

## Binary Outcomes and Steiger Test

For binary (case-control) outcomes:

- **Default R² calculation assumes quantitative traits** — this is incorrect for binary outcomes
- **Correct approach**: Use `get_r_from_lor()` to convert log-odds ratios to R² on the liability scale
- **Requires**: Effect allele frequency, number of cases/controls, and population prevalence
- **If case/control info unavailable**: Flag that Steiger R² for the outcome may be inaccurate
- **Impact**: Incorrect R² can lead to wrong conclusions about causal direction

## Common Scenarios

### Scenario 1: Clean causal effect
- IVW significant, all methods agree, no heterogeneity, no pleiotropy, correct direction
- **Conclusion**: Strong evidence for causal effect

### Scenario 2: Heterogeneity but consistent direction
- IVW significant, methods agree on direction, Q p < 0.05, Egger intercept p > 0.05
- **Conclusion**: Likely causal but some instruments may act through other pathways; weighted median provides a more robust estimate

### Scenario 3: Directional pleiotropy detected
- IVW significant, Egger intercept p < 0.05, Egger slope differs from IVW
- **Conclusion**: IVW may be biased; if MR-Egger slope is significant, causality may still hold but effect size is uncertain. Consider MR-PRESSO for outlier removal.

### Scenario 4: Methods disagree on direction
- IVW positive, MR-Egger negative (or vice versa)
- **Conclusion**: Weak evidence; substantial pleiotropy likely. Do not claim causality.

### Scenario 5: Result driven by one SNP
- Leave-one-out shows one SNP dramatically changes the estimate
- **Conclusion**: Investigate that SNP's biology. If it's in a pleiotropic region, consider removing it and re-running.

### Scenario 6: Extreme heterogeneity with discordant outlier SNPs
- Cochran's Q p < 1e-10, single-SNP analysis reveals SNPs with opposite-direction effects
- MR-PRESSO identifies specific outlier instruments
- **Conclusion**: Run outlier-corrected analysis. Compare original vs corrected estimates. Investigate biology of outlier SNPs (e.g., pleiotropic loci like APOE). Report both estimates.

### Scenario 7: Weighted Mode disagrees with other methods
- IVW, MR-Egger, Weighted Median significant and concordant; Weighted Mode non-significant
- **Conclusion**: May reflect lower statistical power of Weighted Mode. If direction is concordant, causality is still supported. If direction is discordant, investigate pleiotropy. Always report explicitly.

## Caveats

1. **MR estimates reflect lifelong exposure** — genetic variants are fixed at conception, so MR estimates reflect the effect of long-term differences in exposure, not acute interventions
2. **Population-specific** — instruments may have different effects across ancestries
3. **Linear assumption** — standard MR assumes a linear dose-response relationship
4. **Cannot distinguish closely related traits** — if BMI and waist circumference share instruments, MR cannot determine which is the true causal factor
5. **Winner's curse** — selecting instruments from the same GWAS as estimation can inflate associations
6. **Sample overlap** — if exposure and outcome GWAS share participants, can introduce bias (use two-sample design to minimize)
