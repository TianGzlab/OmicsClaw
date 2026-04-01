---
doc_id: sc-filter-guardrails
title: Single-Cell Filtering Guardrails
doc_type: knowhow
critical_rule: MUST explain the effective QC thresholds before running sc-filter and treat tissue presets as wrapper heuristics rather than universal biology rules
domains: [singlecell]
related_skills: [sc-filter]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell filtering, qc filtering, min genes, max mt percent, tissue preset, 单细胞过滤, 质控阈值, 调参]
priority: 1.0
source_urls:
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.filter_cells.html
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.pp.filter_genes.html
  - https://scanpy.readthedocs.io/en/stable/api/scanpy.pp.calculate_qc_metrics.html
---

# Single-Cell Filtering Guardrails

- **Inspect first**: review `n_genes_by_counts`, `total_counts`, and `%MT` distributions before choosing thresholds.
- **Key wrapper controls**: explain `min_genes`, `max_genes`, `min_counts`, `max_counts`, `max_mt_percent`, and `min_cells` before running.
- **Treat `--tissue` honestly**: it is an OmicsClaw preset that overrides thresholds; do not describe it as an upstream Scanpy parameter.
- **Do not overclaim automation**: this wrapper applies explicit threshold filters only; it does not infer optimal cutoffs from the data.
- **Use method-correct language**: cell filtering and gene filtering are separate operations, and `min_cells` is a gene-retention control, not a cell-quality score.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-filter.md`.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-filter.md`.
