# TWAS Hub Validation Guide

This document provides guidance on validating your TWAS results against published studies from TWAS Hub.

---

## What is TWAS Hub?

[TWAS Hub](http://twas-hub.org/) is a centralized database aggregating published TWAS results across multiple traits and tissues. It allows researchers to:
- **Validate findings**: Compare your results to published studies
- **Identify replication**: Assess which genes replicate known associations
- **Discover novelty**: Identify genes not previously reported
- **Check concordance**: Verify effect directions match published studies

---

## Key Distinction

- **Expression weights** (GTEx v8, PredictDB): Pre-computed prediction models used by all TWAS studies
- **TWAS associations** (TWAS Hub): Pre-computed gene-trait association results from specific published studies

Your analysis computes **fresh TWAS associations** using your GWAS data + shared expression weights.

---

## When to Use TWAS Hub Validation

**Use when:**
- Your trait is available in TWAS Hub (common diseases/traits)
- Publishing results (shows replication of known associations)
- Prioritizing novel vs. known discoveries
- Comparing power to previous studies

**Skip when:**
- Novel trait not in TWAS Hub
- Time-sensitive exploratory analysis
- Using TWAS only for hypothesis generation

---

## Interpretation Guidelines

### Replication Rate

- **>70%**: Strong validation - findings align with literature
- **40-70%**: Moderate - may reflect differences in:
  - Ancestry populations
  - Sample size
  - Phenotype definitions
- **<40%**: Low - investigate potential issues

### Novel Discoveries

Genes significant in your study but not in published TWAS:
- May represent true biological discoveries
- Could reflect increased statistical power
- Warrant follow-up validation with colocalization/MR

### Effect Concordance

Proportion of replicated genes with same effect direction:
- **>80%**: Expected for well-powered studies
- **<80%**: Suggests allele harmonization issues or population differences

---

## Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Low replication | Different trait definitions | Check phenotype compatibility |
| Effect discordance | Allele flip | Re-check allele harmonization |
| All genes novel | Trait mismatch | Verify correct trait ID |
| No overlap | Different tissues | Confirm tissue matches |

---

**Last Updated:** 2026-01-28


---
