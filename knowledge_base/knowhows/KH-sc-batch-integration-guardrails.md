---
doc_id: sc-batch-integration-guardrails
title: Single-Cell Batch Integration Guardrails
doc_type: knowhow
critical_rule: MUST explain the selected integration backend plus the batch metadata it uses before running sc-batch-integration
domains: [singlecell]
related_skills: [sc-batch-integration, sc-integrate]
phases: [before_run, on_warning, after_run]
search_terms: [batch integration, Harmony, scVI, scANVI, BBKNN, Scanorama, batch key, 单细胞整合, 批次校正, 调参]
priority: 1.0
source_urls:
  - https://scanpy.readthedocs.io/en/latest/generated/scanpy.external.pp.harmony_integrate.html
  - https://docs.scvi-tools.org/en/stable/api/reference/scvi.model.SCVI.html
  - https://docs.scvi-tools.org/en/1.3.1/api/reference/scvi.model.SCANVI.html
  - https://bbknn.readthedocs.io/en/latest/bbknn.bbknn.html
  - https://scanpy.readthedocs.io/en/latest/generated/scanpy.external.pp.scanorama_integrate.html
---

# Single-Cell Batch Integration Guardrails

- **Inspect first**: confirm the batch column and whether labels exist, because `scanvi` needs labels while other methods only need batch structure.
- **Key wrapper controls**: explain `method`, `batch_key`, `n_epochs`, and `no_gpu` before running.
- **Use method-correct language**: `batch_key` is the core control across Harmony, scVI, BBKNN, and Scanorama; `n_epochs` only matters for scVI/scANVI in this wrapper.
- **Do not invent unsupported knobs**: official docs discuss additional parameters such as Harmony `theta`, BBKNN `neighbors_within_batch`, and Scanorama `knn`/`sigma`, but the current OmicsClaw wrapper does not expose them.
- **Be honest about unavailable methods**: `fastmnn`, `seurat_cca`, and `seurat_rpca` are declared in metadata but not bundled for execution in this build.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-batch-integration.md`.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-batch-integration.md`.
