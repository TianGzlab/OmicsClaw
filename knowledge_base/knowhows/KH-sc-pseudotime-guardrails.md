---
doc_id: sc-pseudotime-guardrails
title: Single-Cell Pseudotime Guardrails
doc_type: knowhow
critical_rule: MUST explain the start state and the active trajectory representation before running sc-pseudotime
domains: [singlecell]
related_skills: [sc-pseudotime]
phases: [before_run, on_warning, after_run]
search_terms: [pseudotime, trajectory, root cluster, root cell, DPT, Palantir, VIA, CellRank, Slingshot]
priority: 1.0
---

# Single-Cell Pseudotime Guardrails

- Always explain that pseudotime needs a biologically defensible start state.
- Always explain that `use_rep` changes the result; do not silently pick among multiple integrated embeddings.
- Treat `method` and `corr_method` as different concepts.
- Block count-oriented input; pseudotime should run on normalized expression.
- If the user has not clustered yet, point them to `sc-clustering` first.
- If the user has multiple integrated embeddings, stop and ask which one should drive the trajectory.
- For `cellrank`, say clearly that this is about macrostates / terminal-state inference, not only a scalar pseudotime.
- For `slingshot_r`, say clearly that this is branch-focused lineage inference through the R bridge.
- For longer method guidance and parameter interpretation, see `knowledge_base/skill-guides/singlecell/sc-pseudotime.md`.
