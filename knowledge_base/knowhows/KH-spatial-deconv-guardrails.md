---
doc_id: spatial-deconv-guardrails
title: Spatial Deconvolution Guardrails
doc_type: knowhow
critical_rule: MUST inspect reference labels, matrix type, and explain the selected deconvolution method plus method-specific parameters before running
domains: [spatial]
related_skills: [spatial-deconvolution, spatial-deconv, deconv]
phases: [before_run, on_warning, after_run]
search_terms: [spatial deconvolution, cell type deconvolution, cell proportion, cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, CARD, 空间去卷积, 细胞比例, 调参]
priority: 1.0
---

# Spatial Deconvolution Guardrails

- **Inspect first**: verify that the reference h5ad exists, the selected `cell_type_key` is biologically meaningful, and enough shared genes exist between spatial and reference data.
- **Do not flatten matrix assumptions**: `cell2location`, `rctd`, `destvi`, `stereoscope`, and `card` are count-based; `tangram` and `spotlight` should use non-negative normalized expression; `flashdeconv` is more flexible in the current wrapper but still needs spatial coordinates and shared genes.
- **Explain the run before execution**: state the chosen method and the small set of parameters that actually control the first pass.
- **Use method-correct language**: do not present all deconvolution methods as interchangeable "cell proportion estimators" without mentioning their assumptions, training behavior, or spatial priors.
- **Respect reference constraints**: current OmicsClaw RCTD wrapper drops cell types with fewer than 25 reference cells before running spacexr; this should be explained instead of hidden.
- **Keep CARD imputation separate from base deconvolution**: enabling imputation adds an extra refinement step and should be described as such.
- **Preserve the standardized output contract**: the canonical OmicsClaw output is `tables/proportions.csv` plus derived summaries and reproducibility files, regardless of backend.
- **Keep visualization layers separated**: Python standard gallery is the default analysis layer; R customization should consume `figure_data/` and must not silently rerun deconvolution.
- **Use uncertainty exports deliberately**: assignment margin and normalized entropy are the current wrapper's standard ambiguity summaries; do not describe them as calibrated posterior probabilities.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-deconv.md`.
