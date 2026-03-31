---
doc_id: sc-de-guardrails
title: Single-Cell Differential Expression Guardrails
doc_type: knowhow
critical_rule: MUST distinguish exploratory marker ranking from replicate-aware pseudobulk inference before running sc-de
domains: [singlecell]
related_skills: [sc-de]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell differential expression, marker ranking, wilcoxon, DESeq2 pseudobulk, group comparison, 单细胞差异表达, 伪bulk, 调参]
priority: 1.0
source_urls:
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html
  - https://bioconductor.org/packages/release/bioc/vignettes/DESeq2/inst/doc/DESeq2.html
---

# Single-Cell Differential Expression Guardrails

- **Inspect first**: decide whether the user wants cluster markers or replicate-aware condition DE, because those are different statistical questions.
- **Key wrapper controls**: explain `method`, `groupby`, `group1`, `group2`, `sample_key`, `celltype_key`, and `n_top_genes` before running.
- **Use method-correct language**: Scanpy `wilcoxon` and `t-test` are exploratory single-cell ranking paths; `deseq2_r` is the replicate-aware pseudobulk path.
- **Do not invent unsupported knobs**: the current wrapper does not expose a full DESeq2 design formula editor or Scanpy low-level test parameters.
- **Do not overclaim MAST**: in this build, `mast` is a compatibility label and should not be described as a native full MAST backend.

