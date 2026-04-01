---
doc_id: sc-cell-annotation-guardrails
title: Single-Cell Annotation Guardrails
doc_type: knowhow
critical_rule: MUST explain the selected annotation source and the exact reference/model input before running sc-cell-annotation
domains: [singlecell]
related_skills: [sc-cell-annotation, sc-annotate]
phases: [before_run, on_warning, after_run]
search_terms: [cell annotation, CellTypist, SingleR, scmap, model, reference, 单细胞注释, 参考集, 调参]
priority: 1.0
source_urls:
  - https://celltypist.readthedocs.io/en/stable/_modules/celltypist/annotate.html
  - https://celltypist.readthedocs.io/en/stable/notebook/celltypist_tutorial.html
  - https://bioconductor.org/packages/release/bioc/vignettes/SingleR/inst/doc/SingleR.html
  - https://bioconductor.org/packages/SingleR/
---

# Single-Cell Annotation Guardrails

- **Inspect first**: check whether cluster labels already exist and whether the user wants marker-based annotation, CellTypist, or a reference-style path.
- **Key wrapper controls**: explain `method`, `cluster_key`, `model`, and `reference` before running.
- **Use method-correct language**: `model` is the main CellTypist selector; `reference` is the wrapper-level choice for the reference-style path.
- **Do not invent unsupported knobs**: official CellTypist docs also expose options like `majority_voting`, but the current OmicsClaw wrapper does not expose them.
- **Be honest about fallbacks**: `singler` and `scmap` are not full native backends in this wrapper and may fall back instead of providing full upstream functionality.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-cell-annotation.md`.
