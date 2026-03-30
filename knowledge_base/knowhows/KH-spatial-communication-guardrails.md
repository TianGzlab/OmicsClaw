---
doc_id: spatial-communication-guardrails
title: Spatial Communication Guardrails
doc_type: knowhow
critical_rule: MUST inspect cell type labels, species support, and explain the selected communication method plus method-specific parameters before running ligand-receptor analysis
domains: [spatial]
related_skills: [spatial-cell-communication, spatial-communication, communication]
phases: [before_run, on_warning, after_run]
search_terms: [cell communication, cell-cell communication, ligand receptor, ligand-receptor, LIANA, CellPhoneDB, FastCCC, CellChat, 细胞通讯, 细胞通信, 配体受体, 调参]
priority: 1.0
---

# Spatial Communication Guardrails

- **Inspect first**: verify the cell type column, number of cell types, and whether the selected labels are biologically interpretable enough for communication analysis.
- **Check species support before promising a method**: current OmicsClaw wrapper supports human and mouse globally, but `cellphonedb` and `fastccc` are effectively human-only.
- **Do not flatten methods into one generic story**: LIANA, CellPhoneDB, FastCCC, and CellChat have different ranking semantics and different core parameters.
- **Explain the run before execution**: state the method and the small set of key parameters that will control the first pass.
- **Respect matrix assumptions**: current `spatial-communication` expects log-normalized expression in `adata.X`; do not describe scaled or z-scored matrices as valid CellPhoneDB input.
- **Preserve the standardized output contract**: method-specific backends may differ internally, but OmicsClaw exports a canonical LR table plus communication summary and signaling-role tables.
- **Keep visualization layers separated**: Python standard gallery is the default analysis layer; R customization should consume `figure_data/` and must not silently recompute communication inference.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/spatial/spatial-communication.md`.
