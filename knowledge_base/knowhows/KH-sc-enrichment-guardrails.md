---
doc_id: sc-enrichment-guardrails
domain: singlecell
skill: sc-enrichment
critical_rule: MUST distinguish statistical enrichment from per-cell pathway scoring before running sc-enrichment
summary: Guardrails for single-cell ORA / GSEA on marker or DE rankings.
related_skills: [sc-enrichment, sc-pathway-scoring, sc-markers, sc-de]
---

# Guardrails

- **State the question first**:
  - `sc-enrichment` = statistical enrichment on marker / DE rankings
  - `sc-pathway-scoring` = per-cell signature activity
- **Check the upstream source**:
  - clustered h5ad + `groupby` can auto-rank markers
  - `sc-markers` output directory can usually be reused directly
  - `sc-de` output directory is preferred for condition-aware enrichment
- **Do not hide the gene-set source**:
  - user must provide a local GMT/JSON or a built-in database key
  - if a built-in key may require downloading, say so explicitly
- **Explain the installation path simply**:
  - Python side: `sc-enrichment` and `sc-pathway-scoring` share the same `singlecell-enrichment` extra
  - R side: `engine=r` is best installed through conda/mamba prebuilt Bioconductor packages, not ad-hoc source compilation
- **Method meaning**:
  - `ora` for thresholded positive genes
  - `gsea` for full ranked lists
- **Engine meaning**:
  - `engine=auto` prefers the R clusterProfiler path when available
  - `engine=python` keeps the run fully in Python
  - `engine=r` expects `clusterProfiler` and `enrichplot`
- **Point to the next step**:
  - after `sc-enrichment`, users usually go to biological interpretation, `sc-cell-annotation`, or `sc-pathway-scoring`
