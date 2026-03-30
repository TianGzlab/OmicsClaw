# Multiple Testing Correction Guide

This document provides comprehensive guidance on choosing and applying multiple testing correction methods for genomics experiments.

---

## Why Multiple Testing Correction?

### The Multiple Testing Problem

**Key insight:** When testing many hypotheses simultaneously, some will appear significant by chance even if no true effects exist.

**Example:**
- Test 20,000 genes for differential expression at α = 0.05
- If NO genes are truly DE, expect 1,000 false positives (5% of 20,000)
- Without correction, results are mostly noise

**Genomics scale:**
- RNA-seq: ~15,000-20,000 gene tests
- ATAC-seq: ~50,000-150,000 peak tests
- Methylation arrays: ~450,000-850,000 CpG tests
- GWAS: ~500,000-10,000,000 SNP tests

### Type I Error (False Positive)

**Definition:** Rejecting null hypothesis when it's actually true (claiming effect when none exists)

**Family-Wise Error Rate (FWER):**
- Probability of making ≥1 false positive among all tests
- With m independent tests at α = 0.05: FWER = 1 - (0.95)^m
- For m = 20: FWER ≈ 0.64 (64% chance of false positive)
- For m = 100: FWER ≈ 0.994 (virtually guaranteed false positive)

**Consequence:** Need more stringent thresholds to control error rate

---

## Multiple Testing Correction Methods

### Bonferroni Correction

**Method:** Divide α by number of tests

**Formula:** α_corrected = α / m, where m = number of tests

**Example:**
- 20,000 tests, α = 0.05
- Bonferroni threshold: 0.05 / 20,000 = 2.5 × 10^-6
- Reject null if p < 2.5 × 10^-6

**Properties:**
✅ Controls FWER (probability of ANY false positive)
✅ Very simple and transparent
✅ Makes no assumptions about test dependence
❌ Extremely conservative (low power)
❌ Many false negatives (misses true effects)
❌ Not recommended for genomics (too stringent)

**When to use:**
- Small number of tests (m < 100)
- Candidate gene studies where FWER control critical
- Situations where false positives very costly

### Benjamini-Hochberg FDR

**Method:** Control False Discovery Rate (expected proportion of false positives among discoveries)

**FDR Definition:** E[FP / (FP + TP)] where FP = false positives, TP = true positives

**Procedure:**
1. Order p-values: p_(1) ≤ p_(2) ≤ ... ≤ p_(m)
2. Find largest k where: p_(k) ≤ (k/m) × α
3. Reject hypotheses 1, 2, ..., k

**Example:**
- α = 0.05 (control FDR at 5%)
- If 1000 genes called significant, expect ~50 are false positives
- But 950 are likely true positives

**Properties:**
✅ Much more powerful than Bonferroni
✅ Optimal under independence
✅ Still controls error rate under positive dependence
✅ Standard choice for genomics
✅ Balances false positives and false negatives well

**When to use:**
- Standard choice for RNA-seq, ATAC-seq, ChIP-seq
- When you can tolerate some false positives
- Exploratory discovery experiments
- Most published genomics studies

**R implementation:**
```r
adjusted_p <- p.adjust(pvalues, method = "BH")
significant <- adjusted_p < 0.05
```

### q-value (Storey's Method)

**Method:** Enhanced FDR estimation accounting for proportion of true nulls

**Key innovation:** Estimates π0 (proportion of truly null hypotheses) from p-value distribution

**Advantage over BH:**
- If π0 < 1 (some true effects exist), more powerful than BH
- Provides q-value (minimum FDR at which test is significant)
- More accurate FDR estimates

**Properties:**
✅ More powerful than BH when many true effects
✅ Provides interpretable q-values
✅ Handles positive dependence
❌ Requires good p-value calibration
❌ Can be unstable with small sample sizes

**When to use:**
- RNA-seq with expected many DE genes (>10%)
- Large sample sizes (n ≥ 5 per group)
- When BH is too conservative

**R implementation:**
```r
library(qvalue)
qobj <- qvalue(p = pvalues)
qvalues <- qobj$qvalues
significant <- qvalues < 0.05
```

### Independent Hypothesis Weighting (IHW)

**Method:** Data-driven weighting that increases power by upweighting more promising tests

**Key innovation:** Uses covariate (e.g., mean expression) to prioritize hypotheses without looking at p-values

