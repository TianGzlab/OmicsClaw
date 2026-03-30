---
doc_id: gene-essentiality
title: Gene Essentiality Analysis
doc_type: knowhow
critical_rule: MUST invert DepMap essentiality scores before correlation or direction-sensitive interpretation
domains: [genomics, general]
related_skills: [pooled-crispr-screens, lasso-biomarker-panel]
phases: [before_run]
search_terms: [essentiality, CRISPR, DepMap, gene effect, correlation, 基因关键性, 必需基因, 基因敲除]
priority: 0.9
---

# Gene Essentiality Analysis

## CRITICAL: DepMap Score Direction

**DepMap essentiality scores are INVERTED from intuition:**
- **Negative scores = Essential genes** (knockout kills cells)
- **Zero = Non-essential** (knockout has no effect)
- **-1 = Median effect of known essential genes**

```
Essential ←――――――――――――――――――――――→ Non-essential
        -2    -1    0    +0.5
```

## MANDATORY: Invert Before Correlating

**When computing correlations with essentiality, you MUST invert the scores first:**

```python
# REQUIRED: Invert essentiality scores
essentiality_inverted = -essentiality_raw

# Now: positive values = more essential
correlation, pvalue = spearmanr(expression, essentiality_inverted)

# Interpretation (AFTER inversion):
# - Positive correlation → higher expression = higher essentiality
# - Negative correlation → higher expression = lower essentiality
```

## Finding Strongest Negative Correlation

**ALWAYS invert first, even when looking for negative correlations:**

```python
# CORRECT: Invert first, then find most negative correlation
essentiality_inverted = -essentiality_raw
correlations = {gene: spearmanr(expr, essentiality_inverted)[0] for gene, expr in expression_data.items()}
most_negative = min(correlations, key=correlations.get)  # Gene where higher expr = LOWER essentiality

# WRONG: Using raw scores gives opposite biological meaning!
# correlations = {gene: spearmanr(expr, essentiality_raw)[0] for gene, expr in expression_data.items()}
```

**Why?** A negative correlation with inverted scores means: higher expression → lower essentiality (biologically meaningful). Without inversion, you get the opposite interpretation.

## Checklist

Before computing correlations with essentiality:
- [ ] Inverted scores with `essentiality_inverted = -essentiality_raw`
- [ ] Verified known essential genes (RPS14, RPL11) have negative raw scores


---
