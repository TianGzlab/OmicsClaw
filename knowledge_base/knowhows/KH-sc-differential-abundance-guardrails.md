---
doc_id: sc-differential-abundance-guardrails
title: Single-Cell Differential Abundance Guardrails
doc_type: knowhow
critical_rule: MUST confirm sample-level replication and explain why DA/compositional analysis is not the same as DE before running sc-differential-abundance
domains: [singlecell]
related_skills: [sc-differential-abundance]
phases: [before_run, on_warning, after_run]
search_terms: [differential abundance, compositional analysis, milo, sccoda, neighborhood, sample-aware]
priority: 1.0
source_urls:
  - https://www.sc-best-practices.org/conditions/compositional.html
  - https://sccoda.readthedocs.io/en/latest/getting_started.html
---

# Single-Cell Differential Abundance Guardrails

- **Inspect first**: verify there are real replicate samples, not just many cells.
- **Explain the question correctly**: DA asks whether cell-state prevalence shifts between conditions; it is not differential expression.
- **Do not hide compositionality**: scCODA results are relative to a reference cell type; unchanged-looking cell types can still move because proportions sum to one.
- **Use method-correct language**: Milo is neighborhood-level DA on a KNN graph; scCODA is a Bayesian compositional model.
- **Stop when replication is absent**: if there is effectively one sample per condition, say that inference is exploratory only.
- **For longer tuning and interpretation guidance**: see `knowledge_base/skill-guides/singlecell/sc-differential-abundance.md`.
