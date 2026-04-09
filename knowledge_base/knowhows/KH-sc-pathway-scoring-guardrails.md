---
doc_id: sc-pathway-scoring-guardrails
title: Single-Cell Pathway Scoring Guardrails
doc_type: knowhow
critical_rule: MUST distinguish pathway/signature scoring from statistical enrichment testing before running sc-pathway-scoring
domains: [singlecell]
related_skills: [sc-pathway-scoring]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell pathway scoring, aucell, module score, pathway activity, signature score, 单细胞通路打分, 通路活性]
priority: 1.0
source_urls:
  - https://www.bioconductor.org/packages/devel/bioc/vignettes/AUCell/inst/doc/AUCell.html
  - https://scanpy.readthedocs.io/en/stable/generated/scanpy.tl.score_genes.html
---

# Single-Cell Pathway Scoring Guardrails

- **Say what this skill really does**: this skill scores pathway or signature activity per cell; it is not ORA or preranked GSEA significance testing.
- **Explain the workflow first**: for most users this comes after `sc-preprocessing`, and often after `sc-clustering` or `sc-cell-annotation` when grouped summaries matter.
- **Be honest about matrix needs**:
  - `score_genes_py` needs normalized expression in `adata.X`
  - `aucell_r` can rank a count-like source, but grouped biological interpretation still works best after preprocessing
- **Treat gene-set source as first-class input**: users must provide either a local `--gene-sets` GMT file or a built-in `--gene-set-db` library key.
- **Show the real key parameters**:
  - shared: `gene_sets / gene_set_db`, `species`, `groupby`, `top_pathways`
  - `aucell_r`: `aucell_auc_max_rank`
  - `score_genes_py`: `score_genes_ctrl_size`, `score_genes_n_bins`
- **Do not overclaim grouped summaries**: if `groupby` is absent, the run can still score each cell, but grouped pathway summaries will be limited or skipped.
- **Guide the next step honestly**:
  - after pathway scoring, users often continue to `sc-cell-annotation` or `sc-de`
  - if users really want GO/KEGG enrichment significance, they need a separate statistical enrichment workflow
