---
doc_id: sc-markers-guardrails
title: Single-Cell Marker Guardrails
doc_type: knowhow
critical_rule: MUST explain the grouping column and ranking method before running sc-markers
domains: [singlecell]
related_skills: [sc-markers]
phases: [before_run, on_warning, after_run]
search_terms: [marker genes, rank genes groups, wilcoxon, logreg, cluster markers, 单细胞marker, 调参]
priority: 1.0
source_urls:
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.rank_genes_groups.html
---

# Single-Cell Marker Guardrails

- **Inspect first**: confirm that the grouping column truly represents clusters or labels worth ranking.
- **Use normalized expression**: this workflow should rank markers from normalized `adata.X`, not silently switch to raw counts.
- **Key wrapper controls**: explain `groupby`, `method`, `n_genes`, `n_top`, and the public filtering thresholds before running.
- **Use method-correct language**: `wilcoxon`, `t-test`, and `logreg` are alternative ranking modes for the same cluster-marker question.
- **Do not overclaim certainty**: top-ranked markers are candidate discriminative genes, not final cell-type labels by themselves.
- **Do not confuse with condition DE**: if the user wants treated-vs-control, point them to `sc-de`.
- **Point to the next step**: after reviewing markers, the usual next branch is `sc-cell-annotation`.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-markers.md`.
