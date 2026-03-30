---
doc_id: scatac-preprocessing-guardrails
title: scATAC Preprocessing Guardrails
doc_type: knowhow
critical_rule: MUST inspect whether the input is a raw-count-like peak matrix, explain the effective sparsity, TF-IDF, and graph parameters, and never claim fragment-aware or motif-aware preprocessing when the current wrapper does not implement it
domains: [singlecell]
related_skills: [scatac-preprocessing, scatac-preprocess]
phases: [before_run, on_warning, after_run]
search_terms: [scATAC preprocessing, ATAC TF-IDF, LSI preprocessing, chromatin accessibility clustering, 单细胞ATAC预处理, 染色质可及性, 调参]
priority: 1.0
---

# scATAC Preprocessing Guardrails

- **Inspect first**: verify that `adata.X` still looks like a non-negative peak matrix, not an already-transformed embedding or gene-activity matrix.
- **Do not overclaim scope**: current OmicsClaw `scatac-preprocessing` does not start from fragments, call peaks, compute motifs, or compute gene activity.
- **Explain the run before execution**: state the effective `min_peaks`, `min_cells`, `n_top_peaks`, `tfidf_scale_factor`, `n_lsi`, `n_neighbors`, and `leiden_resolution`.
- **Use wrapper-correct language**: `n_top_peaks` is a wrapper-level retained-feature budget after filtering, not a promise that every upstream Signac / ArchR feature-selection option is exposed.
- **Preserve the contract**: successful runs should emit `processed.h5ad`, a standard gallery, figure-data CSVs, and the reproducibility bundle including the analysis notebook.
- **Interpret outputs correctly**: `processed.h5ad` stores the retained peak space used for TF-IDF + LSI, not the original full fragment universe.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/scatac-preprocessing.md`.
