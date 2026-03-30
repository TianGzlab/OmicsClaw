# MIQE 2.0 Guidelines for qPCR

**MIQE: Minimum Information for Publication of Quantitative Real-Time PCR Experiments**

**← Back to [SKILL.md](../SKILL.md) | See also:** [Code Examples](code_examples.md) | [Parameter Ranges](parameter_ranges.md) | [Best Practices](primer_design_best_practices.md)

This document provides a practical guide to the MIQE 2.0 guidelines (2025 revision) for designing, validating, and reporting qPCR experiments. Referenced from SKILL.md for qPCR-specific compliance requirements.

---

## Overview

The MIQE guidelines establish minimum standards for:
- Experimental design
- Sample preparation and quality
- qPCR assay design and validation
- Data analysis and normalization
- Transparent reporting

**Reference:** Bustin SA, et al. (2025) Clinical Chemistry 71(6):634-660

---

## Essential vs. Desirable Information

**Essential (E)**: Required for all publications
**Desirable (D)**: Recommended for complete transparency

---

## 1. Experimental Design

### Purpose and Application **(E)**
- Define biological question being addressed
- Specify qPCR application (gene expression, copy number, genotyping, etc.)
- State hypothesis being tested

### Experimental Design **(E)**
- **Biological replicates**: Minimum 3 independent samples
- **Technical replicates**: Minimum 2-3 per biological sample
- **Controls**: Positive controls, negative controls, no-template controls (NTCs)
- **Sample size justification**: Power analysis or pilot data

### Sample Information **(E)**
- **Description**: Cell type, tissue, organism, treatment conditions
- **Collection method**: Tissue dissection, cell culture, blood draw
- **Storage**: Temperature, duration, preservative (e.g., RNAlater)
- **Processing**: Homogenization method, time to processing

---

## 2. Sample Quality and Preparation

### RNA Quality **(E for RT-qPCR)**
- **Integrity**: RIN (RNA Integrity Number) ≥ 7 recommended
  - RIN 8-10: Excellent
  - RIN 7-8: Good
  - RIN 5-7: Marginal (document and justify)
  - RIN < 5: Poor (not recommended)
- **Quantification**: Spectrophotometry (260/280, 260/230 ratios)
  - 260/280: 1.8-2.0 (pure RNA)
  - 260/230: 2.0-2.2 (no organic contamination)
- **Method**: Bioanalyzer, TapeStation, gel electrophoresis

### DNA Quality **(E for qPCR)**
- **Integrity**: Gel electrophoresis (high molecular weight band)
- **Purity**: 260/280 ratio 1.8-2.0
- **Quantification**: Fluorometry (Qubit) or spectrophotometry

### Reverse Transcription **(E for RT-qPCR)**
- **RT enzyme**: Name, manufacturer, lot number
- **Priming method**: Oligo(dT), random primers, or gene-specific
- **RT conditions**: Temperature, time, reaction volume
- **RNA input**: Amount per reaction (typically 0.1-1 µg)
- **RT controls**:
  - **+RT**: Standard reaction
  - **-RT**: No enzyme control (checks for gDNA contamination)
  - **No template control**: Water instead of RNA

---

## 3. qPCR Assay Design

### Primer Design **(E)**
- **Sequences**: Disclose forward and reverse primer sequences
- **Location**: Gene name, accession number, exon positions
- **Amplicon length**: 70-140 bp (optimal for qPCR)
- **Primer length**: 18-22 nt
- **Tm**: 58-62°C, primers matched within 2°C
- **GC content**: 40-60%

### Exon-Spanning Design **(E for RT-qPCR)**
- Primers should span exon-exon junctions OR
- Intron size > 1 kb to avoid gDNA amplification
- Document exon positions

### Probe Design **(E for TaqMan)**
- **Sequence**: Disclose probe sequence
- **Location**: Between primers
- **Length**: 18-30 nt
- **Tm**: 5-10°C higher than primers (typically 65-70°C)
- **Fluorophore/quencher**: Specify dyes used

### In Silico Specificity **(E)**
- BLAST search confirms single target
- No significant off-target hits
- Document BLAST results

---

## 4. qPCR Assay Validation

### Specificity Verification **(E)**

