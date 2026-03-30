---
doc_id: sc-preprocessing-guardrails
title: Single-Cell Preprocessing Guardrails
doc_type: knowhow
critical_rule: MUST inspect whether the input is raw-count-like, explain the chosen preprocessing backend plus effective QC and graph parameters, and never silently swap an explicitly requested method
domains: [singlecell]
related_skills: [sc-preprocessing, sc-preprocess]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell preprocessing, scRNA preprocessing, Scanpy preprocessing, Seurat preprocessing, SCTransform preprocessing, QC filter normalize cluster, 单细胞预处理, 归一化, 调参]
priority: 1.0
---

# Single-Cell Preprocessing Guardrails

- **Inspect first**: verify the matrix still looks count-like, whether counts are already preserved in `layers["counts"]` or `adata.raw`, and whether the user is accidentally rerunning preprocessing on normalized or scaled data.
- **Do not fake method choice**: current OmicsClaw `sc-preprocessing` exposes three real backends, `scanpy`, `seurat`, and `sctransform`; do not imply more methods exist, and do not silently replace an explicitly requested method with another backend.
- **Separate wrapper filters from backend internals**: `min_genes`, `min_cells`, and `max_mt_pct` are wrapper-level QC controls even when the backend is Seurat or SCTransform.
- **Explain the run before execution**: state the chosen backend, effective QC thresholds, HVG budget, PCA / graph settings, and clustering resolution.
- **Use method-correct language**: Scanpy here uses log-normalized HVG selection with `flavor='seurat'`; Seurat uses `NormalizeData + FindVariableFeatures(vst)`; SCTransform uses `SCTransform(variable.features.n=...)`.
- **Preserve the contract**: successful runs should emit a downstream-ready `processed.h5ad`, a standard gallery, figure-data CSVs, and the reproducibility bundle including the analysis notebook.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-preprocessing.md`.
