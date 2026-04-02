---
doc_id: sc-markers-guardrails
title: Single-Cell Marker Guardrails
doc_type: knowhow
critical_rule: MUST explain the cluster grouping and ranking method before running sc-markers
domains: [singlecell]
related_skills: [sc-markers]
phases: [before_run, on_warning, after_run]
search_terms: [marker genes, rank genes groups, wilcoxon, logreg, cluster markers, 单细胞marker, 调参]
priority: 1.0
source_urls:
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html
---

# Single-Cell Marker Guardrails

- **Inspect first**: confirm the grouping column really represents clusters or labels worth ranking against.
- **Key wrapper controls**: explain `groupby`, `method`, `n_genes`, and `n_top` before running.
- **Use method-correct language**: `wilcoxon`, `t-test`, and `logreg` are alternative ranking modes for the same cluster-marker question.
- **Do not overclaim biological certainty**: top-ranked markers are candidate discriminative genes, not final cell-type labels by themselves.
- **Do not invent unsupported thresholds**: this wrapper does not expose a large matrix of extra rank-gene parameters beyond the public flags above.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-markers.md`.
