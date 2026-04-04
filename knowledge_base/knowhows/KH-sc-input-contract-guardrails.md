---
doc_id: sc-input-contract-guardrails
title: Single-Cell Input Contract Guardrails
doc_type: knowhow
critical_rule: MUST decide whether the input can be standardized safely, whether key scientific parameters need user confirmation, or whether required metadata/content is missing and analysis must pause
domains: [singlecell]
related_skills: [sc-standardize-input, sc-qc, sc-preprocessing, sc-filter, sc-ambient-removal, sc-doublet-detection, sc-cell-annotation, sc-pseudotime, sc-velocity, sc-batch-integration, sc-de, sc-markers, sc-grn, sc-cell-communication, sc-enrichment]
phases: [before_run, on_warning]
search_terms: [singlecell input contract, standardize input, missing metadata, ask user, confirm parameters, insufficient data, 单细胞输入合同, 缺少元数据, 参数确认]
priority: 1.0
---

# Single-Cell Input Contract Guardrails

- **Auto-canonicalize when safe, export explicitly only when useful**: if the user drops in an external `.h5ad` or count matrix, downstream scRNA skills should prefer the shared canonicalization helper first; `sc-standardize-input` is the optional explicit wrapper when the user wants to inspect or export the canonical object itself.
- **Keep matrix semantics explicit**: `adata.layers["counts"]` is the stable raw-count source, `adata.X` is the current active matrix for the current stage, and `adata.raw` must not be described as universally meaning raw counts or universally meaning normalized expression without checking `adata.uns["omicsclaw_matrix_contract"]`.
- **Continue automatically only when defaults are operational, not scientific**: safe examples include wrapper defaults such as a standard plotting path or a first-pass Python backend; do not auto-pick a biologically meaningful grouping, reference atlas, or replicate design.
- **Stop and ask for user confirmation when multiple scientific choices are plausible**: examples include ambiguous `species`, multiple possible `cluster_key` / `cell_type` / `batch_key` / `sample_key` columns, unclear `groupby` / `group1` / `group2`, or several possible annotation references/models.
- **Stop and ask for missing metadata when the data cannot answer the question yet**: for example, pseudobulk DE without replicate/sample metadata, cell communication without cell-type labels, batch integration without a real batch column, or annotation without a usable reference/model choice.
- **Fail clearly when required matrix content is missing**: examples include no raw count-like matrix for count-based workflows, no spliced/unspliced layers for velocity, or missing raw/filtered 10x inputs for CellBender or SoupX.
- **Do not hide user decisions inside fallback logic**: automatic fallback is acceptable for technical runtime issues, but not for silently changing the biological question or picking an unconfirmed key parameter.
- **For detailed operator guidance**: see `knowledge_base/skill-guides/singlecell/sc-standardize-input.md`.
