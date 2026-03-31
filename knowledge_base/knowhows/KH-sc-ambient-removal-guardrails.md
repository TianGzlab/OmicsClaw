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
- **Key wrapper controls**: explain `method`, `contamination`, `expected_cells`, `raw_h5`, `raw_matrix_dir`, and `filtered_matrix_dir`.
- **Use method-correct language**: `simple` uses a wrapper-level contamination fraction; `cellbender` relies on `expected_cells`; `soupx` requires raw and filtered matrices.
- **Do not invent hidden knobs**: official CellBender docs also discuss `total-droplets-included`, but the current OmicsClaw wrapper does not expose it.
- **Do not fake SoupX readiness**: if the required raw/filtered inputs are missing, say the wrapper will fall back instead of pretending full SoupX control is available.

