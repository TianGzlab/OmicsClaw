---
doc_id: sc-standardize-input-guardrails
title: Single-Cell Input Standardization Guardrails
doc_type: knowhow
critical_rule: MUST explain that sc-standardize-input fixes structural AnnData contract issues but does not invent missing biology, sample metadata, or analysis intent
domains: [singlecell]
related_skills: [sc-standardize-input]
phases: [before_run, on_warning, after_run]
search_terms: [single-cell standardize input, AnnData contract, counts layer, gene symbols, input normalization, 单细胞输入整理, 格式标准化]
priority: 1.0
---

# Single-Cell Input Standardization Guardrails

- **Explain scope honestly**: this skill standardizes AnnData structure and provenance; it does not filter cells, normalize expression, annotate biology, or guess missing sample design.
- **Inspect first**: identify whether counts are most trustworthy in `layers['counts']`, `adata.raw`, or `adata.X`, and whether gene symbols are available in `var_names` or metadata columns such as `gene_symbols`.
- **Do not fabricate missing metadata**: if the user later wants DE, batch integration, cell communication, or annotation, say clearly that standardization cannot invent `groupby`, `sample_key`, `batch_key`, `cell_type`, or reference/model choices.
- **Use this skill as a hand-off step**: when users drop in an external `.h5ad` and ask for downstream analysis, recommend standardizing first so later scRNA skills see a stable contract.
- **Explain the output contract**: after a successful run, users should understand that `processed.h5ad` is the file to pass into downstream OmicsClaw scRNA skills.
- **For detailed operator guidance**: see `knowledge_base/skill-guides/singlecell/sc-standardize-input.md`.
