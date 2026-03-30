---
doc_id: spatial-condition-guardrails
title: Spatial Condition Comparison Guardrails
doc_type: knowhow
critical_rule: MUST inspect biological replicates and pseudobulk design before running any condition comparison
domains: [spatial]
related_skills: [spatial-condition, spatial-condition-comparison, condition]
phases: [before_run, on_warning, after_run]
search_terms: [spatial condition, pseudobulk, pydeseq2, deseq2, wilcoxon, treatment vs control, replicate, 空间条件比较, 伪bulk, 重复, 差异分析, 调参]
priority: 1.0
---

# Spatial Condition Comparison Guardrails

- **Inspect first**: verify `condition_key`, `sample_key`, and whether each biological sample belongs to exactly one condition.
- **Do not use spot-level pseudoreplication**: condition inference should be based on sample-level pseudobulk profiles, not on per-spot Wilcoxon tests treated as independent replicates.
- **Choose the method intentionally**: use `pydeseq2` as the first choice when replicate counts are adequate; use `wilcoxon` as a fallback when sample counts are limited or the NB model is unstable.
- **Explain the run before execution**: state the reference condition, cluster key, and the small set of parameters controlling replicate filtering and DE testing.
- **Keep visualization layers separated**: Python standard gallery is the default analysis layer; R customization should consume `figure_data/` and must not silently recompute pseudobulk DE.
- **Use method-correct language**: PyDESeq2 provides NB-GLM differential expression; Wilcoxon here is a pseudobulk fallback, not equivalent evidence.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-condition.md`.
