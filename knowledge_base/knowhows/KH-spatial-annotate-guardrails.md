---
doc_id: spatial-annotate-guardrails
title: Spatial Annotation Guardrails
doc_type: knowhow
critical_rule: MUST inspect matrix type, cluster/reference metadata, and explain the selected annotation method plus key parameters before running
domains: [spatial]
related_skills: [spatial-annotate, spatial-cell-annotation, annotate]
phases: [before_run, on_warning, after_run]
search_terms: [spatial annotation, cell type annotation, Tangram, scANVI, CellAssign, marker overlap, label transfer, 空间注释, 细胞类型注释, 标签转移, 调参]
priority: 1.0
---

# Spatial Annotation Guardrails

- **Inspect first**: verify whether the dataset has log-normalized `adata.X`, raw counts in `layers["counts"]` or `adata.raw`, usable spatial coordinates, and a cluster column if `marker_based` will be used.
- **Do not mix matrix assumptions**: `marker_based` and `tangram` use log-normalized expression; `scanvi` and `cellassign` should preferentially use raw counts from a declared layer.
- **Validate the reference deliberately**: before Tangram or scANVI, confirm the reference file exists, the requested `cell_type_key` is present, and the gene overlap is large enough to support transfer.
- **Treat `batch_key` and `layer` as scientific inputs**: do not present them as implementation details when the method is `scanvi` or `cellassign`; they directly affect model setup.
- **Explain the run before execution**: state the chosen method and the small set of parameters that will control the first pass, especially `marker_*`, `tangram_*`, `scanvi_*`, or `cellassign_max_epochs`.
- **Use method-correct language**: marker-based mode reports marker-overlap scores, Tangram reports projected cell-type probabilities, and scANVI / CellAssign expose model-based confidence summaries.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-annotate.md`.
