---
doc_id: de-padj-guardrails
title: Differential Expression — Adjusted P-value (FDR) Filtering
doc_type: knowhow
critical_rule: MUST use adjusted p-values (padj/FDR) for DEG filtering and MUST NOT interpret raw p-values as significance thresholds
domains: [bulkrna, singlecell]
related_skills: [sc-de, bulkrna-de, bulk-rnaseq-counts-to-de-deseq2, bulkrna-deseq2]
phases: [before_run, after_run]
search_terms: [padj, FDR, Benjamini-Hochberg, BH, adjusted p-value, multiple testing correction, DEG filtering, 校正p值, FDR过滤, 差异基因过滤]
priority: 1.0
---

# Differential Expression — Adjusted P-value (FDR) Filtering

### Critical: Use Adjusted P-values for DEG Filtering

**ALWAYS use adjusted p-values (padj / FDR) for filtering significant genes — NEVER raw p-values.**

This rule applies equally to:

- **Bulk RNA-seq DE** workflows (DESeq2 / edgeR / limma).
- **Single-cell pseudobulk DE** workflows (DESeq2_R aggregated by sample × cell-type).

Both sit in the multiple-testing regime: thousands of genes are tested simultaneously, and raw p-values inflate false positives. The Benjamini-Hochberg FDR correction is the default; tighter methods (Bonferroni) are valid but unusual for DE.

### Standard Filter

```python
# CORRECT — adjusted p-value
significant = results[
    (results["padj"] <= 0.05) &
    (results["log2FoldChange"].abs() >= 1.0)
]

# WRONG — raw p-value
significant = results[results["pvalue"] <= 0.05]
```

### What "Significant" Means

- `padj <= 0.05` → ~5% expected false discovery rate.
- `padj <= 0.01` → stricter, fewer hits, lower FDR.
- A gene with `pvalue = 0.001` but `padj = 0.4` is **not** significant after correction — multiple testing dwarfed the raw p-value.

### Common Reporting Names

| Library / output | Adjusted p-value column |
|---|---|
| DESeq2 (Python pydeseq2 / R) | `padj` |
| edgeR `topTags` | `FDR` |
| limma `topTable` | `adj.P.Val` |
| Scanpy `rank_genes_groups` | `pvals_adj` |

When the user asks "how many DEGs?", always quote the count after padj filtering, not raw p-value, and state the threshold used.

### Cross-references

- For bulk-specific design and matrix contract details, see `KH-bulk-rnaseq-differential-expression.md`.
- For single-cell pseudobulk design and replicate-aware caveats, see `KH-sc-de-guardrails.md`.
