---
doc_id: spatial-register-guardrails
title: Spatial Registration Guardrails
doc_type: knowhow
critical_rule: MUST inspect slice labels, slice count, and explain the selected registration method plus method-specific parameters before running
domains: [spatial]
related_skills: [spatial-registration, spatial-register, register]
phases: [before_run, on_warning, after_run]
search_terms: [spatial registration, slice alignment, coordinate alignment, PASTE, STalign, multi-slice, 空间配准, 切片对齐, 调参]
priority: 1.0
---

# Spatial Registration Guardrails

- **Inspect first**: verify that a real slice-label column exists and that spatial coordinates are present.
- **Do not fabricate slice structure**: if no slice column exists, the run should stop and the user should be told to supply `--slice-key` or create an appropriate label column.
- **Choose the method intentionally**: PASTE and STalign solve different registration problems and should not be described as interchangeable.
- **Respect slice-count constraints**: current OmicsClaw STalign wrapper is pairwise-only; PASTE is the correct current wrapper choice for 3 or more slices.
- **Explain the run before execution**: state the reference slice, slice key, and the small set of method-specific parameters that will control the first pass.
- **Separate upstream from wrapper controls**: `paste_alpha`, `paste_dissimilarity`, and `paste_use_gpu` are public PASTE controls, while `stalign_image_size` and `use_expression` are current OmicsClaw wrapper-level controls around the STalign workflow.
- **Preserve the output contract**: aligned coordinates must land in `adata.obsm["spatial_aligned"]`, with figures and metrics exported through the standard OmicsClaw layout.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-register.md`.