**Melt Curve Analysis (SYBR Green):**
- Single, sharp peak indicates specific product
- Multiple peaks or broad peaks indicate non-specific products
- Document melt temperature

**Agarose Gel:**
- Single band at expected size
- No primer dimers or off-target products

**Sequencing (Desirable):**
- Sequence qPCR product to confirm identity

### Amplification Efficiency **(E)**

**Standard Curve:**
- **Dilution series**: 5-7 points, 5-10× dilutions
- **Concentration range**: Covering expected sample range
- **Template**: Pooled cDNA, plasmid, or synthetic oligo

**Efficiency Calculation:**
- E = 10^(-1/slope) - 1
- **Acceptable range**: 90-110% (optimal: 95-105%)
- Efficiency outside range indicates:
  - <90%: Inhibition, poor primer design, secondary structures
  - >110%: Primer dimers, contamination, pipetting errors

**R² (Linearity):**
- **Required**: R² ≥ 0.98
- Lower R² indicates inconsistent amplification

### Linear Dynamic Range **(E)**
- **Minimum**: 5 orders of magnitude (5 logs)
- Range over which efficiency is constant
- Document lowest and highest quantifiable concentrations

### Limit of Detection (LOD) **(D)**
- Lowest template amount giving consistent amplification
- Test with replicate dilutions near detection limit
- Report Cq variation at LOD

### Cq Variation **(E)**
- **Intra-assay**: CV < 5% (technical replicates)
- **Inter-assay**: CV < 10% (between runs)
- Document variation at different template levels

---

## 5. qPCR Protocol

### Reaction Conditions **(E)**

**Reaction Volume:**
- Typical: 10-20 µL
- State exact volume used

**Primer/Probe Concentrations:**
- **Primers**: 200-500 nM (optimize for each assay)
- **Probe**: 100-250 nM (for TaqMan)

**Template Amount:**
- **cDNA**: Equivalent of 10-100 ng total RNA
- **gDNA**: 10-100 ng per reaction

**Mastermix:**
- Name, manufacturer, catalog number
- Buffer composition (if custom)

### Cycling Protocol **(E)**

**Example Protocol:**
```
Initial denaturation:  95°C, 10 min
Amplification (40 cycles):
  Denaturation:  95°C, 15 sec
  Annealing/Extension: 60°C, 60 sec
Melt curve (SYBR): 60-95°C, 0.5°C increments
```

**Document:**
- All temperatures and times
- Number of cycles (typically 40-45)
- Ramp rates (if non-standard)

### Instrument **(E)**
- Manufacturer, model
- Software version
- Calibration/maintenance records **(D)**

---

## 6. Reference Genes (Normalization)

### Reference Gene Selection **(E)**

**Requirements:**
- Stable expression across all samples
- Similar abundance to target genes
- Not affected by experimental conditions

**Number of Reference Genes:**
- **Minimum**: 2-3 independent reference genes
- **Recommended**: 3-4 for critical experiments

**Common Reference Genes:**
- **Housekeeping genes**: GAPDH, ACTB, RPL13A, HPRT1, TBP
- **Tissue-specific**: Validate stability in your system

**Validation:**
- Test stability across all experimental conditions
- Use algorithms: geNorm, NormFinder, BestKeeper
- Report M-value (geNorm) or SD (NormFinder)

### Normalization Method **(E)**
- ΔΔCq method (most common)
- Relative quantification
- Absolute quantification (if standard curve available)

---

## 7. Data Analysis

### Cq Determination **(E)**
- **Method**: Automated threshold, manual threshold, second derivative
- **Threshold setting**: Fixed or per-run
- **Baseline correction**: Document method

### Quality Control **(E)**

**No-Template Controls (NTCs):**
- **Requirement**: Cq > 35 or undetected
- If Cq < 35: Check for contamination, primer dimers

**No-RT Controls (-RT):**
- **For RT-qPCR**: Cq > target +5 or undetected
- If amplification detected: gDNA contamination present

**Positive Controls:**
- Known template of defined concentration
- Verify assay performance

### Outlier Identification **(E)**
- **Method**: Grubbs' test, ROUT, visual inspection
- **Criteria**: Document how outliers identified and excluded
- **Transparency**: Report number of outliers removed

