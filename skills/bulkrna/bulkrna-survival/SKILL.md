---
name: bulkrna-survival
description: >-
  Survival analysis for bulk RNA-seq — Kaplan-Meier curves, Cox proportional hazards, expression-based patient stratification.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, survival, Kaplan-Meier, Cox, hazard-ratio, clinical]
requires: [numpy, pandas, matplotlib, scipy]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "📈"
    trigger_keywords: [survival, Kaplan-Meier, Cox, prognosis, hazard ratio, overall survival, clinical outcome]
    allowed_extra_flags:
      - "--clinical"
      - "--cutoff-method"
      - "--genes"
    legacy_aliases: [bulk-survival]
    saves_h5ad: false
---

# Bulk RNA-seq Survival Analysis

Expression-based survival analysis for clinical bulk RNA-seq datasets. Stratifies patients by gene expression (median split or optimal cutoff), generates Kaplan-Meier plots, computes log-rank tests, and fits Cox proportional hazards models.

## Core Capabilities

- Median-split or optimal-cutoff patient stratification by gene expression
- Kaplan-Meier survival curves with confidence intervals
- Log-rank test for comparing survival between expression groups
- Cox proportional hazards regression (univariate and multivariate)
- Multi-gene signature scoring and survival association
- Forest plot of hazard ratios for multiple genes

## Why This Exists

- **Without it**: Researchers must combine expression data with clinical metadata in R, use the `survival`/`survminer` packages, manually iterate over genes, and create separate plots — often requiring significant R expertise.
- **With it**: A single Python command performs expression-stratified survival analysis with Kaplan-Meier curves, log-rank tests, and Cox regression from a count matrix and clinical metadata file.
- **Why OmicsClaw**: Pure Python implementation using `lifelines` (optional) with built-in fallback to scipy-based log-rank, integrated into the OmicsClaw reporting framework.

## Algorithm / Methodology

### Kaplan-Meier Estimation
1. Sort patients by event time
2. Compute survival probability at each time point: S(t) = ∏(1 - d_i/n_i)
3. Greenwood's formula for confidence intervals

### Log-Rank Test
- Compare survival distributions between high/low expression groups
- Chi-square test statistic with 1 degree of freedom

### Cox Proportional Hazards
- Model: h(t|x) = h₀(t) × exp(β₁x₁ + β₂x₂ + ...)
- Estimates hazard ratios and 95% confidence intervals
- Concordance index (C-index) for model assessment

### Patient Stratification
- **Median split**: Divide at median expression value
- **Optimal cutoff**: Maximize log-rank statistic across all possible cutpoints

## Landmark Survival

When median survival is not reached (KM curve never crosses 50%), landmark survival rates are more robust. The system automatically computes S(t) with 95% CI at fixed time points (e.g., 1yr, 3yr, 5yr).

## Clinical Validity Checks

| Check | Threshold | Action |
|-------|-----------|--------|
| **Events Per Variable (EPV)** | < 10 | Warns about potential overfitting in multi-gene models |
| **Heavy censoring** | > 80% censored | Warns that KM tail estimates are unreliable |
| **Median not reached** | KM never crosses 50% | Reports "Not reached" and uses landmark survival instead |

### EPV Guideline

| EPV | Reliability |
|-----|-------------|
| >= 20 | Very stable estimates |
| 10-20 | Adequate for most analyses |
| 5-10 | Interpret with caution |
| < 5 | Potentially severely overfitted |

Rule of thumb: no more than 1 gene per 10 events in the dataset.

## Input Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Expression matrix | `.csv` | Genes as rows, samples as columns |
| Clinical data | `.csv` | Must contain `sample`, `time` (in months/days), `event` (0/1) columns |

## CLI Reference

```bash
python omicsclaw.py run bulkrna-survival --demo
python omicsclaw.py run bulkrna-survival --input expr.csv --clinical clinical.csv --genes TP53,BRCA1 --output results/
python bulkrna_survival.py --demo --output /tmp/survival_demo
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── km_GENE1.png
│   ├── km_GENE2.png
│   └── forest_plot.png
├── tables/
│   ├── survival_results.csv
│   └── cox_results.csv
└── reproducibility/
    └── commands.sh
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--input` | — | Path to expression matrix CSV |
| `--clinical` | — | Path to clinical data CSV |
| `--genes` | — | Comma-separated gene list to analyze |
| `--cutoff-method` | `median` | Stratification: `median` or `optimal` |
| `--output` | — | Output directory |
| `--demo` | — | Run with demo data |

## Safety

- **Local-first**: All processing runs locally; no data is uploaded.
- **Disclaimer**: Every report includes the standard OmicsClaw disclaimer.
- **Clinical data sensitivity**: No PHI is transmitted; all data stays on local filesystem.

## Integration with Orchestrator

**Chaining partners**:
- `bulkrna-de` — Upstream: provides candidate genes for survival analysis
- `bulkrna-enrichment` — Parallel: genes associated with survival → pathway enrichment
- `bulkrna-ppi-network` — Downstream: survival-associated genes → PPI network

## Citations

- [Kaplan-Meier](https://doi.org/10.1080/01621459.1958.10501452) — Kaplan & Meier, JASA 1958
- [Cox PH](https://doi.org/10.1111/j.2517-6161.1972.tb00899.x) — Cox, JRSSB 1972
- [lifelines](https://doi.org/10.21105/joss.01317) — Davidson-Pilon, JOSS 2019

## Dependencies

**Required**: numpy, pandas, scipy, matplotlib
**Optional**: lifelines (enhanced KM curves, Cox regression, C-index)

## Related Skills

- `bulkrna-de` — Differential expression upstream
- `bulkrna-enrichment` — Pathway enrichment of survival-associated genes
