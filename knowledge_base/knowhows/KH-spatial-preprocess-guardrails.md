---
doc_id: spatial-preprocess-guardrails
title: Spatial Preprocess Guardrails
doc_type: knowhow
critical_rule: MUST inspect platform type, count preservation, and explain the effective QC thresholds plus graph parameters before running preprocessing
domains: [spatial]
related_skills: [spatial-preprocessing, spatial-preprocess, preprocess]
phases: [before_run, on_warning, after_run]
search_terms: [spatial preprocess, spatial preprocessing, spatial QC, visium preprocess, xenium preprocess, normalize, leiden, umap, 空间预处理, 质控, 调参]
priority: 1.0
---

# Spatial Preprocess Guardrails

- **Inspect first**: confirm the platform or file type, whether the matrix in `X` still contains raw counts, and whether spatial coordinates are present. If the user only has FASTQ pairs plus barcode-coordinate metadata, route to `spatial-raw-processing` first.
- **Do not hide preset behavior**: when `--tissue` is used, explain the resolved QC thresholds rather than only mentioning the preset name.
- **Separate loader hints from scientific parameters**: `data_type`, `species`, and `tissue` are wrapper-level controls; `n_top_hvg`, `n_neighbors`, and `leiden_resolution` map to the actual preprocessing workflow.
- **Explain the run before execution**: state the effective QC thresholds and the main graph / clustering parameters that will control the first pass.
- **Preserve raw counts correctly**: downstream spatial skills assume preprocessing keeps raw counts in `adata.layers["counts"]` and `adata.raw`.
- **Use method-correct language**: current OmicsClaw `spatial-preprocess` exposes one implemented workflow, `scanpy_standard`; do not imply that multiple preprocessing backends already exist unless they are truly implemented.
- **Be explicit about missing coordinates**: preprocessing can still run without spatial coordinates, but downstream spatial plotting and some skills will be limited.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-preprocess.md`.