### Statistical Analysis **(E)**
- **Test used**: t-test, ANOVA, Mann-Whitney, etc.
- **Corrections**: Multiple testing correction (Bonferroni, FDR)
- **Significance level**: α = 0.05 typical
- **Sample size**: Document n for each group
- **Error bars**: State what they represent (SD, SEM, 95% CI)

---

## 8. Reporting Results

### Essential Information to Report

**In Materials & Methods:**
- Complete primer/probe sequences and locations
- qPCR protocol (mastermix, cycling conditions)
- Assay validation results (efficiency, R², specificity)
- Reference genes used and validation
- Normalization method
- Statistical tests

**In Results:**
- Cq values or fold-changes with error measures
- Number of biological and technical replicates
- Quality control results (NTCs, -RT controls)
- Outliers removed (if any)

**In Supplementary:**
- Raw Cq values (all replicates)
- Standard curves
- Melt curves or gel images
- Full MIQE checklist

---

## 9. MIQE Compliance Checklist

### Quick Validation Checklist

Before submitting primers for ordering:
- [ ] Primers 18-22 nt, GC 40-60%, Tm 58-62°C
- [ ] Amplicon 70-140 bp
- [ ] Primers span exon junction or intron > 1 kb
- [ ] In silico specificity check (BLAST)
- [ ] Primers within 2°C Tm

After receiving primers:
- [ ] Melt curve shows single peak
- [ ] Standard curve: E = 90-110%, R² > 0.98
- [ ] Linear range ≥ 5 logs
- [ ] NTCs show Cq > 35 or undetected
- [ ] -RT controls show Cq > target +5 or undetected
- [ ] Technical replicate CV < 5%

For publication:
- [ ] ≥ 3 biological replicates
- [ ] ≥ 2 technical replicates per sample
- [ ] ≥ 2 validated reference genes
- [ ] Complete methods section
- [ ] Raw data available (supplementary)
- [ ] MIQE checklist completed

---

## 10. Common MIQE Violations

### What NOT to Do

❌ **Single reference gene**: Use minimum 2-3
❌ **No efficiency validation**: Must report E and R²
❌ **No melt curve**: Required for SYBR Green assays
❌ **Insufficient replicates**: Minimum 3 biological, 2 technical
❌ **No primer sequences**: Must disclose sequences
❌ **Amplicon > 150 bp**: Reduces efficiency, use 70-140 bp
❌ **No NTC/−RT controls**: Required quality controls
❌ **No outlier handling**: Must document method
❌ **No statistical analysis**: Must report tests used

---

## 11. MIQE Checklist Template

Use this checklist to ensure compliance:

### Experimental Design
- [x] qPCR purpose specified
- [ ] Experimental design documented
- [ ] Sample size justified (n ≥ 3 biological replicates)

### Sample
- [ ] RNA/DNA quality verified (RIN, 260/280)
- [ ] Storage conditions documented
- [ ] RT protocol complete (for RT-qPCR)

### qPCR Target
- [x] Primer sequences provided
- [x] Amplicon length 70-140 bp
- [x] In silico specificity checked
- [ ] Empirical specificity verified (melt curve/gel/sequencing)

### qPCR Assay
- [ ] Standard curve: slope, efficiency, R²
- [ ] Linear dynamic range determined
- [ ] Cq variation reported
- [ ] LOD specified

### qPCR Protocol
- [ ] Complete reaction conditions
- [ ] Cycling parameters documented
- [ ] Instrument specified

### Data Analysis
- [ ] Cq determination method
- [ ] Outlier handling described
- [ ] Normalization method (reference genes)
- [ ] Statistical analysis described
- [ ] NTC and -RT results reported

---

## Resources

**Official MIQE Guidelines:**
- Original MIQE (2009): Bustin SA, et al. Clin Chem 55(4):611-622
- MIQE 2.0 (2025): Bustin SA, et al. Clin Chem 71(6):634-660

**Online Tools:**
- RDML (MIQE compliant data format): https://rdml.org/
- MIQE Guidelines Website: https://rdml.org/miqe.html

**Reference Gene Selection:**
- geNorm: https://genorm.cmgg.be/
- RefFinder: https://www.heartcure.com.au/reffinder/

---

**Last Updated:** 2026-01-28
**Based on:** MIQE 2.0 Guidelines (2025)
