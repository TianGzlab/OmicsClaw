---
doc_id: sc-qc-guardrails
title: Single-Cell QC Guardrails
doc_type: knowhow
critical_rule: MUST inspect matrix type, gene naming convention, and explain that sc-qc is diagnostic-only before running single-cell QC
domains: [singlecell]
related_skills: [sc-qc]
phases: [before_run, on_warning, after_run]
search_terms: [scRNA QC, single-cell QC, mitochondrial percentage, ribosomal percentage, genes per cell, library size, 质量控制, 线粒体比例, 调参]
priority: 1.0
---

# Single-Cell QC Guardrails

- **Inspect first**: confirm the input still looks count-like, the gene symbols resemble the selected species convention, and the user understands this step is for diagnostics rather than filtering.
- **Standardize external inputs first when provenance is unclear**: recommend `sc-standardize-input` before QC when counts or gene-symbol provenance are uncertain, but keep that recommendation in preflight rather than the raw loader.
- **Do not fake method choice**: current OmicsClaw `sc-qc` exposes one public QC path, `qc_metrics`; do not describe multiple QC backends unless they are truly implemented.
- **Treat `--species` honestly**: it is a wrapper-level control for mitochondrial and ribosomal prefix detection, but it directly affects `%MT` and `%ribo` estimates.
- **Explain the run before execution**: state the selected species and mention that ribosomal percentage is computed automatically in the current wrapper.
- **Do not overclaim thresholds**: QC plots support threshold choice, but the skill itself does not decide or apply filtering cutoffs.
- **Flag gene naming mismatches**: if symbols do not use expected human or mouse prefixes, warn that mitochondrial / ribosomal percentages may be incomplete.
- **Use the shared preflight honestly**: `sc-qc` may continue with warnings when counts are available but gene-symbol conventions are weak; only hard-block when no raw count-like matrix can be found.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-qc.md`.
