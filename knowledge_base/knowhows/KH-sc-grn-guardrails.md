---
doc_id: sc-grn-guardrails
title: Single-Cell GRN Guardrails
doc_type: knowhow
critical_rule: MUST verify the external pySCENIC resources before running sc-grn and must not imply the workflow is self-contained without them
domains: [singlecell]
related_skills: [sc-grn]
phases: [before_run, on_warning, after_run]
search_terms: [GRN, pySCENIC, regulon, TF list, motif database, 单细胞调控网络, 转录因子, 调参]
priority: 1.0
source_urls:
  - https://pyscenic.readthedocs.io/
  - https://github.com/aertslab/pySCENIC
---

# Single-Cell GRN Guardrails

- **Inspect first**: verify the user has a TF list, motif annotations, and cisTarget databases, because those are core prerequisites.
- **Key wrapper controls**: explain `tf_list`, `db`, `motif`, `n_top_targets`, `n_jobs`, and `seed` before running.
- **Use method-correct language**: the workflow combines GRNBoost2 adjacency inference, motif pruning, and AUCell scoring.
- **Do not invent hidden database knobs**: pySCENIC exposes many resource-specific details, but the current OmicsClaw wrapper only exposes a compact resource-selection surface.
- **Do not overclaim automation**: this wrapper does not automatically fetch pySCENIC resources for the user.

