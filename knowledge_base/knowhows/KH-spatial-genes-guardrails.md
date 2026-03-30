---
doc_id: spatial-genes-guardrails
title: Spatial SVG Analysis Guardrails
doc_type: knowhow
critical_rule: MUST inspect matrix type and coordinates, then explain the selected SVG method plus method-specific parameters before running
domains: [spatial]
related_skills: [spatial-genes, spatial-svg-detection, genes]
phases: [before_run, on_warning, after_run]
search_terms: [spatially variable gene, spatial gene, SVG, Moran, SpatialDE, SPARK-X, FlashS, spatial autocorrelation, spatial pattern, 空间变异基因, 空间基因, SVG分析, 莫兰, 空间模式, 调参]
priority: 1.0
---

# Spatial SVG Analysis Guardrails

- **Inspect first**: verify spatial coordinates and determine whether the dataset provides log-normalized expression in `adata.X`, raw counts in `layers["counts"]`, or `adata.raw`.
- **Do not mix matrix assumptions**: `morans` is a log-expression baseline, while `spatialde`, `sparkx`, and `flashs` should preferentially use raw counts.
- **Choose the method intentionally**: use Moran's I as a strong baseline on many datasets; use FlashS or SPARK-X first on very large data; use SpatialDE when smooth gradients or AEH-style grouping are the actual goal.
- **Explain the run before execution**: state the method and the small set of key parameters that will control the first pass.
- **Use method-correct language**: do not describe all outputs as generic p-value rankings; score meaning differs across Moran's I, SpatialDE, SPARK-X, and FlashS.
- **Keep visualization layers separate**: Python standard gallery is the canonical OmicsClaw output; optional R plotting should read `figure_data/` and focus on presentation, not recomputation.
- **Preserve the gallery contract**: when extending the skill, prefer adding new `PlotSpec` recipe entries and new exported `figure_data/` tables instead of hard-coding one-off plotting branches.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-genes.md`.
