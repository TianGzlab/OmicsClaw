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
- **Standardize external inputs first**: if the object comes from outside OmicsClaw and matrix provenance is unclear, recommend `sc-standardize-input` before annotation.
- **Key wrapper controls**: explain `method`, `cluster_key`, `model`, and `reference` before running.
- **Use method-correct language**: `model` is the main CellTypist selector; `reference` is the wrapper-level choice for the reference-style path.
- **Do not invent unsupported knobs**: official CellTypist docs also expose options like `majority_voting`, but the current OmicsClaw wrapper does not expose them.
- **Respect the matrix contract**: marker scoring, CellTypist, SingleR, and scmap should read log-normalized expression, preferably from `adata.raw`; do not describe raw counts as direct input for these methods.
- **Disclose fallback honestly**: if CellTypist input validation fails or the model cannot run, the wrapper can fall back to `markers`; report both the requested and executed methods.
- **Stop when the biological selector is still ambiguous**: do not blindly keep the default CellTypist model or default SingleR/scmap reference without user confirmation when those choices materially affect the label story.
- **Be honest about runtime dependencies**: `singler` requires an R environment with SingleR, celldex, SingleCellExperiment, and zellkonverter; `scmap` is a public method and requires `scmap` plus the same R bridge stack.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-cell-annotation.md`.
