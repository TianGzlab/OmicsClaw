---
doc_id: bulk-rnaseq-differential-expression
title: Best practices for RNA-seq Differential Expression Analysis
doc_type: knowhow
critical_rule: MUST use adjusted p-values (padj/FDR) for DEG filtering and MUST NOT interpret raw p-values as significance thresholds
domains: [bulkrna, singlecell]
related_skills: [bulk-rnaseq-counts-to-de-deseq2, bulkrna-de, bulkrna-deseq2, de]
phases: [before_run]
search_terms: [RNA-seq, differential expression, DESeq2, padj, FDR, fold change, 差异表达, 差异基因, 差异分析]
priority: 0.9
---

# Best practices for RNA-seq Differential Expression Analysis

### Critical: Use Adjusted P-values for DEG Filtering

**ALWAYS use adjusted p-values (padj/FDR) for filtering significant genes, NEVER raw p-values.**

In RNA-seq analysis, thousands of genes are tested simultaneously. Raw p-values must be adjusted (e.g., using Benjamini-Hochberg FDR) to control false discovery rate.

**Standard DEG filtering (Python):**
```python
# CORRECT - Use adjusted p-values
significant_degs = results[
    (results['padj'] <= 0.05) &                    # Adjusted p-value
    (abs(results['log2FoldChange']) >= 0.5)     # Fold change (inclusive)
]
```

**For R DESeq2:**
```r
# CORRECT - Use padj column
sig_genes <- subset(res, padj <= 0.05 & abs(log2FoldChange) >= 0.5)
```

---

### Terminology

- "Statistically significant DEGs" = genes passing **adjusted p-value** threshold
- "p < 0.05" in DEG context typically means **padj < 0.05** unless explicitly stated as "raw p-value"
- Use inclusive inequalities (`>=`, `<=`) unless the question explicitly uses strict inequalities (`>`, `<`)


---
