---
doc_id: sc-gene-programs-guardrails
title: Single-Cell Gene Programs Guardrails
doc_type: knowhow
critical_rule: MUST explain that gene programs are latent coordinated modules and not automatically equivalent to canonical pathways or marker sets
domains: [singlecell]
related_skills: [sc-gene-programs]
phases: [before_run, after_run]
search_terms: [gene program, cnmf, nmf, module, latent factors]
priority: 1.0
source_urls:
  - https://github.com/codyheiser/cnmf
---

# Single-Cell Gene Programs Guardrails

- **Inspect first**: confirm the matrix and layer choice are appropriate for non-negative factorization.
- **Do not over-interpret factor count**: `n_programs` is a modeling choice, not a discovered truth.
- **Be honest about backend differences**: NMF is a lightweight matrix factorization baseline; cNMF-style workflows aim for more stable consensus programs.
- **Separate genes from biology**: top program genes suggest a module, but pathway or lineage meaning still needs interpretation.
- **For longer tuning and interpretation guidance**: see `knowledge_base/skill-guides/singlecell/sc-gene-programs.md`.
