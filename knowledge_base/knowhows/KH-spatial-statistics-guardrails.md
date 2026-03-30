---
doc_id: spatial-statistics-guardrails
title: Spatial Statistics Guardrails
doc_type: knowhow
critical_rule: MUST decide whether the question is cluster-level, gene-level, or graph-level before choosing a spatial statistics method
domains: [spatial]
related_skills: [spatial-statistics, statistics]
phases: [before_run, on_warning, after_run]
search_terms: [spatial statistics, Moran, Geary, Ripley, co-occurrence, Getis-Ord, local Moran, centrality, 空间统计, 调参]
priority: 1.0
---

# Spatial Statistics Guardrails

- **Inspect first**: verify spatial coordinates exist, identify whether the user needs cluster-level neighborhood structure, gene-level autocorrelation, or graph-level topology, and check whether a usable `cluster_key` is available.
- **State the graph contract before running**: for graph-based methods, report `stats_n_neighs`, `stats_n_rings`, and whether OmicsClaw will reuse an existing graph or rebuild it.
- **Keep evidence types separate**: neighborhood enrichment / Ripley / co-occurrence are not interchangeable with Moran / Geary / local hotspot maps, and graph centrality is not a communication result.
- **Require exact inputs for exact methods**: bivariate Moran requires exactly two genes; local methods should not be presented as global gene-ranking statistics.
- **Use method-correct interpretation**: hotspot counts describe spatial concentration, not differential expression; centrality scores describe graph position, not biological causality.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-statistics.md`.
