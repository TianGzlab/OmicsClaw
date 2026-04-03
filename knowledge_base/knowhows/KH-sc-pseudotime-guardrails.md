---
doc_id: sc-pseudotime-guardrails
title: Single-Cell Pseudotime Guardrails
doc_type: knowhow
critical_rule: MUST explain the root choice and distinguish the trajectory method from the trajectory-gene correlation method before running sc-pseudotime
domains: [singlecell]
related_skills: [sc-pseudotime]
phases: [before_run, on_warning, after_run]
search_terms: [pseudotime, DPT, PAGA, diffusion map, root cluster, trajectory genes, 单细胞拟时序, 轨迹, 调参]
priority: 1.0
source_urls:
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.paga.html
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.diffmap.html
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.dpt.html
---

# Single-Cell Pseudotime Guardrails

- **Inspect first**: verify the cluster labels and whether the user has a biologically defensible root cluster or root cell.
- **Standardize external inputs first when provenance is unclear**: recommend `sc-standardize-input` for object hygiene, but pseudotime still needs a real cluster column and a defensible root choice.
- **Key wrapper controls**: explain `method`, `cluster_key`, `root_cluster`, `root_cell`, `n_dcs`, `n_genes`, and `corr_method` before running.
- **Use method-correct language**: in the current wrapper, `method` selects the trajectory algorithm (`dpt`), while `corr_method` only controls how trajectory-associated genes are ranked afterward.
- **Do not invent unsupported backends**: this build exposes only the DPT trajectory path, even if users mention other trajectory tools.
- **Do not hide root selection**: if the root is uncertain, say that explicitly instead of pretending pseudotime direction is fixed by the algorithm alone.
- **Stop when the trajectory start state is underspecified**: do not run pseudotime blindly if both `root_cluster` and `root_cell` are absent and no human choice has been confirmed.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-pseudotime.md`.
