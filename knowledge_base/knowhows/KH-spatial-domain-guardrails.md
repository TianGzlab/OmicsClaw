---
doc_id: spatial-domain-guardrails
title: Spatial Domain Analysis Guardrails
doc_type: knowhow
critical_rule: MUST inspect the dataset and explain the selected spatial domain method plus key clustering parameters before running
domains: [spatial]
related_skills: [spatial-domains, spatial-domain-identification, domains]
phases: [before_run, on_warning]
search_terms: [spatial domain, tissue region, niche, leiden, louvain, SpaGCN, STAGATE, GraphST, BANKSY, CellCharter, 空间域, 聚类参数, 调参, domain identification]
priority: 1.0
---

# Spatial Domain Analysis Guardrails

- **Inspect first**: verify `obsm["spatial"]`, dataset size, and whether embeddings such as `obsm["X_pca"]` already exist.
- **Choose the method intentionally**: do not jump straight to a deep graph model when Leiden, CellCharter, or BANKSY is a better first pass.
- **Explain the run before execution**: tell the user which method will be used and the key parameters that matter for that method.
- **Respect implementation limits**: do not promise histology-aware SpaGCN in the current OmicsClaw workflow, and do not treat all domain methods as having the same assumptions.
- **Large-data caution**: for large tissues, prefer scalable baselines before heavy deep models unless the user explicitly requests the latter.
- **Keep visualization layers separate**: Python standard gallery is the canonical OmicsClaw output; optional R plotting should read `figure_data/` and focus on presentation, not recomputation.
- **Preserve the gallery contract**: when extending the skill, prefer adding new `PlotSpec` recipe entries and exported `figure_data/` tables instead of hard-coding one-off plotting branches.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-domains.md`.
