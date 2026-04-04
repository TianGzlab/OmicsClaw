---
doc_id: sc-pseudotime-guardrails
title: Single-Cell Pseudotime Guardrails
doc_type: knowhow
critical_rule: MUST explain the root choice and distinguish the trajectory method from the trajectory-gene correlation method before running sc-pseudotime
domains: [singlecell]
related_skills: [sc-pseudotime]
phases: [before_run, on_warning, after_run]
search_terms: [pseudotime, DPT, PAGA, diffusion map, Palantir, VIA, CellRank, root cluster, trajectory genes, 单细胞拟时序, 轨迹, 调参]
priority: 1.0
source_urls:
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.paga.html
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.diffmap.html
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.dpt.html
  - https://pypi.org/project/pyVIA/
  - https://github.com/ShobiStassen/VIA
  - https://cellrank.readthedocs.io/
---

# Single-Cell Pseudotime Guardrails

- **Inspect first**: verify the cluster labels and whether the user has a biologically defensible root cluster or root cell.
- **Standardize external inputs first when provenance is unclear**: recommend `sc-standardize-input` for object hygiene, but pseudotime still needs a real cluster column and a defensible root choice.
- **Key wrapper controls**: explain `method`, `cluster_key`, `root_cluster`, `root_cell`, `n_dcs`, `n_genes`, and `corr_method` before running.
- **Use method-correct language**: in the current wrapper, `method` selects the trajectory algorithm (`dpt`, `palantir`, `via`, or `cellrank`), while `corr_method` only controls how trajectory-associated genes are ranked afterward.
- **Do not flatten methods into one story**: DPT gives scalar ordering, Palantir adds entropy/fate probabilities, VIA adds graph terminal-state discovery, and CellRank adds macrostates / fate probabilities on top of a transition kernel.
- **Do not hide root selection**: if the root is uncertain, say that explicitly instead of pretending pseudotime direction is fixed by the algorithm alone.
- **Stop when the trajectory start state is underspecified**: do not run pseudotime blindly if both `root_cluster` and `root_cell` are absent and no human choice has been confirmed.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-pseudotime.md`.
