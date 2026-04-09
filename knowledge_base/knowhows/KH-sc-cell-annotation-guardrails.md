---
doc_id: sc-cell-annotation-guardrails
title: Single-Cell Annotation Guardrails
doc_type: knowhow
critical_rule: MUST explain the chosen annotation source and the exact reference/model input before running sc-cell-annotation
domains: [singlecell]
related_skills: [sc-cell-annotation, sc-annotate]
phases: [before_run, on_warning, after_run]
search_terms: [cell annotation, manual annotation, CellTypist, SingleR, scmap, popv, knnpredict, model, reference, 单细胞注释, 参考集, 调参]
priority: 1.0
source_urls:
  - https://celltypist.readthedocs.io/en/latest/celltypist.annotate.html
  - https://bioconductor.org/packages/release/bioc/vignettes/SingleR/inst/doc/SingleR.html
  - https://bioconductor.org/packages/release/bioc/html/scmap.html
---

# Single-Cell Annotation Guardrails

- **Inspect first**: confirm whether the user wants manual relabeling, marker-based annotation, CellTypist, a labeled H5AD reference (`popv` / `knnpredict`), or an R reference path (`singler` / `scmap`).
- **Use normalized expression**: public annotation paths should read normalized expression, not raw counts.
- **Do not auto-cluster in marker mode**: `markers` annotation now expects an existing cluster/label column.
- **Key wrapper controls**: explain `method`, `cluster_key`, `manual_map/manual_map_file`, `model`, `reference`, and `celltypist_majority_voting` before running.
- **Use method-correct language**: `model` is the CellTypist selector; `reference` is either a labeled H5AD (`popv` / `knnpredict`) or an atlas selector / labeled H5AD (`singler` / `scmap`).
- **Disclose fallback honestly**: if CellTypist falls back to `markers`, state both the requested and executed methods.
- **Do not overclaim certainty**: annotation labels are still hypotheses that should be checked against markers and biology.
- **Point to the next step**: after annotation, users often go back to `sc-markers` for support or forward to `sc-de` for condition-aware testing.
- **For detailed parameter strategy**: see `knowledge_base/skill-guides/singlecell/sc-cell-annotation.md`.
