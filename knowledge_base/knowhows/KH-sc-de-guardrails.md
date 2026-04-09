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
- **Point to the right upstream step**: cluster-marker DE usually comes after `sc-clustering`; sample-aware condition DE usually comes after labels/annotation and explicit replicate metadata.
- **Key wrapper controls**: explain `method`, `groupby`, `group1`, `group2`, `sample_key`, `celltype_key`, `n_top_genes`, and any method-specific parameters before running.
- **Use method-correct language**: Scanpy `wilcoxon`, `t-test`, and `logreg` are exploratory single-cell ranking paths; `mast` is an R-backed hurdle-model path on log-normalized expression; `deseq2_r` is the replicate-aware pseudobulk path on raw counts.
- **Do not invent unsupported knobs**: the current wrapper does not expose a full DESeq2 design formula editor or Scanpy low-level test parameters.
- **Respect the matrix contract**: `wilcoxon`, `t-test`, `logreg`, and `mast` should use `X = normalized_expression`; `deseq2_r` should use raw counts from `layers["counts"]`, aligned raw counts in `adata.raw`, or count-like `adata.X`.
- **Stop for pseudobulk design gaps**: do not run `deseq2_r` until the user has confirmed the condition column, both contrast groups, the replicate column, and the cell-type column.
- **Stop for clustering gaps**: do not pretend you can produce cluster markers when the object has no cluster/label column yet; send the user to `sc-clustering` first.
- **Be honest about runtime dependencies**: `mast` and `deseq2_r` are real public R-backed methods and require their corresponding R stacks; if those stacks are missing, fail clearly instead of implying the method still ran.
- **Point to the next step**: DE results usually flow into `sc-enrichment` for statistical term interpretation, or `sc-pathway-scoring` when the user instead wants per-cell signature activity.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-de.md`.
