---
doc_id: spatial-integrate-guardrails
title: Spatial Integration Guardrails
doc_type: knowhow
critical_rule: MUST inspect batch structure and explain the selected integration method plus method-specific parameters before running batch correction
domains: [spatial]
related_skills: [spatial-integrate, spatial-integration, integrate]
phases: [before_run, on_warning, after_run]
search_terms: [spatial integration, batch correction, harmony, bbknn, scanorama, sample integration, multi-sample integration, 空间整合, 批次校正, 调参]
priority: 1.0
---

# Spatial Integration Guardrails

- **Inspect first**: verify `obs[batch_key]`, batch count, batch-size imbalance, and whether `obsm["X_pca"]` already exists.
- **Choose the method intentionally**: do not describe Harmony, BBKNN, and Scanorama as interchangeable; Harmony and Scanorama return corrected embeddings, while BBKNN primarily corrects the neighbour graph.
- **Explain the run before execution**: state the method and the small set of key parameters that will control the first pass.
- **Respect wrapper behavior**: current OmicsClaw integration runs on PCA space; do not describe it as raw-count integration.
- **Scanorama caution**: the Scanpy wrapper expects batches to be contiguous in `adata`; OmicsClaw now handles this internally, but the assumption should still be understood when interpreting results.
- **Keep visualization layers separate**: Python standard gallery is the canonical OmicsClaw output; optional R plotting should read `figure_data/` and focus on presentation, not recomputation.
- **Preserve the gallery contract**: when extending the skill, prefer adding new `PlotSpec` recipe entries and exported `figure_data/` tables instead of hard-coding one-off plotting branches.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-integrate.md`.
