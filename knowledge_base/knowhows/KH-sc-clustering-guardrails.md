---
doc_id: sc-clustering-guardrails
title: Single-Cell Clustering Guardrails
doc_type: knowhow
critical_rule: MUST verify normalized expression and PCA availability before clustering, make the driving representation explicit, and remind users that batch correction should happen before clustering when batch effects are expected
domains: [singlecell]
related_skills: [sc-clustering, sc-dimred-cluster]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell clustering, leiden, louvain, UMAP clustering, 单细胞聚类, 降维聚类, 调参]
priority: 1.0
---

# Single-Cell Clustering Guardrails

- **Inspect first**: clustering should start from normalized expression plus PCA or an integrated embedding, not from raw counts.
- **Do not collapse preprocessing and clustering into one vague step**: `sc-preprocessing` prepares the normalized PCA-ready object; `sc-clustering` consumes that object for graph construction, embedding, and clustering.
- **Ask about batch effects before clustering**: if likely batch/sample columns are present and no integrated embedding exists, remind the user to consider `sc-batch-integration` first.
- **Make the representation explicit when needed**: if more than one embedding exists, ask the user which one should drive neighbors. `use_rep` is a real tuning decision, not an internal implementation detail.
- **Expose the real tuning knobs**: `n_neighbors`, `resolution`, `use_rep`, and `embedding_method` are the main first-pass controls; then expose the method-specific parameters that belong to the selected embedding backend.
- **Point to the next analysis step**: after clustering, the usual next branches are `sc-markers`, `sc-cell-annotation`, and `sc-de`.
- **Preserve the contract**: successful runs should emit `processed.h5ad`, a standard gallery, figure-data CSVs, and the reproducibility bundle.
