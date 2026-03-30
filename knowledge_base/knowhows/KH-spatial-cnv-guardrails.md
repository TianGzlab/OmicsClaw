---
doc_id: spatial-cnv-guardrails
title: Spatial CNV Analysis Guardrails
doc_type: knowhow
critical_rule: MUST inspect matrix type, genomic annotations, and reference cells before choosing inferCNVpy or Numbat
domains: [spatial]
related_skills: [spatial-cnv, cnv]
phases: [before_run, on_warning, after_run]
search_terms: [spatial cnv, copy number variation, infercnv, infercnvpy, numbat, aneuploidy, tumor clone, 空间CNV, 拷贝数变异, 染色体异常, 肿瘤克隆, 调参]
priority: 1.0
---

# Spatial CNV Analysis Guardrails

- **Inspect first**: verify `var["chromosome"]`, `var["start"]`, `var["end"]`, and whether the dataset preserves both log-normalized expression and raw counts.
- **Do not mix matrix assumptions**: `infercnvpy` should run on `adata.X` log-expression, while `numbat` should run on raw integer counts plus allele counts.
- **Choose the method intentionally**: use `infercnvpy` as the baseline expression-screening method; use `numbat` only when allele counts and a defensible diploid reference are available.
- **Explain the run before execution**: state the reference baseline and the small set of core parameters controlling the first pass.
- **Keep visualization layers separated**: Python standard gallery is the default analysis layer; R customization should consume `figure_data/` and must not silently recompute CNV inference.
- **Use method-correct language**: inferCNVpy outputs anomaly-style expression CNV scores; Numbat outputs posterior / clone-oriented CNV summaries. Do not describe them as the same kind of call.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-cnv.md`.
