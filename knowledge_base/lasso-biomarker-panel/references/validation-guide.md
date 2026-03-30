# Multi-Cohort Validation Design Guide

## Validation Hierarchy (Strongest to Weakest)

1. **Independent cohort, different platform** — e.g., RNA-seq discovery → microarray validation (gold standard)
2. **Independent cohort, same platform** — different study site, same technology
3. **Temporal split** — train on earlier samples, validate on later samples
4. **Nested cross-validation** — internal, unbiased AUC estimation (minimum acceptable)

## Cross-Platform Validation

When discovery and validation use different platforms (e.g., RNA-seq vs Affymetrix):

### Gene Symbol Mapping
1. Map platform-specific IDs to common gene symbols
2. For multi-probe genes: keep probe with highest variance
3. Intersect discovery and validation gene symbol sets
4. Only matched features are used for validation

### Expected Feature Loss
- RNA-seq to Affymetrix: typically 70-85% overlap in gene symbols
- RNA-seq to Olink proteomics: 0-5% overlap (different molecular types)
- Same platform: 95-100% overlap

### Handling Missing Panel Features
If some panel features are missing in validation:
- Report how many features survived mapping
- Model still works with partial features (glmnet handles this)
- AUC may be lower due to reduced information
- If >50% of features missing, results should be interpreted with caution

## Study Design Recommendations

### Minimum Sample Sizes
| Design | Discovery | Validation | Total |
|--------|-----------|------------|-------|
| Exploratory | ≥50 | ≥30 | ≥80 |
| Confirmatory | ≥100 | ≥50 | ≥150 |
| Regulatory | ≥200 | ≥100 | ≥300 |

### Class Balance
- Aim for ≥30% minority class in both cohorts
- Use class-balanced sampling in CV splits (done automatically by `run_lasso_panel`)
- Severely imbalanced data (>90/10) may need SMOTE or weighted LASSO

## Example: Breast Cancer Discovery → GSE32646 Validation

This skill's breast cancer demo demonstrates cross-cohort, same-platform validation:

| Property | Discovery (GSE25055) | Validation (GSE32646) |
|----------|----------------------|----------------------|
| Disease | Breast cancer | Breast cancer |
| Platform | Affymetrix U133A | Affymetrix |
| Samples | ~218 | ~115 |
| Outcome | Basal vs Luminal A subtype | Pathologic complete response |
| Treatment | Various chemotherapy | Paclitaxel + FEC |

**Why this is a useful validation:**
- Same platform — high gene overlap, minimal mapping loss
- Different cohort — independent patient population
- Related but distinct endpoint — tests generalizability of molecular features

## Example: UNIFI → PURSUIT UC Validation

An alternative IBD cross-drug validation design:

| Property | Discovery (GSE206285) | Validation (GSE92415) |
|----------|----------------------|----------------------|
| Disease | Ulcerative Colitis | Ulcerative Colitis |
| Platform | Affymetrix HT HG-U133+ PM | Same platform family |
| Samples | ~542 | ~87 |
| Outcome | Week 8 mucosal healing | Week 6 mucosal healing |
| Drug | Ustekinumab | Golimumab |

**Why this is a strong validation:**
- Different drug (anti-IL-12/23 vs anti-TNF) — tests general response biology
- Same disease and platform — isolates drug-independent signal
- Different trial — independent patient population

## Multi-Cohort Framework

Following Cruchaga/Western et al. (preprint 2024) — 6-cohort, 3,107-sample design:

1. **Discovery cohort** — largest, most homogeneous. Train LASSO here.
2. **Internal validation** — subset of same study. Nested CV provides this.
3. **External validation 1** — same disease, different study.
4. **External validation 2** — related disease (cross-disease).
5. **External validation 3** — different platform (cross-platform).
6. **External validation 4** — different population (cross-demographic).

Each additional validation layer strengthens the evidence for clinical utility.


---
