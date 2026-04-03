---
doc_id: sc-ambient-removal-guardrails
title: Single-Cell Ambient RNA Guardrails
doc_type: knowhow
critical_rule: MUST explain the selected ambient-removal path and its true required inputs before running sc-ambient-removal
domains: [singlecell]
related_skills: [sc-ambient-removal]
phases: [before_run, on_warning, after_run]
search_terms: [ambient RNA, CellBender, SoupX, contamination fraction, raw h5, 单细胞环境RNA, 背景污染, 调参]
priority: 1.0
source_urls:
  - https://cellbender.readthedocs.io/en/v0.2.0/getting_started/remove_background/
  - https://cellbender.readthedocs.io/en/v0.1.0/help_and_reference/remove_background/index.html
  - https://github.com/constantAmateur/SoupX
---

# Single-Cell Ambient RNA Guardrails

- **Inspect first**: verify whether the user actually has `raw_h5` or paired raw/filtered 10x directories, because the method choice depends on those files.
- **Standardize external inputs first when provenance is unclear**: recommend `sc-standardize-input` for the main AnnData, but do not pretend that it replaces CellBender raw `.h5` or SoupX raw/filtered 10x directories.
- **Key wrapper controls**: explain `method`, `contamination`, `expected_cells`, `raw_h5`, `raw_matrix_dir`, and `filtered_matrix_dir`.
- **Use method-correct language**: `simple` uses a wrapper-level contamination fraction; `cellbender` relies on `expected_cells`; `soupx` requires raw and filtered matrices.
- **Enforce the input contract**: the current CellBender wrapper only accepts raw 10x `.h5` input; if the user only has processed `.h5ad`, do not try to run CellBender.
- **Exploit the shared input contract**: for the `simple` path, prefer `layers['counts']`, then aligned `adata.raw`, then count-like `adata.X`; recommend `sc-standardize-input` when provenance is unclear.
- **Do not invent hidden knobs**: official CellBender docs also discuss `total-droplets-included`, but the current OmicsClaw wrapper does not expose it.
- **Describe outputs honestly**: for CellBender, treat `cellbender_output/` as the native method output bundle and `corrected.h5ad` as OmicsClaw's downstream-ready wrapper export.
- **Use the right diagnostics**: direct before/after count scatter plots are only valid on shared barcodes; when the corrected output is a filtered subset, prefer barcode-rank or distribution plots.
- **Do not fake SoupX readiness**: if the required raw/filtered inputs are missing, say the wrapper will fall back and report both the requested and executed methods instead of pretending full SoupX control is available.
- **Stop when the requested method needs extra files you do not have**: do not silently keep a sophisticated method name if the user has not confirmed the matching raw 10x assets.
- **Do not guess CellBender priors from droplet-only input**: if `--input` is absent, require `--expected-cells` explicitly instead of inferring it from the raw `.h5`.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-ambient-removal.md`.
