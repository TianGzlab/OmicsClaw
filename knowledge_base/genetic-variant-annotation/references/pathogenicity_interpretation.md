# Pathogenicity Interpretation Guide

This document provides guidelines for interpreting variant pathogenicity using ACMG/AMP criteria and computational predictions.

---

## ACMG/AMP Classification Framework

The American College of Medical Genetics (ACMG) and Association for Molecular Pathology (AMP) published standards for variant interpretation in 2015.

### Classification Categories

| Category | Abbreviation | Clinical Interpretation |
|----------|-------------|------------------------|
| Pathogenic | P | Causes disease |
| Likely Pathogenic | LP | Probably causes disease (>90% certainty) |
| Uncertain Significance | VUS | Insufficient evidence |
| Likely Benign | LB | Probably does not cause disease |
| Benign | B | Does not cause disease |

---

## Evidence Categories

### Pathogenic Evidence

**Very Strong (PVS)**
- PVS1: Null variant (nonsense, frameshift, canonical ±1 or 2 splice sites, initiation codon, single or multi-exon deletion) in a gene where LOF is a known mechanism of disease

**Strong (PS)**
- PS1: Same amino acid change as established pathogenic variant
- PS2: De novo variant (maternity and paternity confirmed)
- PS3: Well-established functional studies show damaging effect
- PS4: Prevalence in affected individuals statistically higher than controls

**Moderate (PM)**
- PM1: Located in mutational hot spot or critical functional domain
- PM2: Absent from controls or extremely low frequency
- PM3: Detected in trans with a pathogenic variant for recessive disorder
- PM4: Protein length change due to inframe indels or stop-loss
- PM5: Novel missense at amino acid position where different missense change is pathogenic
- PM6: Assumed de novo (without confirmation of paternity/maternity)

**Supporting (PP)**
- PP1: Co-segregation with disease in multiple affected family members
- PP2: Missense in gene with low rate of benign missense variants
- PP3: Multiple lines of computational evidence support deleterious effect
- PP4: Patient's phenotype highly specific for gene
- PP5: Reputable source recently reports variant as pathogenic

### Benign Evidence

**Stand-alone (BA)**
- BA1: Allele frequency > 5% in population databases

**Strong (BS)**
- BS1: Allele frequency greater than expected for disorder
- BS2: Observed in healthy individuals in reputable database
- BS3: Well-established functional studies show no damaging effect
- BS4: Lack of segregation in affected members

**Supporting (BP)**
- BP1: Missense in gene where truncating is disease mechanism
- BP2: Observed in trans with pathogenic variant in fully penetrant dominant gene
- BP3: Inframe indels in repetitive region without known function
- BP4: Multiple lines of computational evidence suggest no impact
- BP5: Found in case with alternate molecular basis
- BP6: Reputable source recently reports variant as benign
- BP7: Synonymous variant with no predicted splice impact

---

## Combining Evidence

### Rules for Pathogenic

| Combination | Classification |
|-------------|----------------|
| 1 PVS1 + 1 PS1-4 | Pathogenic |
| 1 PVS1 + ≥2 PM1-6 | Pathogenic |
| 1 PVS1 + 1 PM1-6 + 1 PP1-5 | Pathogenic |
| ≥2 PS1-4 | Pathogenic |
| 1 PS1-4 + ≥3 PM1-6 | Pathogenic |
| 1 PS1-4 + 2 PM1-6 + ≥2 PP1-5 | Pathogenic |
| 1 PS1-4 + 1 PM1-6 + ≥4 PP1-5 | Pathogenic |

### Rules for Likely Pathogenic

| Combination | Classification |
|-------------|----------------|
| 1 PVS1 + 1 PM1-6 | Likely Pathogenic |
| 1 PS1-4 + 1-2 PM1-6 | Likely Pathogenic |
| 1 PS1-4 + ≥2 PP1-5 | Likely Pathogenic |
| ≥3 PM1-6 | Likely Pathogenic |
| 2 PM1-6 + ≥2 PP1-5 | Likely Pathogenic |
| 1 PM1-6 + ≥4 PP1-5 | Likely Pathogenic |

### Rules for Benign/Likely Benign

| Combination | Classification |
|-------------|----------------|
| 1 BA1 | Benign |
| ≥2 BS1-4 | Benign |
| 1 BS1-4 + 1 BP1-7 | Likely Benign |
| ≥2 BP1-7 | Likely Benign |

---

## Computational Prediction Tools

### SIFT (Sorting Intolerant From Tolerant)

