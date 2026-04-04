---
doc_id: sc-perturb-guardrails
title: Single-Cell Perturbation Guardrails
doc_type: knowhow
critical_rule: MUST distinguish perturbation labels from true perturbed-responder classes and explain that Mixscape separates perturbed versus non-perturbed cells within perturbation groups
domains: [singlecell]
related_skills: [sc-perturb]
phases: [before_run, after_run]
search_terms: [perturbation, perturb-seq, mixscape, pertpy, responder]
priority: 1.0
source_urls:
  - https://pertpy.readthedocs.io/en/latest/api/tools/pertpy.tools.Mixscape.html
---

# Single-Cell Perturbation Guardrails

- **Inspect first**: confirm the perturbation column, control label, and replicate structure before running Mixscape.
- **Stop for missing metadata**: if the user only has expression data without perturbation labels, send them to upstream guide-assignment preparation first instead of guessing labels.
- **Do not equate guide identity with effect**: a cell carrying a perturbation can still be classified as non-perturbed by Mixscape.
- **Prefer replicate-aware signatures**: when replicate labels exist, use them via `split_by` rather than pooling everything immediately.
- **Interpret classes carefully**: `NT`, `NP`, and perturbation-specific responder classes capture different biological states.
- **For longer tuning and interpretation guidance**: see `knowledge_base/skill-guides/singlecell/sc-perturb.md`.
