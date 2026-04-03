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
- **Prefer the full workflow for external data**: when provenance is unclear or the file is not already a stable AnnData object, recommend `sc-standardize-input` and then `sc-preprocessing` before integration.
- **Key wrapper controls**: explain `method`, `batch_key`, `n_epochs`, and `no_gpu` before running.
- **Use method-correct language**: `batch_key` is the core control across Harmony, scVI, BBKNN, and Scanorama; `n_epochs` only matters for scVI/scANVI in this wrapper.
- **Do not invent unsupported knobs**: official docs discuss additional parameters such as Harmony `theta`, BBKNN `neighbors_within_batch`, and Scanorama `knn`/`sigma`, but the current OmicsClaw wrapper does not expose them.
- **Disclose fallback honestly**: if `scanvi` is requested without usable labels and the wrapper executes `scvi`, state both the requested and executed methods explicitly.
- **Stop when batch identity is still ambiguous**: do not silently accept the default `batch_key=batch` unless that column truly represents batches, and do not continue when only one batch is present.
- **Reject suspicious batch columns**: do not integrate on columns that look nearly unique per cell or that split the data into many tiny groups without explicit user confirmation.
- **Respect the matrix contract**: `harmony`, `bbknn`, and `scanorama` operate on normalized / PCA-ready representations, while `scvi`, `scanvi`, `fastmnn`, `seurat_cca`, and `seurat_rpca` should preserve or read raw counts from `layers["counts"]` when available.
- **Be honest about runtime dependencies**: `fastmnn`, `seurat_cca`, and `seurat_rpca` are public methods, but they require a working R environment with batchelor or Seurat plus the shared H5AD bridge packages.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-batch-integration.md`.
