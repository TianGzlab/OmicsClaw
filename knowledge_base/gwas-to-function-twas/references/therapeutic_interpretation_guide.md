## Therapeutic Interpretation Guide for TWAS Directionality

**Purpose:** This guide explains how to interpret TWAS directionality to determine whether genes should be inhibited or activated for therapeutic benefit, with frameworks for confidence assessment and target validation.

**Last Updated:** 2026-01-28

---

## Table of Contents

1. [Understanding TWAS Directionality](#understanding-twas-directionality)
2. [Multi-Layer Directional Analysis](#multi-layer-directional-analysis)
3. [Confidence Assessment Framework](#confidence-assessment-framework)
4. [Causal Inference with Mendelian Randomization](#causal-inference-with-mendelian-randomization)
5. [Real-World Success Stories](#real-world-success-stories)
6. [Common Pitfalls and Red Flags](#common-pitfalls-and-red-flags)
7. [Decision Framework for Drug Modality](#decision-framework-for-drug-modality)

---

## Understanding TWAS Directionality

### What is TWAS Directionality?

TWAS (Transcriptome-Wide Association Study) identifies genes whose genetically regulated expression is associated with a trait. The **direction** of this association tells us whether higher expression increases or decreases the trait value.

**Key concept:** TWAS Z-score (or effect size) indicates direction:
- **Positive Z-score (+)**: Higher predicted expression → Higher trait value
- **Negative Z-score (−)**: Higher predicted expression → Lower trait value

### Translating Direction to Therapeutic Strategy

The therapeutic strategy depends on both the TWAS direction **and** the trait nature:

#### For Risk Traits (Higher is Bad)

Examples: Disease risk, LDL cholesterol, blood pressure

| TWAS Direction | Interpretation | Therapeutic Strategy |
|----------------|----------------|---------------------|
| **Positive (+)** | Higher expression → Higher risk | **INHIBIT** expression |
| **Negative (−)** | Higher expression → Lower risk (protective) | **ACTIVATE** expression |

**Example 1: IL6R and Cardiovascular Disease**
- TWAS Z = +4.5 (positive)
- Higher IL6R expression → Higher CAD risk
- **Therapeutic strategy: INHIBIT IL6R** (Tocilizumab, IL-6 receptor antagonist)

**Example 2: APOE and Alzheimer's Disease**
- TWAS Z = −4.2 (negative)
- Higher APOE expression → Lower AD risk
- **Therapeutic strategy: ACTIVATE APOE** (challenging - gene therapy, enhancers)

#### For Protective/Beneficial Traits (Higher is Good)

Examples: HDL cholesterol, bone density, cognitive function

| TWAS Direction | Interpretation | Therapeutic Strategy |
|----------------|----------------|---------------------|
| **Positive (+)** | Higher expression → Higher beneficial outcome | **ACTIVATE** expression |
| **Negative (−)** | Higher expression → Lower beneficial outcome | **INHIBIT** expression |

#### For Quantitative Traits (Context-Dependent)

Examples: Height, gene expression levels, metabolite levels

- Strategy depends on clinical context
- Determine if increasing or decreasing the trait is therapeutically desired

---

## Multi-Layer Directional Analysis

### Why Multi-Layer Analysis?

TWAS alone shows association between predicted expression and trait, but doesn't confirm the full causal pathway. Multi-layer analysis validates directionality by checking consistency across:

1. **eQTL layer**: Genetic variant → Gene expression
2. **TWAS layer**: Predicted expression → Trait
3. **Combined pathway**: Genetic variant → Expression → Trait

### Three-Layer Pathway Validation

#### Layer 1: eQTL Direction (Variant → Expression)

**Question:** Does the risk allele increase or decrease gene expression?

- Extract lead eQTL variant for the gene
- Determine which allele is associated with trait risk (from GWAS)
- Check if risk allele increases or decreases expression (from eQTL)

**Example (IL6R):**
```
Lead eQTL SNP: rs2228145
Risk allele: C (increases CAD risk)
eQTL effect: C allele → Increased IL6R expression
eQTL direction: Risk allele INCREASES expression
```

#### Layer 2: TWAS Direction (Expression → Trait)

**Question:** Does higher predicted expression increase or decrease the trait?

- From TWAS Z-score or effect size
- Positive Z = higher expression → higher trait value
- Negative Z = higher expression → lower trait value

**Example (IL6R):**
```
TWAS Z-score: +4.5
TWAS direction: Higher expression INCREASES CAD risk
```

#### Layer 3: Combined Pathway

**Question:** Is the full causal pathway consistent?

Combine layers 1 and 2 to determine the full pathway:

```
Risk Allele → Expression Change → Trait Change
```

**Consistency patterns:**

| eQTL Direction | TWAS Direction | Pathway | Consistency | Therapeutic Strategy |
|----------------|----------------|---------|-------------|---------------------|
| ↑ Expression | ↑ Trait | Risk allele → ↑ Expr → ↑ Risk | ✅ Consistent | **INHIBIT** |
| ↓ Expression | ↑ Trait | Risk allele → ↓ Expr → ↑ Risk | ✅ Consistent | **ACTIVATE** |
| ↑ Expression | ↓ Trait | Risk allele → ↑ Expr → ↓ Risk | ⚠️ Paradoxical | Investigate |
| ↓ Expression | ↓ Trait | Risk allele → ↓ Expr → ↓ Risk | ❌ Inconsistent | Recheck alleles |

**IL6R Complete Example:**
```
Layer 1 (eQTL): Risk allele (rs2228145-C) → ↑ IL6R Expression
Layer 2 (TWAS): ↑ IL6R Expression → ↑ CAD Risk
Combined Pathway: Risk allele → ↑ IL6R → ↑ CAD Risk
Consistency: ✅ Fully consistent
Therapeutic Strategy: INHIBIT IL6R expression
Confidence: HIGH
```

### Interpreting Paradoxical or Inconsistent Patterns

**Paradoxical pattern (opposite directions across layers):**

Possible explanations:
1. **Feedback regulation**: Gene expression is subject to compensatory mechanisms
2. **Tissue-specific effects**: eQTL in one tissue, TWAS in another
3. **Developmental timing**: Expression effects vary across lifespan
4. **Complex regulation**: Gene has multiple regulatory pathways with opposing effects

**Action:** Requires deeper investigation before therapeutic recommendation.

**Inconsistent pattern (directions don't make biological sense):**

Likely causes:
1. **Allele harmonization error**: Check effect allele alignment between datasets
2. **LD artifact**: TWAS hit is not the causal gene (check colocalization)
3. **Pleiotropy**: Gene affects trait through multiple pathways
4. **Statistical artifact**: Spurious association

**Action:** Resolve technical issues before proceeding with therapeutic interpretation.

---

## Confidence Assessment Framework

### Three-Tier Confidence System

#### **High Confidence**

Requirements:
- ✅ Strong TWAS association (p < genome-wide significance)
- ✅ Strong colocalization (PP.H4 > 0.8)
- ✅ Consistent directionality across eQTL + TWAS layers
- ✅ (Optional) MR causal evidence (p < 0.05, no pleiotropy)

**Interpretation:** Strong evidence for causal gene-trait relationship. Proceed with therapeutic strategy.

**Example:** IL6R → CAD (TWAS p=1e-6, PP.H4=0.92, consistent pathway, MR p=1e-5)

#### **Medium Confidence**

Requirements:
- ✅ Significant TWAS association (p < 0.001)
- ⚠️ Moderate colocalization (PP.H4 = 0.5-0.8) OR missing colocalization
- ✅ Directional consistency
- ❌ MR not performed or inconclusive

**Interpretation:** Likely causal relationship, but some uncertainty remains. Consider as candidate target pending additional validation.

**Example:** SORT1 → LDL (TWAS p=5e-4, PP.H4=0.65, consistent)

#### **Low Confidence**

Requirements:
- ⚠️ Nominally significant TWAS (p < 0.05)
- ❌ Poor colocalization (PP.H4 < 0.5) OR not assessed
- ❌ Inconsistent directionality OR not assessed
- ❌ Weak MR instruments (F < 10) OR MR shows pleiotropy

**Interpretation:** Association may be spurious or due to LD. Not recommended for therapeutic targeting without further validation.

**Action:** Deprioritize unless biological rationale is very strong.

### Confidence Scoring Matrix

| Evidence Type | Weight | Scoring |
|---------------|--------|---------|
| **TWAS significance** | 30% | −log₁₀(p-value) / 10, capped at 1.0 |
| **Colocalization** | 30% | PP.H4 value (0-1 scale) |
| **MR causal evidence** | 20% | −log₁₀(MR p-value) / 10, capped at 1.0 |
| **Druggability** | 20% | Protein class score (see druggability guide) |

**Composite confidence score:**
```
Confidence = 0.3 × TWAS_score + 0.3 × Coloc_score + 0.2 × MR_score + 0.2 × Drug_score
```

**Interpretation:**
- **Score ≥ 0.7**: High confidence target
- **Score 0.5-0.7**: Medium confidence target
- **Score < 0.5**: Low confidence target

---

## Causal Inference with Mendelian Randomization

### Why MR Strengthens Directionality Evidence

TWAS identifies associations, but associations can be:
1. **Causal**: Gene expression directly influences trait
2. **Reverse causation**: Trait affects gene expression
3. **Confounding**: Shared factors affect both expression and trait

**Mendelian Randomization (MR)** uses genetic variants as instrumental variables to test causality, addressing confounding and reverse causation.

### MR Assumptions for Valid Inference

**Three core assumptions:**

1. **Relevance**: Genetic variants (eQTLs) are strongly associated with gene expression
   - Check: F-statistic > 10 (strong instruments)

2. **Independence**: Genetic variants are independent of confounders
   - Assumed true due to random inheritance (Mendel's laws)

3. **Exclusion restriction**: Genetic variants affect trait **only** through gene expression (no horizontal pleiotropy)
   - Check: MR-Egger intercept test (p > 0.05 = no pleiotropy)

### Interpreting MR Results

#### Significant MR Causal Effect

**IVW p-value < 0.05** suggests gene expression causally affects trait.

**Direction interpretation:**
- **Positive MR beta**: ↑ Expression causally increases trait
- **Negative MR beta**: ↑ Expression causally decreases trait

**Effect size interpretation:**
```
MR beta = 0.15 for CAD risk
Interpretation: 1 SD increase in gene expression causes 15% increase in CAD risk
Therapeutic implication: Inhibiting expression by 1 SD could reduce CAD risk by 15%
```

#### Checking MR Assumption Violations

**Pleiotropy tests:**

1. **MR-Egger intercept test**
   - Null hypothesis: No directional pleiotropy (intercept = 0)
   - If p < 0.05: Pleiotropy detected, IVW estimate may be biased
   - Action: Use MR-Egger slope (less powerful) or MR-PRESSO to remove outliers

2. **Heterogeneity test (Cochran's Q)**
   - Tests whether causal estimates vary across instruments
   - If Q p-value < 0.05: Heterogeneity present
   - Action: Use random-effects IVW or investigate heterogeneity sources

3. **Method consistency**
   - Compare IVW, weighted median, MR-Egger, weighted mode
   - If all methods agree on direction: Strong evidence
   - If methods disagree: Assumption violations likely, interpret cautiously

#### MR Sensitivity Analysis Example

```
Gene: PCSK9
Outcome: LDL cholesterol

IVW:             beta = +0.22, p = 1e-8   ✅ Significant, positive
Weighted Median: beta = +0.19, p = 2e-5   ✅ Consistent direction
MR-Egger:        beta = +0.18, p = 0.03   ✅ Consistent (weaker signal)
MR-Egger intercept: 0.01, p = 0.45        ✅ No pleiotropy detected
Cochran's Q:     p = 0.12                 ✅ No heterogeneity

Interpretation: Strong causal evidence that PCSK9 expression increases LDL.
Therapeutic strategy: INHIBIT PCSK9 (validated by Evolocumab, Alirocumab success)
Confidence: HIGH
```

### When MR is Essential vs. Optional

**MR is ESSENTIAL for:**
- High-stakes drug development decisions (large investment)
- Genes with weak colocalization (PP.H4 < 0.8)
- Conflicting signals from other evidence sources
- Genes with known pleiotropic effects

**MR is OPTIONAL (TWAS + colocalization sufficient) for:**
- Exploratory target discovery
- Strong colocalization already present (PP.H4 > 0.9)
- Rapid screening of many targets
- Limited resources (MR is time-intensive)

---

## Real-World Success Stories

### Example 1: IL6R and Inflammation

**GWAS Finding:**
- rs2228145 (Asp358Ala missense variant) associated with lower CRP and lower CAD risk

**TWAS Analysis:**
- Higher IL6R expression → Higher inflammation markers
- TWAS Z = +4.5, p = 1e-6

**Directionality:**
- Layer 1 (eQTL): Protective allele → Increased soluble IL6R (competitive inhibitor)
- Layer 2 (TWAS): Higher IL6R signaling → Higher inflammation
- Pathway: Protective allele → ↑ sIL6R → ↓ IL6 signaling → ↓ Inflammation
- Strategy: **INHIBIT IL6R signaling**

**Clinical Validation:**
- **Tocilizumab** (IL-6 receptor antagonist)
- Approved for rheumatoid arthritis, giant cell arteritis
- Validated TWAS-based therapeutic strategy

**Confidence:** VERY HIGH (genetic + clinical evidence)

---

### Example 2: PCSK9 and LDL Cholesterol

**GWAS Finding:**
- Loss-of-function variants in PCSK9 → Lower LDL cholesterol, lower CAD risk

**TWAS Analysis:**
- Higher PCSK9 expression → Higher LDL cholesterol
- TWAS Z = +3.8, p = 2e-5
- Colocalization PP.H4 = 0.88

**Directionality:**
- Layer 1 (eQTL): Risk allele → Higher PCSK9 expression
- Layer 2 (TWAS): Higher PCSK9 → Higher LDL
- Pathway: Risk allele → ↑ PCSK9 → ↑ LDL degradation → ↑ LDL levels
- Strategy: **INHIBIT PCSK9**

**Mendelian Randomization:**
- IVW: beta = +0.22 SD LDL per SD PCSK9, p = 1e-8
- No pleiotropy detected (MR-Egger intercept p = 0.45)

**Clinical Validation:**
- **Evolocumab, Alirocumab** (PCSK9 inhibitors)
- Blockbuster drugs approved for hypercholesterolemia
- Reduce LDL by 50-60%, reduce CVD events by 15-20%

**Confidence:** VERY HIGH (genetic + MR + clinical evidence)

---

### Example 3: HMGCR and Statins

**TWAS Analysis:**
- Higher HMGCR expression → Higher LDL cholesterol
- TWAS Z = +3.2, p = 5e-5

**Directionality:**
- HMGCR encodes HMG-CoA reductase (rate-limiting enzyme in cholesterol synthesis)
- Higher expression → More cholesterol production → Higher LDL
- Strategy: **INHIBIT HMGCR enzyme**

**Clinical Validation:**
- **Statins** (Atorvastatin, Simvastatin, etc.)
- Most prescribed cardiovascular drugs worldwide
- HMGCR inhibitors reduce LDL by 30-50%

**Confidence:** VERY HIGH (validated mechanism)

---

## Common Pitfalls and Red Flags

### Pitfall 1: Ignoring Colocalization

**Problem:** Up to 50% of TWAS hits are LD artifacts where GWAS and eQTL signals have distinct causal variants in the same region.

**Red flag:** TWAS association present, but PP.H4 < 0.5

**Solution:** Always perform colocalization testing. Only trust TWAS hits with PP.H4 > 0.8.

---

### Pitfall 2: Allele Harmonization Errors

**Problem:** Effect alleles not properly aligned between eQTL and GWAS data, leading to incorrect directionality.

**Red flag:** Directionality is inconsistent across layers, or pathway doesn't make biological sense.

**Solution:**
- Carefully harmonize effect alleles (flip beta signs when alleles are reversed)
- Remove ambiguous SNPs (A/T, G/C) that can't be strand-aligned
- Use automated harmonization tools (e.g., TwoSampleMR R package)

---

### Pitfall 3: Weak MR Instruments

**Problem:** eQTL associations are weak (F-statistic < 10), leading to weak instrument bias in MR.

**Red flag:** F-statistic < 10, very wide confidence intervals in MR

**Solution:**
- Use more liberal p-value threshold for instrument selection (e.g., p < 5e-5 instead of 5e-8)
- Use larger eQTL studies (GTEx v8 preferred over smaller cohorts)
- Consider using TWAS predicted expression as instrument instead of individual SNPs

---

### Pitfall 4: Horizontal Pleiotropy

**Problem:** eQTL variants affect the trait through pathways other than gene expression, violating MR assumptions.

**Red flag:**
- MR-Egger intercept p < 0.05
- Large heterogeneity (Cochran's Q p < 0.05)
- IVW and weighted median/MR-Egger show opposite directions

**Solution:**
- Use MR-PRESSO to detect and remove outlier SNPs
- Report MR-Egger and weighted median as sensitivity analyses
- If pleiotropy persists, acknowledge limitation and interpret cautiously

---

### Pitfall 5: Tissue Mismatch

**Problem:** eQTL data from non-disease-relevant tissue may not reflect expression changes in target tissue.

**Red flag:** TWAS signal only present in tissue unrelated to disease pathophysiology.

**Example:** Liver eQTL used for brain disease → expression regulation may differ in brain

**Solution:**
- Use disease-relevant tissues (e.g., brain eQTL for neurological diseases)
- If tissue-specific eQTL unavailable, use cross-tissue meta-analysis (S-MultiXcan)
- Validate expression directionality in disease-relevant tissue with experimental data

---

### Pitfall 6: Reverse Causation

**Problem:** Disease affects gene expression, not the other way around.

**Red flag:** eQTL was measured in case-control study (disease status may affect expression).

**Solution:**
- Use eQTL from healthy populations (GTEx is healthy donors)
- MR naturally addresses reverse causation (genetic variants precede disease)
- If eQTL from cases, acknowledge potential for reverse causation

---

## Decision Framework for Drug Modality

### Inhibition Strategies (Easier)

**When to use:** TWAS shows higher expression increases disease risk (positive Z, risk trait)

**Drug modalities:**

1. **Small molecule inhibitors**
   - Best for: Enzymes, kinases, GPCRs, ion channels
   - Pros: Oral bioavailability, easier development
   - Cons: Off-target effects if selectivity is poor
   - **Example:** Statins (HMGCR inhibitors)

2. **Monoclonal antibodies**
   - Best for: Secreted proteins, cell surface receptors
   - Pros: High specificity, long half-life
   - Cons: IV/SC administration, expensive
   - **Example:** Tocilizumab (anti-IL6R), Evolocumab (anti-PCSK9)

3. **RNA interference (RNAi) / Antisense oligonucleotides (ASO)**
   - Best for: Liver-expressed genes, "undruggable" targets
   - Pros: Target any gene, high specificity
   - Cons: Delivery challenges, expensive
   - **Example:** Inclisiran (PCSK9 siRNA)

4. **CRISPR/gene editing (future)**
   - Best for: Permanent gene knockdown
   - Pros: One-time treatment, permanent effect
   - Cons: Delivery, off-target editing, regulatory hurdles

**Druggability ranking:** Kinases/Enzymes > GPCRs > Ion Channels > Secreted Proteins > Transcription Factors

---

### Activation Strategies (Harder)

**When to use:** TWAS shows higher expression decreases disease risk (negative Z, risk trait)

**Drug modalities:**

1. **Small molecule agonists/activators**
   - Best for: GPCRs, nuclear receptors, enzymes
   - Pros: Oral bioavailability
   - Cons: Fewer druggable targets for activation
   - **Example:** GLP-1 agonists (activate GLP1R for diabetes)

2. **Gene therapy / overexpression**
   - Best for: Loss-of-function diseases, monogenic conditions
   - Pros: Permanent expression increase
   - Cons: Delivery challenges, immunogenicity, very expensive
   - **Example:** Factor IX gene therapy for hemophilia B

3. **Protein replacement therapy**
   - Best for: Secreted proteins, enzymes
   - Pros: Direct supplementation
   - Cons: Frequent dosing, expensive, immunogenicity
   - **Example:** Enzyme replacement for lysosomal storage diseases

4. **Indirect activation (pathway agonism)**
   - Best for: When direct activation is not feasible
   - Pros: May be easier than direct activation
   - Cons: Less specific, potential for off-target effects
   - **Example:** Increase APOE by activating LXR pathway

**Activation is generally harder than inhibition** because:
- Fewer druggable mechanisms for increasing function
- Risk of toxicity from over-activation
- Delivery challenges for gene/protein therapy

**Strategic consideration:** If TWAS suggests activation, also consider:
1. Can we inhibit a **negative regulator** of the gene instead?
2. Can we target a **downstream pathway** that the gene activates?
3. Is the gene's function **enzyme-like** (easier to supplement)?

---

## Summary: Therapeutic Interpretation Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  TWAS Hit Identified                                            │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Check Colocalization                                   │
│  → PP.H4 > 0.8?  Yes → Proceed    No → Likely LD artifact      │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 2: Multi-Layer Directional Analysis                      │
│  → Extract eQTL direction (risk allele → expression)            │
│  → Extract TWAS direction (expression → trait)                  │
│  → Check consistency across layers                              │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 3: Determine Therapeutic Strategy                        │
│  → Positive TWAS + Risk trait → INHIBIT                         │
│  → Negative TWAS + Risk trait → ACTIVATE                        │
│  → Check biological plausibility                                │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 4 (Optional): Mendelian Randomization                    │
│  → Establish causal directionality                              │
│  → Check F-statistic > 10 (strong instruments)                  │
│  → Test pleiotropy (MR-Egger intercept)                         │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 5: Assess Confidence Level                               │
│  → High: Strong TWAS + Coloc + Consistent + (MR)                │
│  → Medium: Moderate evidence, needs validation                  │
│  → Low: Weak evidence, deprioritize                             │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Step 6: Druggability Assessment                               │
│  → Protein class (kinase, GPCR, enzyme?)                        │
│  → Known drugs in class?                                        │
│  → Inhibition vs activation feasibility                         │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Final Output: Therapeutic Target Report                       │
│  → Gene                                                          │
│  → Therapeutic strategy (Inhibit/Activate)                      │
│  → Confidence level (High/Medium/Low)                           │
│  → Drug modality recommendations                                │
│  → Priority score                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## References

1. Nelson MR, et al. (2015) The support of human genetic evidence for approved drug indications. *Nat Genet* 47:856-860.
2. King EA, et al. (2019) Are drug targets with genetic support twice as likely to be approved? *PLoS Genet* 15:e1008489.
3. Gusev A, et al. (2016) Integrative approaches for large-scale transcriptome-wide association studies. *Nat Genet* 48:245-252.
4. Hemani G, et al. (2018) The MR-Base platform supports systematic causal inference across the human phenome. *eLife* 7:e34408.
5. Giambartolomei C, et al. (2014) Bayesian test for colocalisation between pairs of genetic association studies. *PLoS Genet* 10:e1004383.
6. Swerdlow DI, et al. (2016) Selecting instruments for Mendelian randomization in the wake of genome-wide association studies. *Int J Epidemiol* 45:1600-1616.

---

**Document Version:** 1.0
**Last Updated:** 2026-01-28
**Maintainer:** Claude Code Workflow Development
