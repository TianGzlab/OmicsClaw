---
doc_id: spatial-enrichment-guardrails
title: Spatial Enrichment Guardrails
doc_type: knowhow
critical_rule: MUST separate ORA, preranked GSEA, and ssGSEA conceptually before running spatial enrichment
domains: [spatial]
related_skills: [spatial-enrichment, enrichment]
phases: [before_run, on_warning, after_run]
search_terms: [spatial enrichment, pathway enrichment, gene set enrichment, enrichr, GSEA, ssGSEA, GO, Reactome, MSigDB, 空间富集, 通路富集, 调参]
priority: 1.0
---

# Spatial Enrichment Guardrails

- **Inspect first**: verify the `groupby` column, confirm `adata.X` is suitable for marker ranking or group-level scoring, and check whether the user wants thresholded ORA, ranked-list GSEA, or score-style ssGSEA.
- **Do not collapse methods together**: `enrichr` is ORA on positive markers, `gsea` uses the full ranked list, and `ssgsea` in the current wrapper is a group-level scoring layer.
- **Explain the gene-set source before running**: state whether the run will use a local built-in library, a local `.gmt` / `.json` file, or an externally resolved library key.
- **Keep pathway interpretation significance-first**: do not pre-filter terms by keywords instead of statistical ranking and biological context.
- **Keep the visualization layers separated**: Python gallery outputs are the canonical analysis layer; any optional R plotting should read `figure_data/` and must not recompute enrichment statistics.
- **Use method-correct language**: NES-based GSEA output, ORA overlap-based output, and ssGSEA scores are not interchangeable evidence.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-enrichment.md`.
