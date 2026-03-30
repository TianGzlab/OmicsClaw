---
doc_id: spatial-de-guardrails
title: Spatial Differential Expression Guardrails
doc_type: knowhow
critical_rule: MUST separate exploratory Scanpy marker ranking from sample-aware pseudobulk inference before running spatial differential expression
domains: [spatial]
related_skills: [spatial-de, de]
phases: [before_run, on_warning, after_run]
search_terms: [spatial differential expression, marker genes, wilcoxon, t-test, pydeseq2, pseudobulk, cluster markers, 空间差异表达, marker, 伪bulk, 调参]
priority: 1.0
---

# Spatial Differential Expression Guardrails

- **Inspect first**: verify the `groupby` column, confirm whether `adata.X` is log-normalized, and check whether raw counts plus a real `sample_key` exist.
- **Do not mix inference levels**: `wilcoxon` / `t-test` in this skill are exploratory Scanpy marker methods on spots or cells; `pydeseq2` is the replicate-aware pseudobulk path.
- **No fake replicates**: never fabricate DESeq2 samples by random cell splitting or arbitrary chunking.
- **Choose the method intentionally**: use Scanpy for marker discovery; use `pydeseq2` only for explicit two-group comparisons with biological sample structure.
- **Explain the run before execution**: state the method, `groupby`, comparison groups if any, and the small set of method-specific parameters that matter first.
- **Keep visualization layers separated**: Python standard gallery is the default analysis layer; R customization should consume `figure_data/` and must not silently recompute DE.
- **Use method-correct language**: do not present Scanpy marker rankings as equivalent evidence to sample-aware pseudobulk NB-GLM results.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-de.md`.
