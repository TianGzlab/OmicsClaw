# LDSC QC Guidelines for GWAS Summary Statistics

This document provides detailed guidance on interpreting LDSC (LD Score Regression) intercept tests to distinguish polygenicity from population stratification in GWAS summary statistics.

---

## Overview

LDSC intercept analysis is the gold standard for assessing whether genomic inflation (λGC > 1) in GWAS results is due to:
- **Polygenicity**: True polygenic architecture (many small-effect variants)
- **Confounding**: Population stratification, batch effects, or cryptic relatedness

**Key principle:** LDSC separates these two sources of inflation by leveraging LD patterns.

---

## Running LDSC Intercept Test

### Basic Command

```bash
python ldsc.py \
  --h2 gwas_sumstats.txt \
  --ref-ld-chr eur_w_ld_chr/ \
  --w-ld-chr eur_w_ld_chr/ \
  --out gwas_qc
```

### Required Input Format

GWAS summary statistics must have these columns:
- `SNP`: rsID or chr:pos
- `A1`: Effect allele
- `A2`: Reference allele
- `Z`: Z-score (or compute from BETA/SE)
- `N`: Sample size
- `P`: P-value (optional)

### LD Score Files

Download from LDSC website:
- **EUR**: European LD scores (1000 Genomes EUR)
- **EAS**: East Asian LD scores
- **AFR**: African LD scores

Use LD scores that match your GWAS ancestry.

---

## Interpreting LDSC Output

### Key Metrics

1. **LDSC Intercept**: Estimated intercept from LD score regression
2. **Intercept SE**: Standard error of intercept estimate
3. **Ratio**: Proportion of inflation due to confounding

### Output Example

```
Mean chi^2 = 1.456
Lambda GC = 1.392
Intercept: 1.023 (0.008)
Ratio: 0.086 (0.032)
```

---

## Interpretation Guidelines

### Intercept Values

| Intercept | Ratio | Interpretation | Action |
|-----------|-------|----------------|--------|
| **≈ 1.0** | < 0.10 | ✅ **Good quality** - Inflation is polygenic | Proceed with analysis |
| **1.0-1.05** | 0.10-0.15 | ⚠️ **Acceptable** - Mostly polygenic, minor confounding | Acceptable for TWAS |
| **1.05-1.10** | 0.15-0.30 | ⚠️ **Moderate issues** - Substantial confounding | Consider re-QC or apply intercept correction |
| **> 1.10** | > 0.30 | ❌ **Poor quality** - High confounding | Re-QC GWAS before TWAS |

### Ratio Interpretation

**Ratio = (Intercept - 1) / (λGC - 1)**

- **Ratio < 0.10**: Less than 10% of inflation due to confounding (excellent)
- **Ratio = 0.10-0.30**: 10-30% confounding (acceptable)
- **Ratio > 0.30**: More than 30% confounding (problematic)

---

## Common Scenarios

### Scenario 1: High λGC, Low Intercept (Good)

```
Lambda GC = 1.5
Intercept = 1.02
Ratio = 0.04
```

**Interpretation**: High inflation is due to polygenicity (many true associations), not confounding.

**Action**: ✅ Proceed with TWAS - this is ideal for well-powered polygenic traits.

### Scenario 2: Moderate λGC, High Intercept (Bad)

```
Lambda GC = 1.2
Intercept = 1.12
Ratio = 0.60
```

**Interpretation**: Most inflation is due to confounding, not true polygenic signal.

**Action**: ❌ **Do not proceed** with TWAS until confounding is resolved.

**Possible causes:**
- Population stratification (insufficient PC adjustment)
- Batch effects
- Cryptic relatedness
- Genotyping errors

**Solutions:**
1. Re-run GWAS with more principal components
2. Check for batch effects
3. Filter samples with high relatedness
4. Apply genomic control correction

### Scenario 3: Low λGC, Intercept ≈ 1 (Underpowered)

```
Lambda GC = 1.02
Intercept = 1.00
Ratio = 0.00
```

**Interpretation**: No inflation - either well-controlled or underpowered GWAS.

**Action**:
- Check sample size (N > 5,000 recommended)
- If N is large, trait may be weakly heritable
- TWAS may have limited power to detect associations

---

## When LDSC Detects Confounding

### Step 1: Identify Source of Confounding

Common sources:
1. **Population stratification**
   - Check PCA plots for outliers
   - Increase number of PCs in GWAS model
   - Consider restricting to homogeneous ancestry

2. **Batch effects**
   - Check for genotyping batch differences
   - Include batch covariates in GWAS

3. **Cryptic relatedness**
   - Use KING or PLINK to identify related samples
   - Remove one sample from each related pair (pi-hat > 0.2)

4. **Low-quality genotypes**
   - Stricter QC filters (call rate > 99%, HWE p > 1e-6)
   - Remove low-quality samples

### Step 2: Apply Corrections

**Option A: Re-run GWAS** (preferred)
- Fix underlying QC issues
- Re-run association analysis with corrected data

**Option B: Apply LDSC Intercept Correction** (if re-running not feasible)
- Divide chi-square statistics by LDSC intercept
- `chi2_corrected = chi2_observed / intercept`
- Updates P-values to remove confounding inflation

---

## LDSC for Different Ancestries

### European Ancestry

Use EUR LD scores (most common):
```bash
--ref-ld-chr eur_w_ld_chr/
```

### East Asian Ancestry

Use EAS LD scores:
```bash
--ref-ld-chr eas_ldscores/
```

### African Ancestry

Use AFR LD scores:
```bash
--ref-ld-chr afr_ldscores/
```

### Admixed or Multi-Ancestry

- Use LD scores matching the largest ancestry component
- Or compute custom LD scores from your study population

---

## Integration with TWAS Workflow

### When to Run LDSC Intercept QC

**Timing**: Before running TWAS (Step 1 of workflow)

**Why critical for TWAS**:
- TWAS inherits GWAS confounding
- Population stratification can cause false positive gene associations
- LDSC ensures GWAS is clean before imputing gene expression

### Decision Tree

```
Run LDSC Intercept Test
         |
         ├─> Ratio < 0.15? ──> ✅ Proceed with TWAS
         |
         └─> Ratio ≥ 0.15? ──> ⚠️ Investigate confounding
                                    |
                                    ├─> Can re-QC GWAS? ──> Re-run GWAS ──> Repeat LDSC
                                    |
                                    └─> Cannot re-QC? ──> Apply intercept correction ──> Proceed with caution
```

---

## Advanced: Partitioned LDSC for Tissue Selection

For rigorous tissue selection (recommended for Tier 2+ analyses), use LDSC partitioned heritability:

**See [gwas-heritability-ldsc](../../gwas-heritability-ldsc/) workflow** for:
- Identifying tissues enriched for trait heritability
- Statistical evidence for tissue relevance
- Data-driven tissue recommendations for TWAS

This provides unbiased tissue selection compared to biology-based assumptions.

---

## References

- **LDSC Method**: Bulik-Sullivan BK, et al. (2015) LD Score regression distinguishes confounding from polygenicity in genome-wide association studies. *Nat Genet* 47:291-295. [doi:10.1038/ng.3211](https://doi.org/10.1038/ng.3211)

- **Partitioned Heritability**: Finucane HK, et al. (2015) Partitioning heritability by functional annotation using genome-wide association summary statistics. *Nat Genet* 47:1228-1235. [doi:10.1038/ng.3404](https://doi.org/10.1038/ng.3404)

---

**Last Updated:** 2026-01-28
