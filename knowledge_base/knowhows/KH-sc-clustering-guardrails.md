---
doc_id: sc-clustering-guardrails
title: Single-Cell Clustering Guardrails
doc_type: knowhow
critical_rule: MUST verify normalized expression and PCA availability before clustering, and remind users that batch correction should happen before clustering when batch effects are expected
domains: [singlecell]
related_skills: [sc-clustering, sc-dimred-cluster]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell clustering, leiden, louvain, UMAP clustering, 单细胞聚类, 降维聚类, 调参]
priority: 1.0
---

# Single-Cell Clustering Guardrails

- **Inspect first**: clustering should start from normalized expression plus PCA, not from raw counts.
- **Do not collapse preprocessing and clustering into one vague step**: `sc-preprocessing` prepares the normalized PCA-ready object; `sc-clustering` consumes that object for graph construction, UMAP, and clustering.
- **Ask about batch effects before clustering**: if likely batch/sample columns are present and no integrated embedding exists, remind the user to consider `sc-batch-integration` first.
- **Make the embedding explicit when needed**: if more than one embedding exists, ask the user which one should drive neighbors and UMAP.
- **Expose the real tuning knobs**: `n_neighbors` and clustering resolution are the main first-pass controls; do not hide them behind vague wording.
- **Preserve the contract**: successful runs should emit `processed.h5ad`, a standard gallery, figure-data CSVs, and the reproducibility bundle.
