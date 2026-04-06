---
doc_id: sc-preprocessing-guardrails
title: Single-Cell Preprocessing Guardrails
doc_type: knowhow
critical_rule: MUST inspect whether the input is raw-count-like, explain the chosen backend plus effective QC/HVG/PCA parameters, and never silently claim that preprocessing already finished clustering
domains: [singlecell]
related_skills: [sc-preprocessing, sc-preprocess]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell preprocessing, scRNA preprocessing, normalization, HVG, PCA, 单细胞预处理, 归一化, 调参]
priority: 1.0
---

# Single-Cell Preprocessing Guardrails

- **Inspect first**: verify the matrix still looks count-like, whether counts are preserved in `layers["counts"]` or `adata.raw`, and whether the user is accidentally rerunning preprocessing on normalized data.
- **Canonicalize once, then reuse state**: if count provenance is unclear, prefer the shared single-cell canonicalization helper; if the object already carries QC metrics from `sc-qc`, reuse them instead of forcing the user through the same QC step again.
- **Default user path is QC-informed preprocessing**: if the user asks for preprocessing without having reviewed QC distributions or provided filtering thresholds, pause and recommend `sc-qc` first, or explicitly confirm that the default first-pass filtering thresholds are acceptable.
- **Do not fake method choice**: current OmicsClaw `sc-preprocessing` exposes four real backends, `scanpy`, `seurat`, `sctransform`, and `pearson_residuals`; do not imply more methods exist, and do not silently replace an explicitly requested method with another backend.
- **Expose method-specific defaults honestly**: `scanpy`, `seurat`, `sctransform`, and `pearson_residuals` do not share exactly the same tuning knobs. Tell the user which defaults belong to the selected backend instead of presenting one generic parameter story.
- **Separate base preprocessing from clustering**: this skill stops at a normalized PCA-ready object. UMAP and clustering belong to `sc-clustering`, and batch correction belongs to `sc-batch-integration` when needed.
- **Surface the important side branches**: this skill does not remove doublets automatically; mention `sc-doublet-detection` when doublets may matter. If likely batch/sample columns are present, remind the user to consider `sc-batch-integration` before clustering.
- **Stop when the R backend would inherit ambiguous counts**: if `seurat` or `sctransform` would have to treat `adata.X` as raw counts because no `counts` layer or aligned `adata.raw` exists, make the user confirm that matrix state first.
- **Preserve the contract**: successful runs should emit a normalized, PCA-ready `processed.h5ad`, a standard gallery, figure-data CSVs, and the reproducibility bundle including the analysis notebook.
- **For detailed parameter and workflow guidance**: see `knowledge_base/skill-guides/singlecell/sc-preprocessing.md`.
