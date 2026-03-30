# TWAS Troubleshooting Guide

Common issues and solutions for FUSION and S-PrediXcan TWAS analyses.

---

## GWAS Summary Statistics Issues

### Issue: Genomic Inflation (λGC > 1.1)

**Symptoms:** QQ plot shows early departure from expected line

**Causes:**
- Population stratification
- Batch effects
- Cryptic relatedness

**Solutions:**
1. Run LDSC intercept test (see [ldsc_qc_guidelines.md](ldsc_qc_guidelines.md))
2. If Ratio > 0.15, re-run GWAS with more PCs
3. Apply LDSC intercept correction as last resort

---

### Issue: Allele Alignment Errors

**Symptoms:** Warning messages about allele mismatches, unexpected effect directions

**Causes:**
- Reference/alternate allele flipped between GWAS and reference panel
- Different strand orientation
- Ambiguous strand SNPs (A/T, G/C)

**Solutions:**
```python
from scripts.validate_gwas_sumstats import harmonize_alleles

gwas_harmonized = harmonize_alleles(
    gwas_df,
    reference_panel="1000G_EUR",
    remove_ambiguous=True  # Remove A/T and G/C SNPs
)
```

---

### Issue: Missing Data in GWAS

**Symptoms:** Large portions of genome missing, low SNP coverage

**Causes:**
- Strict QC filters
- Poor imputation quality
- Array-specific coverage gaps

**Solutions:**
- Re-impute with TOPMed or 1000G Phase 3 reference
- Lower INFO score filter (≥ 0.6 acceptable for TWAS)
- Check that GWAS and LD reference have compatible SNP sets

---

## TWAS Analysis Issues

### Issue: No Significant Genes

**Symptoms:** All TWAS P-values > Bonferroni threshold

**Causes:**
- Underpowered GWAS (small N)
- Trait not mediated by expression
- Wrong tissue selected

**Solutions:**
1. Check GWAS power (expect genome-wide significant hits)
2. Try FDR correction instead of Bonferroni (more liberal)
3. Run LDSC tissue enrichment to identify relevant tissues
4. Consider S-MultiXcan to aggregate across tissues

---

### Issue: Too Many Significant Genes (Hundreds)

**Symptoms:** Hundreds of genome-wide significant genes

**Causes:**
- Genomic inflation in GWAS
- Population stratification propagating to TWAS
- Highly polygenic trait (normal for some traits)

**Solutions:**
1. Check LDSC intercept - if Ratio > 0.15, fix GWAS confounding first
2. Inspect QQ plot for excessive inflation
3. If GWAS is clean, many genes may be real (e.g., height, BMI)

---

### Issue: Poor Colocalization (Low PP.H4)

**Symptoms:** Most TWAS hits have PP.H4 < 0.5

**Interpretation:** This is common - up to 50% of TWAS hits are LD artifacts

**Solutions:**
- **Filter genes with PP.H4 > 0.8** for high-confidence targets
- Use conditional analysis to identify independent signals
- Focus on genes with strong colocalization for drug targeting

---

### Issue: Conflicting Directionality

**Symptoms:** eQTL and TWAS effect directions disagree

**Causes:**
- Allele harmonization error
- Complex regulation (feedback loops)
- Tissue-specific effects

**Solutions:**
1. Re-check allele alignment in GWAS and eQTL data
2. Verify risk allele definition
3. If alignment is correct, may indicate complex biology

---

## Tool-Specific Issues

### FUSION Errors

#### "Error: No genes in weight file"

**Cause:** Weight file path incorrect or chromosome mismatch

**Solution:**
```bash
# Check weight file exists
ls weights/GTEx_v8/GTEx.Artery_Coronary.pos

# Verify chromosome format matches (e.g., "chr1" vs "1")
head gwas_sumstats.txt
```

#### "LD reference not found"

**Cause:** LD reference panel path incorrect

**Solution:**
```bash
--ref_ld_chr LDREF/1000G.EUR.
# Note: Include "1000G.EUR." as prefix, FUSION adds chromosome number
```

#### Memory Error

**Cause:** Large LD regions loading into memory

**Solution:**
- Run chromosomes separately
- Increase RAM allocation
- Use `--LDblocks` to limit LD window size

---

### S-PrediXcan Errors

#### "No genes imputed"

**Cause:** SNP ID format mismatch between GWAS and weights database

**Solution:**
```bash
# Check SNP ID formats
head gwas_sumstats.txt  # e.g., "rs123456" or "chr1:12345"
sqlite3 weights.db "SELECT * FROM weights LIMIT 5"

# Reformat GWAS SNP IDs to match database format
```

#### "Allele mismatch warnings"

**Cause:** Effect/non-effect allele definitions differ

**Solution:**
```python
# Harmonize alleles before S-PrediXcan
gwas_harmonized = harmonize_alleles(gwas_df, reference_panel="1000G_EUR")
```

---

## Mendelian Randomization Issues

### Issue: Weak Instrument (F-statistic < 10)

**Symptoms:** MR estimates are unstable, wide confidence intervals

**Causes:**
- Too few eQTL SNPs as instruments
- Weak eQTL associations

**Solutions:**
- Relax eQTL P-value threshold to get more instruments
- Use expression prediction models as instruments (TWAS approach)
- If F < 10 persists, MR not appropriate for this gene

---

### Issue: Pleiotropy Detected

**Symptoms:** MR-Egger intercept P < 0.05

**Interpretation:** Instruments may affect trait through pathways other than gene expression

**Solutions:**
- Use MR-PRESSO to remove outlier SNPs
- Try weighted median MR (more robust to pleiotropy)
- Interpret results with caution

---

## Performance Issues

### Issue: TWAS Taking Too Long

**Symptoms:** FUSION running >24 hours per tissue

**Solutions:**
- Parallelize by chromosome (run chr1-22 in parallel)
- Use S-PrediXcan instead (10-100x faster)
- Use only BSLMM model in FUSION (skip lasso/enet)
- Pre-filter GWAS to HapMap3 SNPs only

---

### Issue: Out of Memory

**Symptoms:** R/Python killed, memory error messages

**Solutions:**
- Run fewer tissues simultaneously
- Process chromosomes separately
- Use S-PrediXcan (lower memory footprint)
- Increase swap space or run on HPC cluster

---

## Data Interpretation Issues

### Issue: Gene Not in Database

**Symptoms:** TWAS skips genes of interest

**Causes:**
- Gene not expressed in selected tissue
- Poor prediction R² in training data (excluded)

**Solutions:**
- Try alternative tissues
- Check GTEx portal for gene expression patterns
- Some genes cannot be imputed (non-coding, low expression)

---

### Issue: Cross-Tissue Inconsistency

**Symptoms:** Gene significant in one tissue only

**Interpretation:** May reflect true tissue-specific regulation

**Solutions:**
- Validate with biological knowledge of trait
- Run S-MultiXcan to see if signal strengthens
- Check if tissue matches known disease biology

---

## Getting Help

If issues persist:

1. **FUSION**: https://github.com/gusevlab/fusion_twas/issues
2. **MetaXcan/S-PrediXcan**: https://github.com/hakyimlab/MetaXcan/issues
3. **COLOC**: https://github.com/chr1swallace/coloc/issues
4. **LDSC**: https://github.com/bulik/ldsc/issues

---

**Last Updated:** 2026-01-28