**How it works:**
1. Stratify tests by covariate (mean expression, peak strength, etc.)
2. Learn optimal weights for each stratum using independent data
3. Weight hypotheses before FDR correction
4. Higher weight = higher priority = more power to detect

**Properties:**
✅ Can increase discoveries by 10-50% over BH
✅ Still controls FDR rigorously
✅ Uses information in data without inflating error
✅ Works with DESeq2, edgeR outputs
❌ Requires careful covariate selection
❌ More complex than BH

**When to use:**
- RNA-seq when mean expression varies widely
- ATAC-seq when peak strengths vary
- Any setting with informative covariate
- Want maximum power while controlling FDR

**R implementation:**
```r
library(IHW)
ihw_res <- ihw(
  pvalues = pvalues,
  covariates = mean_expression,  # Must be independent of p-value under null
  alpha = 0.05
)
significant <- adj_pvalues(ihw_res) < 0.05
```

**Important:** Covariate must be independent of p-value under null hypothesis
- ✅ Good: Mean expression (independent of DE status under null)
- ✅ Good: Peak width, GC content (independent of accessibility)
- ❌ Bad: Effect size (correlated with p-value)
- ❌ Bad: Test statistic (directly related to p-value)

### Local FDR (lfdr)

**Method:** Estimates probability that each specific test is a false positive

**Distinction from FDR:**
- FDR: Expected proportion of FP among all rejections (global)
- lfdr: Probability that THIS specific test is FP (local)

**Properties:**
✅ Provides test-specific error estimates
✅ Can be more powerful in some settings
❌ Requires good p-value density estimation
❌ Less commonly used in practice
❌ Harder to interpret

**When to use:**
- Prioritizing individual genes for follow-up
- Want error estimate for each specific test
- Comfortable with Bayesian interpretation

---

## Choosing a Multiple Testing Method

### Decision Framework

```
┌─────────────────────────────────────────────────┐
│ How many tests?                                 │
└───────────────┬─────────────────────────────────┘
                │
        ┌───────┴───────┐
        │               │
    < 100 tests    ≥ 100 tests
        │               │
   Bonferroni      ┌────┴────┐
   or BH-FDR       │         │
                   │    Genomic scale
                   │    (1000s-100000s)
                   │         │
                   │    ┌────┴─────┐
                   │    │          │
              Want maximum    Standard
              power?           approach?
                   │          │
                   │          │
              Use IHW    Use BH-FDR
              (if have         │
              covariate)       │
                         (Most common)
```

### Method Comparison Table

| Method | FWER/FDR | Power | Complexity | Best For |
|--------|----------|-------|------------|----------|
| **Bonferroni** | FWER | Very Low | Simple | Candidate genes (m < 100) |
| **BH-FDR** | FDR | Moderate | Simple | Standard genomics (default) |
| **q-value** | FDR | Moderate-High | Moderate | Large effect size expected |
| **IHW** | FDR | High | Moderate | Want maximum power |
| **Local FDR** | FDR | Moderate-High | Complex | Prioritizing specific tests |

### Recommendations by Assay

**Bulk RNA-seq:**
- **Standard:** BH-FDR at q < 0.05 or q < 0.1
- **Higher power:** IHW with mean expression as covariate
- **Conservative:** q-value if many DE genes expected

**Single-cell RNA-seq:**
- **Standard:** BH-FDR at q < 0.05
- **Cell type markers:** BH-FDR at q < 0.01 (more stringent)
- **Avoid:** Very stringent thresholds (power already low due to dropout)

**ATAC-seq:**
- **Standard:** BH-FDR at q < 0.05
- **Higher power:** IHW with peak signal strength as covariate
- **Conservative:** BH-FDR at q < 0.01 for high-confidence peaks

**ChIP-seq:**
- **Narrow peaks:** BH-FDR at q < 0.05 (or q < 0.01 for TF binding)
- **Broad peaks:** BH-FDR at q < 0.1 (more lenient, broader features)
- **Differential binding:** BH-FDR at q < 0.05

**Methylation:**
- **Array (450K/EPIC):** BH-FDR at q < 0.05 (or IHW)
- **WGBS:** BH-FDR at q < 0.01 (millions of tests, be more stringent)

**GWAS:**
- **Genome-wide:** Bonferroni at p < 5 × 10^-8 (traditional threshold)
- **Candidate regions:** BH-FDR at q < 0.05

