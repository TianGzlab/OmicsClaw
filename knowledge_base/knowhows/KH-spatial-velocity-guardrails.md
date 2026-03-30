---
doc_id: spatial-velocity-guardrails
title: Spatial Velocity Guardrails
doc_type: knowhow
critical_rule: MUST inspect spliced/unspliced layer availability and explain the selected backend plus shared preprocessing / graph settings before running
domains: [spatial]
related_skills: [spatial-velocity, velocity]
phases: [before_run, on_warning, after_run]
search_terms: [spatial velocity, RNA velocity, scvelo, velovi, latent time, pseudotime, spliced, unspliced, 调参]
priority: 1.0
---

# Spatial Velocity Guardrails

- **Inspect first**: confirm `layers["spliced"]` and `layers["unspliced"]` exist, check for spatial coordinates and an interpretable `cluster_key`, and ask whether the user wants a fast first pass or a heavier kinetic / variational run.
- **State the shared contract before running**: surface `velocity_min_shared_counts`, `velocity_n_top_genes`, `velocity_n_pcs`, `velocity_n_neighbors`, and any `velocity_graph_*` overrides because these materially change the result.
- **Keep backend semantics separate**: `stochastic` / `deterministic` / `dynamical` are scVelo kinetic models; `velovi` is a variational posterior model with training hyperparameters.
- **Use time language carefully**: `velocity_pseudotime` and `latent_time` are model-derived orderings, not absolute biological time.
- **Do not hide training choices**: for VELOVI, always surface `max_epochs`, `n_samples`, and early-stopping status when summarizing the run.
- **Keep the visualization layers separated**: Python gallery outputs are the canonical analysis layer; optional R visualization should consume `figure_data/` and must not rerun scVelo or VELOVI.
- **For detailed method selection and tuning guidance**: see `knowledge_base/skill-guides/spatial/spatial-velocity.md`.