**Purpose:** Predicts whether amino acid substitution affects protein function

**Score Range:** 0-1
- ≤ 0.05: Deleterious
- > 0.05: Tolerated

**Method:** Sequence homology-based; assumes important positions are conserved

**Limitations:**
- Lower accuracy for variants in poorly conserved regions
- Cannot predict gain-of-function

**ACMG Application:** Supporting evidence (PP3/BP4)

### PolyPhen-2 (Polymorphism Phenotyping v2)

**Purpose:** Predicts impact of amino acid substitutions

**Score Range:** 0-1
- 0.000-0.446: Benign
- 0.447-0.908: Possibly damaging
- 0.909-1.000: Probably damaging

**Method:** Combines sequence, structure, and functional information

**Limitations:**
- Trained primarily on Mendelian disease variants
- May be biased toward human disease-causing mutations

**ACMG Application:** Supporting evidence (PP3/BP4)

### CADD (Combined Annotation Dependent Depletion)

**Purpose:** Integrates multiple annotations into single score

**Score Range:** 1-40+ (Phred-scaled)
- < 10: Likely benign
- 10-20: Uncertain
- 20-30: Likely damaging
- > 30: Highly likely damaging

**Interpretation:**
- CADD > 10: Top 10% most deleterious variants
- CADD > 20: Top 1%
- CADD > 30: Top 0.1%

**Advantages:**
- Scores all variants (not just missense)
- Integrates many data sources

**ACMG Application:** Supporting evidence (PP3/BP4)

### REVEL (Rare Exome Variant Ensemble Learner)

**Purpose:** Missense variant pathogenicity prediction

**Score Range:** 0-1
- < 0.3: Likely benign
- 0.3-0.5: Uncertain
- > 0.5: Likely pathogenic
- > 0.75: Highly likely pathogenic

**Method:** Ensemble of 13 tools including SIFT, PolyPhen, MutationTaster

**Advantages:**
- Higher accuracy than individual tools
- Specific for missense variants
- Well-validated on ClinVar data

**Recommendation:** Use REVEL > 0.5 as moderate evidence (can upgrade PP3 to PM2-like)

**ACMG Application:** Supporting to moderate evidence (PP3 or PM-level)

### MutationTaster

**Purpose:** Evaluates disease-causing potential

**Predictions:**
- Disease causing
- Disease causing (automatic)
- Polymorphism
- Polymorphism (automatic)

**Method:** Integrates conservation, splice sites, protein features

**ACMG Application:** Supporting evidence (PP3/BP4)

### SpliceAI

**Purpose:** Predicts splice-altering variants

**Score Range:** 0-1 (delta score)
- > 0.8: High confidence splice-altering
- 0.5-0.8: Medium confidence
- 0.2-0.5: Low confidence
- < 0.2: No splice effect

**Applications:**
- Exonic variants creating cryptic splice sites
- Intronic variants disrupting splicing
- Synonymous variants affecting splicing

**ACMG Application:** Functional evidence (PS3/BS3 if validated)

---

## Population Frequency Interpretation

### gnomAD (Genome Aggregation Database)

**Content:** 141,456 individuals, ~1 billion variants

**Populations:**
- African/African American (AFR)
- Latino/Admixed American (AMR)
- Ashkenazi Jewish (ASJ)
- East Asian (EAS)
- Finnish (FIN)
- Non-Finnish European (NFE)
- South Asian (SAS)
- Other (OTH)

### Frequency Thresholds

| AF Threshold | Interpretation | ACMG Criteria |
|-------------|----------------|---------------|
| > 5% | Common variant, likely benign | BA1 (Benign) |
| 1-5% | Common, unlikely disease-causing | BS1 (Strong benign) |
| 0.1-1% | Low frequency, consider disorder | PM2 if absent |
| < 0.1% | Rare, consistent with disease | PM2 |
| Absent | Very rare or de novo | PM2 |

**Important considerations:**
- Check relevant population (not just global AF)
- Consider disease prevalence and penetrance
- Recessive disorders tolerate higher AF than dominant
- X-linked recessive: check hemizygous males specifically

---

## ClinVar Integration

### ClinVar Review Status

| Stars | Review Status | Reliability |
|-------|--------------|-------------|
| ★★★★ | Practice guideline | Highest |
| ★★★ | Expert panel | High |
| ★★ | Multiple submitters, no conflicts | Moderate |
| ★ | Multiple submitters, conflicts | Low-Moderate |
| - | Single submitter | Low |
| - | No assertion | No information |

### Using ClinVar Classifications