---

## Significance Thresholds

### Common FDR Thresholds

**q < 0.05 (5% FDR):**
- Standard for most genomics applications
- Balance between sensitivity and specificity
- Among 1000 discoveries, expect ~50 false positives
- **Recommended as default**

**q < 0.1 (10% FDR):**
- More lenient, higher power
- Useful for exploratory studies
- Pilot experiments to generate hypotheses
- Among 1000 discoveries, expect ~100 false positives

**q < 0.01 (1% FDR):**
- More stringent, lower power
- High-confidence discoveries
- Follow-up validation studies
- When false positives are costly

### Choosing Your Threshold

**Use q < 0.05 when:**
- Standard discovery experiment
- Balancing sensitivity and specificity
- Following literature precedent
- Grant or publication

**Use q < 0.1 when:**
- Exploratory or pilot study
- Sample size limited (low power)
- Generating hypotheses for follow-up
- Biology expected to be subtle

**Use q < 0.01 when:**
- High-confidence hits needed
- Follow-up experiments costly
- Clinical or translational application
- Avoiding false positives critical

---

## Implementation in Common Tools

### DESeq2 (RNA-seq)

**Standard BH-FDR:**
```r
library(DESeq2)
dds <- DESeq(dds)
res <- results(dds, alpha = 0.05)  # BH-FDR at 5%
significant <- res[res$padj < 0.05 & !is.na(res$padj), ]
```

**With IHW:**
```r
library(DESeq2)
library(IHW)
dds <- DESeq(dds)
res <- results(dds, filterFun = ihw)  # Automatic IHW
significant <- res[res$padj < 0.05 & !is.na(res$padj), ]
```

**With lfcShrink (adaptive shrinkage):**
```r
res <- lfcShrink(dds, coef = "condition_treatment_vs_control", type = "apeglm")
# Shrinks LFC, improves power for small effects
significant <- res[res$padj < 0.05 & !is.na(res$padj), ]
```

### edgeR (RNA-seq, ATAC-seq)

**Standard BH-FDR:**
```r
library(edgeR)
fit <- glmQLFit(dge, design)
qlf <- glmQLFTest(fit, coef = 2)
results <- topTags(qlf, n = Inf, adjust.method = "BH")
significant <- results$table[results$table$FDR < 0.05, ]
```

### limma (Microarray, RNA-seq)

**Standard BH-FDR:**
```r
library(limma)
fit <- lmFit(eset, design)
fit2 <- eBayes(fit)
results <- topTable(fit2, coef = 2, adjust.method = "BH", n = Inf)
significant <- results[results$adj.P.Val < 0.05, ]
```

### Manual Correction

**For any p-values:**
```r
# Benjamini-Hochberg
adjusted_p <- p.adjust(pvalues, method = "BH")

# Bonferroni
adjusted_p <- p.adjust(pvalues, method = "bonferroni")

# Or using multtest package
library(multtest)
adjusted_p <- mt.rawp2adjp(pvalues, proc = "BH")
```

---

## Interpreting Results

### What Does q < 0.05 Mean?

**Correct interpretation:**
- "Among all genes I call significant at q < 0.05, I expect ~5% are false positives"
- "The FDR for my set of discoveries is controlled at 5%"
- "If I report 100 significant genes, ~5 are likely false positives (but I don't know which ones)"

