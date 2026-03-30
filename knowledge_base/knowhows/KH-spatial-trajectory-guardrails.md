---
doc_id: spatial-trajectory-guardrails
title: Spatial Trajectory Guardrails
doc_type: knowhow
critical_rule: MUST inspect preprocessing state, root selection strategy, and explain the selected trajectory backend plus method-specific parameters before running
domains: [spatial]
related_skills: [spatial-trajectory, trajectory]
phases: [before_run, on_warning, after_run]
search_terms: [trajectory, pseudotime, diffusion pseudotime, DPT, CellRank, Palantir, cell fate, lineage, 轨迹, 拟时序, 调参]
priority: 1.0
---

# Spatial Trajectory Guardrails

- **Inspect first**: verify that PCA and the neighbor graph already exist; trajectory should not be presented as independent of preprocessing.
- **Choose the root deliberately**: root cell, root cell type, or auto-root heuristic can materially change the biological interpretation.
- **Do not flatten methods into one generic story**: DPT gives scalar pseudotime, CellRank adds macrostates / fate probabilities, and Palantir adds branch entropy and waypoint-refined pseudotime.
- **Explain the run before execution**: state the backend and the small set of root / method-specific parameters that will control the first pass.
- **Separate wrapper controls from upstream parameters**: `cluster_key`, `root_cell`, and `root_cell_type` are wrapper-level controls, while `dpt_n_dcs`, `cellrank_n_states`, `cellrank_schur_components`, `cellrank_frac_to_keep`, `palantir_n_components`, `palantir_knn`, `palantir_num_waypoints`, and `palantir_max_iterations` map to public backend APIs.
- **Do not claim an unavailable backend actually ran**: if CellRank or Palantir is missing or fails, the system should not quietly describe the output as a successful run of that method.
- **Keep the visualization layers separated**: Python gallery outputs are the canonical analysis layer; any optional R plotting should read `figure_data/` and must not recompute trajectory inference.
- **Preserve the output contract**: scalar pseudotime summaries, trajectory-gene tables, and method-specific trajectory artifacts should be exported through the standard OmicsClaw layout.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-trajectory.md`.
