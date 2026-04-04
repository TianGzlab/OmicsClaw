---
doc_id: sc-tenifold-knockout-guardrails
title: scTenifoldKnk Guardrails
doc_type: knowhow
critical_rule: MUST explain that scTenifoldKnk is a virtual knockout on a WT-inferred GRN and not a substitute for real perturbation experiments
domains: [singlecell]
related_skills: [sc-tenifold-knockout]
phases: [before_run, after_run]
search_terms: [scTenifoldKnk, virtual knockout, GRN, in silico perturbation]
priority: 1.0
source_urls:
  - https://github.com/cailab-tamu/scTenifoldKnk
  - https://sctenifold.readthedocs.io/en/latest/sctenifoldknk.html
---

# scTenifoldKnk Guardrails

- **Inspect first**: confirm the knockout gene exists in the expression matrix and that the matrix orientation is genes x cells.
- **Do not oversell causality**: this is a virtual knockout on an inferred WT network, not direct evidence from a real perturbation assay.
- **Keep input size realistic**: official runtime increases quickly with gene and cell count.
- **Interpret output correctly**: the main result is the differential regulation table, not a differential expression analysis.
- **For longer tuning and interpretation guidance**: see `knowledge_base/skill-guides/singlecell/sc-tenifold-knockout.md`.