**Incorrect interpretations:**
- ❌ "This gene has a 5% chance of being a false positive" (that's local FDR, not FDR)
- ❌ "I have 95% confidence this effect is real" (not a confidence statement)
- ❌ "P < 0.05 after correction" (q-value is not a p-value)

### Reporting Significant Genes

**In results section:**
> "We identified 1,247 differentially expressed genes at FDR < 0.05 (Benjamini-Hochberg correction). Of these, 687 were upregulated and 560 were downregulated in the treatment group."

**In methods section:**
> "Differential expression was assessed using DESeq2 v1.36.0 with default parameters. P-values were adjusted for multiple testing using the Benjamini-Hochberg method, and genes with adjusted p-value (q-value) < 0.05 were considered significant."

**With IHW:**
> "We used Independent Hypothesis Weighting (IHW) with mean expression as the covariate to increase power while controlling FDR at 5%. This approach identified 1,512 significant genes compared to 1,247 with standard Benjamini-Hochberg correction, representing a 21% increase in discoveries."

### Volcano Plots and Multiple Testing

**Standard volcano plot:**
- X-axis: log2 fold change
- Y-axis: -log10(adjusted p-value) NOT raw p-value
- Horizontal line at -log10(0.05) = 1.3 for q < 0.05
- Points above line and left/right of FC threshold are significant

**Correct labeling:**
- ✅ "FDR < 0.05" or "q < 0.05" or "Adjusted p < 0.05"
- ❌ "p < 0.05" (ambiguous, sounds like unadjusted)

---

## Special Considerations

### What If Nothing Is Significant?

**Possible reasons:**
1. **Underpowered study** - Need more samples or depth
2. **No true biological effect** - Null hypothesis is true
3. **High variability** - Biological or technical noise too large
4. **Poor quality data** - Technical issues masking signal
5. **Wrong comparison** - Testing wrong contrast or timepoint

**What NOT to do:**
❌ Relax correction threshold arbitrarily (q < 0.2, q < 0.5, etc.)
❌ Report "trends" or "marginally significant" results
❌ Switch to uncorrected p-values
❌ Cherry-pick genes of interest and claim they're significant

**What to do instead:**
✅ Report that no genes met significance threshold
✅ Examine power analysis - was study adequately powered?
✅ Look at top genes (ranked by p-value) for biological interpretation
✅ Consider effect sizes - are effects too small to detect?
✅ Run QC - are there technical issues?
✅ Design better follow-up experiment

### Stratified Multiple Testing

**Scenario:** Testing in multiple contexts (multiple cell types, tissues, conditions)

**Approach 1: Correct within each stratum**
- Test each cell type separately
- Apply FDR correction within each
- Appropriate when strata are independent questions

**Approach 2: Correct across all tests**
- Pool all tests from all strata
- Apply single FDR correction
- More conservative but controls overall FDR

**Example:**
- Testing DE in 10 cell types (15,000 genes × 10 = 150,000 tests)
- Within-stratum: BH-FDR within each cell type (10 separate corrections)
- Across-stratum: BH-FDR across all 150,000 tests (one correction)

**Recommendation:**
- Use within-stratum if strata represent distinct biological questions
- Use across-stratum if want to control overall false discovery rate

### Pre-Filtering to Reduce Tests

**Motivation:** Reduce number of tests to increase power

**Common filters:**
- RNA-seq: Remove genes with very low counts (e.g., < 10 reads across all samples)
- ATAC-seq: Remove peaks with very low signal
- Methylation: Remove probes with known SNPs or cross-reactivity

**Legality:** Filtering is valid if done on covariate INDEPENDENT of test statistic under null
- ✅ Mean expression (independent of DE under null)
- ✅ Peak width (independent of differential accessibility)
- ❌ Fold change (directly related to test statistic)
- ❌ P-value (obviously invalid)

**Impact:** Can increase power by removing uninformative tests

**Implementation in DESeq2:**
```r
# DESeq2 automatically does independent filtering
res <- results(dds, independentFiltering = TRUE)  # Default
```

---

## Advanced Topics

### Multiple Testing in scRNA-seq

**Unique challenges:**
- Testing in many cell types increases multiple testing burden
- Sparse data (dropout) reduces power
- Pseudobulk vs. single-cell methods have different multiple testing considerations

**Recommendations:**
1. **Use pseudobulk approach** when possible (aggregate cells to sample level)
   - Reduces total number of tests
   - Better power
   - Apply standard BH-FDR

2. **For single-cell methods** (cell-level tests):
   - Still use BH-FDR
   - May need more lenient threshold (q < 0.1)
   - Consider effect size thresholds (fold-change > 1.5) in addition to q-value

3. **For multi-cell-type analyses:**
   - Correct within each cell type (recommended)
   - Or correct across all tests (more conservative)

### Empirical Bayes and Shrinkage Methods

**Motivation:** Borrow information across genes to improve power

**Methods:**
- **DESeq2 lfcShrink:** Shrinks log fold changes toward zero, improves power
- **limma eBayes:** Shrinks variance estimates, increases degrees of freedom
- **ashr (adaptive shrinkage):** Flexible shrinkage improving power

**Benefit:** Better power for small effects while controlling FDR

**Usage:**
```r
# DESeq2 with apeglm shrinkage
res <- lfcShrink(dds, coef = "condition_treatment_vs_control", type = "apeglm")
# Then apply standard FDR threshold
significant <- res[res$padj < 0.05 & !is.na(res$padj), ]
```

### Hierarchical Testing

**Scenario:** Testing at multiple levels (gene → pathway, SNP → gene → region)

**Approach:** Use hierarchical FDR control
1. Test at finest level (genes)
2. Aggregate to higher level (pathways)
3. Control FDR at each level

**Benefit:** Increases power to detect effects at different scales

---

## Common Mistakes

### Mistake 1: Not Correcting at All

❌ **Wrong:** Report genes with p < 0.05 without correction

**Why it's wrong:** Almost all results are likely false positives

✅ **Correct:** Always apply multiple testing correction in genomics

### Mistake 2: Correcting Multiple Times

❌ **Wrong:** Apply BH-FDR in DESeq2, then apply again manually

**Why it's wrong:** Double correction is too conservative

✅ **Correct:** DESeq2 `padj` column already contains corrected values - use directly

### Mistake 3: Choosing Threshold After Seeing Results

❌ **Wrong:** Try q < 0.05 (nothing significant), switch to q < 0.1 or q < 0.2

**Why it's wrong:** Post-hoc threshold selection inflates false positives

✅ **Correct:** Pre-specify threshold (typically q < 0.05), stick with it

### Mistake 4: Reporting "Trends"

❌ **Wrong:** "Gene X showed a trend toward significance (q = 0.08)"

**Why it's wrong:** Non-significant is non-significant; "trend" is not a statistical term

✅ **Correct:** Report as not significant, or examine in exploratory manner

### Mistake 5: Mixing Corrected and Uncorrected

❌ **Wrong:** Use FDR for RNA-seq but raw p-values for qPCR validation

**Why it's wrong:** Inconsistent error control

✅ **Correct:** Use appropriate correction for each experiment scale

---

## Validation and Orthogonal Evidence

### Multiple Testing in Validation Experiments

**Key principle:** Validation experiments test fewer hypotheses, need less stringent correction

**Example workflow:**
1. Discovery (RNA-seq): Test 20,000 genes with BH-FDR at q < 0.05 → 1000 significant genes
2. Select top 20 genes for qPCR validation
3. Validation: Test 20 genes with Bonferroni correction (α = 0.05/20 = 0.0025)

**Rationale:**
- Discovery phase: Exploratory, many tests, use FDR
- Validation phase: Confirmatory, few tests, use FWER (Bonferroni)

### Building Evidence Without Correction

**When minimal correction acceptable:**
- Orthogonal evidence supports finding (proteomics confirms RNA-seq)
- Known biology supports result (gene is in relevant pathway)
- Spatial localization matches (ISH confirms RNA-seq)
- Functional validation (knockdown experiment confirms)

**Reporting:**
> "While Gene X did not reach genome-wide significance (q = 0.12), it was consistently upregulated across three independent cohorts (all nominal p < 0.01), and encodes a protein in the target pathway, making it a strong candidate for follow-up."

---

## Software Implementations

### R Packages

| Package | Function | Method |
|---------|----------|--------|
| `stats` | `p.adjust()` | BH, Bonferroni, others |
| `qvalue` | `qvalue()` | Storey's q-value |
| `IHW` | `ihw()` | Independent hypothesis weighting |
| `DESeq2` | `results()` | BH or IHW (via `filterFun`) |
| `edgeR` | `topTags()` | BH or others |
| `limma` | `topTable()` | BH or others |

### Workflow Scripts

- [multiple_testing.R](../scripts/multiple_testing.R) - Implementations of all methods

---

## Additional Resources

**Key Papers:**
- Benjamini Y & Hochberg Y (1995) "Controlling the False Discovery Rate." *J R Stat Soc Series B* 57(1):289-300
- Storey JD & Tibshirani R (2003) "Statistical significance for genomewide studies." *PNAS* 100(16):9440-9445
- Ignatiadis N et al. (2016) "Data-driven hypothesis weighting increases detection power." *Nat Methods* 13(7):577-580

**Related Guides:**
- [power_analysis_guidelines.md](power_analysis_guidelines.md) - Accounts for multiple testing in power
- [experimental_design_best_practices.md](experimental_design_best_practices.md) - Sample size for adequate power

---

**Last Updated:** 2026-01-28
**Version:** 1.0
