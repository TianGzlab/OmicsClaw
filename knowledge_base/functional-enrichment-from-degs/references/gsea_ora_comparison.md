# GSEA vs ORA: Detailed Method Comparison

This document provides an in-depth comparison of Gene Set Enrichment Analysis (GSEA) and Over-Representation Analysis (ORA) to help you understand when to use each method.

---

## GSEA (Gene Set Enrichment Analysis)

### Method Overview

**What it does:** Tests whether genes in a pathway tend to be at the TOP or BOTTOM of your ranked gene list (by fold change or test statistic).

**Input:** ALL genes ranked by expression change (no cutoff applied)

**Question answered:** "Are genes in this pathway coordinately up- or down-regulated?"

**Statistical approach:** Uses a running enrichment score that walks down the ranked gene list, increasing when a gene is in the pathway, decreasing when not. Computes significance via permutation testing.

### Strengths
- No arbitrary significance cutoffs needed
- Detects subtle but coordinated changes across many genes
- Works well even when few genes pass strict thresholds
- Provides direction (activated vs suppressed pathways)
- More sensitive to modest changes across entire pathways
- Uses all available information from the experiment

### Limitations
- Requires ranking metric (fold changes or test statistics)
- Computationally more expensive (permutation testing)
- Results can be harder to interpret for non-bioinformaticians
- Requires careful selection of ranking metric

### Output Interpretation
- **Positive NES (Normalized Enrichment Score):** Pathway is ACTIVATED (genes tend to be upregulated)
- **Negative NES:** Pathway is SUPPRESSED (genes tend to be downregulated)
- **Leading edge genes:** Core genes driving the enrichment signal
- **FDR < 0.05:** Statistically significant after multiple testing correction

### Best Ranking Metrics (in order of preference)
1. **Test statistic (t-statistic, Wald statistic)** - BEST, accounts for both effect size and significance
2. **Signed -log10(pvalue)** - Good alternative if test statistic unavailable
3. **Log2 fold change** - Avoid if possible, ignores statistical significance

---

## ORA (Over-Representation Analysis)

### Method Overview

**What it does:** Tests whether your significant genes overlap with a pathway more than expected by chance.

**Input:** A discrete list of significant genes (e.g., padj < 0.05, |log2FC| > 1)

**Question answered:** "Do my significant genes contain more pathway X members than expected?"

**Statistical approach:** Uses Fisher's exact test / hypergeometric test to compare observed vs. expected overlap between gene list and pathway.

### Strengths
- Simple and intuitive
- Fast computation
- Good for validating GSEA findings
- Works with any gene list (not just DE results)
- Easy to explain to collaborators

### Limitations
- Requires arbitrary cutoffs (which genes are "significant"?)
- Loses information about genes just below threshold
- Must analyze UP and DOWN genes separately to preserve direction
- Less sensitive to subtle coordinated changes
- Can be biased by gene list size

### Output Interpretation
- **GeneRatio:** k/n (genes in pathway / total query genes)
- **BgRatio:** M/N (genes in pathway in background / total background genes)
- **p.adjust < 0.05:** Statistically significant enrichment
- **Higher GeneRatio** = stronger enrichment
- **Must run separately for up/down genes** to preserve directionality

### Critical ORA Requirements
1. **Specify background genes:** Use all tested genes, not all known genes
2. **Separate up/down genes:** Don't combine opposite directions
3. **Appropriate thresholds:** padj < 0.05, |log2FC| ≥ 1 (adjust as needed)

---

## When to Use Which Method

| Scenario | Recommended Method | Rationale |
|----------|-------------------|-----------|
| **Default / no preference stated** | GSEA | More sensitive, no arbitrary cutoffs |
| User has full DE results with fold changes | GSEA | Can use all information |
| User wants to detect subtle coordinated changes | GSEA | Designed for this |
| User asks "what pathways are activated/suppressed" | GSEA | Provides directionality via NES |
| User has a specific gene list (no fold changes) | ORA | GSEA requires ranking |
| User wants quick validation of GSEA results | ORA | Complementary approach |
| User explicitly requests ORA | ORA | Honor user preference |
| Few genes pass significance threshold (<50) | GSEA | ORA underpowered with few genes |
| User wants to compare to Enrichr results | ORA | Enrichr uses ORA method |
| Very large gene list (>1000 significant genes) | Both | GSEA for sensitivity, ORA for validation |

---

## Decision Flowchart

```
User requests enrichment analysis
            │
            ▼
    Do they have full DE results
    (with fold changes)?
            │
       ┌────┴────┐
       │         │
      YES        NO
       │         │
       ▼         ▼
   Use GSEA    Use ORA
   (default)   (gene list only)
       │
       ▼
   Did user specifically
   request ORA?
       │
   ┌───┴───┐
   │       │
  YES      NO
   │       │
   ▼       ▼
Run both  Run GSEA
          only
```

---

## Comparing Results Between Methods

When you run both GSEA and ORA, you may see:

### Concordant Results (expected)
- Pathways significant in both GSEA and ORA
- This is the strongest evidence for pathway enrichment

### GSEA significant, ORA not significant
- Pathway has modest but coordinated changes across many genes
- Few genes pass strict ORA thresholds
- Still biologically meaningful

### ORA significant, GSEA not significant
- Strong signal in a few genes, but not coordinated across pathway
- May indicate a subset of pathway is affected
- Less common than scenario above

### Neither significant
- Pathway not affected in your experiment
- Or: wrong database, wrong species, poor gene identifier mapping

---

## Common Pitfalls

### GSEA Pitfalls
1. ❌ Using fold change alone for ranking (ignores significance)
2. ❌ Not removing duplicate genes
3. ❌ Using too few permutations (use ≥10,000)
4. ❌ Filtering genes before ranking (use ALL genes)

### ORA Pitfalls
1. ❌ Not specifying background genes (biases results)
2. ❌ Combining up and down genes (loses biological meaning)
3. ❌ Using all known genes as background (wrong denominator)
4. ❌ Filtering by keyword instead of statistics

---

## References

1. **GSEA original paper:** Subramanian A, et al. (2005) Gene set enrichment analysis: A knowledge-based approach for interpreting genome-wide expression profiles. PNAS. DOI: 10.1073/pnas.0506580102

2. **Method comparison:** Geistlinger L, et al. (2021) Toward a gold standard for benchmarking gene set enrichment analysis. Brief Bioinform. DOI: 10.1093/bib/bbz158

3. **Best practices:** Reimand J, et al. (2019) Pathway enrichment analysis and visualization of omics data using g:Profiler, GSEA, Cytoscape and EnrichmentMap. Nat Protoc. DOI: 10.1038/s41596-018-0103-9
