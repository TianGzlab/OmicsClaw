---
name: metabolomics-quantification
description: >-
  Feature quantification, missing value imputation, and normalization for metabolomics data.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [metabolomics, quantification, imputation, normalization]
metadata:
  omicsclaw:
    domain: metabolomics
    emoji: "📏"
    trigger_keywords: [metabolomics quantification, imputation, feature quantification, missing values]
---

# 📏 Metabolomics Quantification

Feature quantification with missing value imputation (min/median/KNN) and normalization (TIC/median/log).

## CLI Reference

```bash
python omicsclaw.py run met-quantify --demo
python omicsclaw.py run met-quantify --input <features.csv> --output <dir>
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--impute` | `min` | min, median, or knn |
| `--normalize` | `tic` | tic, median, or log |

## Why This Exists

- **Without it**: Downstream models crash when encountering missing LC/MS peak values
- **With it**: Recovers matrix completeness via K-Nearest Neighbors (KNN) or Median Imputation
- **Why OmicsClaw**: Centralized, reproducible preprocessing steps tailored for sparse metabolomic data

## Workflow

1. **Calculate**: Assess inherent missing value distributions per feature.
2. **Execute**: Impute empty values using the user-defined algorithm (KNN, Min, Median).
3. **Assess**: Apply normalization logic (TIC, MAD) to align global gradients.
4. **Generate**: Output structural completed data matrices.
5. **Report**: Produce imputation QC boxplots before and after correction.

## Example Queries

- "Impute missing values using KNN"
- "Normalize this feature table with TIC"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── quantified.csv
├── figures/
│   └── imputation_boxplot.png
├── tables/
│   └── imputed_matrix.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `peak-detection` — Upstream raw data matrix creation
- `met-diff` — Downstream univariate/multivariate testing

## Citations

- [NOREVA](https://doi.org/10.1093/nar/gkx449) — normalization evaluation
