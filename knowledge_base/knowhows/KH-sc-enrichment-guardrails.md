---
doc_id: sc-enrichment-guardrails
title: Single-Cell Enrichment Guardrails
doc_type: knowhow
critical_rule: MUST verify the gene-set source and explain AUCell's cell-wise scoring semantics before running sc-enrichment
domains: [singlecell]
related_skills: [sc-enrichment]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell enrichment, aucell, pathway activity, gene set scoring, 单细胞富集, 通路活性]
priority: 1.0
source_urls:
  - https://www.bioconductor.org/packages/devel/bioc/vignettes/AUCell/inst/doc/AUCell.html
  - https://github.com/aertslab/AUCell
---

# Single-Cell Enrichment Guardrails

- **Inspect first**: confirm that the gene-set file matches the gene identifier space of the input object.
- **Standardize external inputs first when provenance is unclear**: recommend `sc-standardize-input` for object hygiene, but remember that enrichment still depends on the user-supplied gene-set file matching the feature IDs.
- **Key wrapper controls**: explain `gene_sets`, `groupby`, `top_pathways`, and `aucell_auc_max_rank` before running.
- **Use method-correct language**: AUCell scores per-cell gene-set activity from within-cell gene rankings; it is not a cluster-level over-representation test.
- **Explain grouped summaries honestly**: if the requested `groupby` column is missing, the wrapper can still score per-cell AUCell activity but grouped summaries will be absent.
- **Do not invent unsupported backends**: the current `sc-enrichment` wrapper exposes only the AUCell Bioconductor path.
- **Do not overclaim thresholding**: the current wrapper scores AUCell activity but does not expose automatic threshold assignment as a public OmicsClaw control.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-enrichment.md`.