**Pathogenic/Likely Pathogenic:**
- ≥2 stars: Strong evidence (PS1 or PM5 if same amino acid)
- 1 star: Supporting evidence (PP5)

**Benign/Likely Benign:**
- ≥2 stars: Strong evidence (BS1)
- 1 star: Supporting evidence (BP6)

**Conflicting Interpretations:**
- Review individual submissions
- Check review status and evidence
- May remain VUS until resolved

---

## Clinical Interpretation Workflow

### Step 1: Assess Variant Consequence

```
HIGH impact (stop_gained, frameshift, splice_site)
    ↓
Consider PVS1 (if LOF is disease mechanism)

MODERATE impact (missense, inframe indel)
    ↓
Assess with computational predictions

LOW/MODIFIER impact
    ↓
Usually benign unless affects splicing/regulation
```

### Step 2: Check Population Frequency

```
AF > 5% → Likely Benign (BA1)
AF 1-5% → Benign evidence (BS1)
AF < 0.1% → Supports pathogenic (PM2)
```

### Step 3: Computational Evidence

```
Missense variant:
    REVEL > 0.5 + CADD > 20 → PP3
    Multiple tools deleterious → PP3
    Multiple tools benign → BP4
```

### Step 4: ClinVar/Literature

```
Check ClinVar for same/similar variants
    Pathogenic (≥2 stars) → PS1/PM5/PP5
    Benign (≥2 stars) → BS1/BP6
    Conflicting → Investigate further
```

### Step 5: Combine Evidence

```
Apply ACMG combining rules
    → Pathogenic
    → Likely Pathogenic
    → VUS
    → Likely Benign
    → Benign
```

---

## Special Considerations

### Loss-of-Function Variants (PVS1)

**Apply PVS1 when ALL true:**
1. Variant is null (stop_gained, frameshift, splice_site, start_lost)
2. LOF is established mechanism for gene
3. Variant is not in last exon or escapes NMD
4. No evidence of alternative rescue mechanism

**Do NOT apply PVS1 if:**
- LOF not established mechanism (e.g., haploinsufficiency uncertain)
- Variant in last exon and likely escapes NMD
- Gene has many benign LOF variants in population
- Alternative start codon likely used

### Missense Variants

**Upgrade to PM1 if in:**
- Functional domain (catalytic site, binding site)
- Mutational hot spot
- Highly conserved region critical for function

**Examples:**
- Kinase active site
- DNA binding domain
- Receptor binding pocket

### Splice Variants

**Canonical splice sites (±1,2):**
- Usually PVS1 if affects donor (GT) or acceptor (AG)
- Check if exon is in-frame (may be PM4 instead)
- Use SpliceAI to confirm prediction

**Splice region (±3-8):**
- Usually PP3 with computational evidence
- May upgrade to PM-level with SpliceAI > 0.5
- Consider functional validation

---

## Common Pitfalls

### Over-reliance on Single Tool

❌ **Incorrect:** "CADD > 20, therefore pathogenic"

✓ **Correct:** "CADD > 20 provides supporting evidence (PP3) when combined with other criteria"

### Ignoring Population Frequency

❌ **Incorrect:** Classifying stop_gained as pathogenic without checking gnomAD

✓ **Correct:** Check frequency first; AF > 5% → Benign regardless of consequence

### Misapplying PVS1

❌ **Incorrect:** Applying PVS1 to all stop_gained variants

✓ **Correct:** Check if:
- LOF is disease mechanism
- Not in last exon
- No rescue mechanisms

### Upgrading Evidence Without Justification

❌ **Incorrect:** Upgrading PP3 to PM-level based on high CADD alone

✓ **Correct:** Evidence strength defined by ACMG; follow guidelines unless strong justification

---

## Resources

### Databases
- ClinVar: https://www.ncbi.nlm.nih.gov/clinvar/
- gnomAD: https://gnomad.broadinstitute.org/
- COSMIC: https://cancer.sanger.ac.uk/cosmic
- HGMD: http://www.hgmd.cf.ac.uk/

### Prediction Tools
- CADD: https://cadd.gs.washington.edu/
- REVEL: https://sites.google.com/site/revelgenomics/
- SpliceAI: https://spliceailookup.broadinstitute.org/
- dbNSFP: https://sites.google.com/site/jpopgen/dbNSFP

### Guidelines
- ACMG/AMP 2015: Richards S, et al. Genet Med. 2015;17(5):405-424
- ClinGen SVI: https://clinicalgenome.org/working-groups/sequence-variant-interpretation/
