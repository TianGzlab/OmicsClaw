---
doc_id: sc-velocity-guardrails
title: Single-Cell Velocity Guardrails
doc_type: knowhow
critical_rule: MUST check for spliced and unspliced layers and explain the chosen velocity mode before running sc-velocity
domains: [singlecell]
related_skills: [sc-velocity]
phases: [before_run, on_warning, after_run]
search_terms: [RNA velocity, scVelo, stochastic, dynamical, steady_state, latent time, 单细胞速度, 调参]
priority: 1.0
source_urls:
  - https://scvelo.readthedocs.io/en/stable/scvelo.tl.velocity.html
  - https://scvelo.readthedocs.io/en/stable/VelocityBasics.html
---

# Single-Cell Velocity Guardrails

- **Inspect first**: verify `layers["spliced"]` and `layers["unspliced"]` exist before promising any velocity run.
- **Standardize external inputs only if it helps provenance**: `sc-standardize-input` can stabilize AnnData structure, but it cannot create velocity layers.
- **Use the new upstream path explicitly**: if `spliced` / `unspliced` are missing, direct the user to `sc-velocity-prep` rather than vaguely asking for a “real velocity object”.
- **Key wrapper controls**: explain `method` or `mode` and `n_jobs` before running.
- **Use method-correct language**: `stochastic`, `dynamical`, and `steady_state` are backend modes for the same velocity skill.
- **Do not overclaim latent time**: latent time is tied to the dynamical path and should not be promised for every velocity run.
- **Stop for missing velocity content**: do not continue when `spliced` / `unspliced` layers are absent, and ask the user to provide a real velocyto / kb-python style object instead.
- **Do not invent unsupported scVelo knobs**: the current OmicsClaw wrapper does not expose the full velocity-model parameter surface from upstream scVelo.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-velocity.md`.
