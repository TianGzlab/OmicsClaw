---
doc_id: sc-doublet-detection-guardrails
title: Single-Cell Doublet Detection Guardrails
doc_type: knowhow
critical_rule: MUST explain the chosen backend's real control knobs before running sc-doublet-detection and MUST not overclaim automatic removal
domains: [singlecell]
related_skills: [sc-doublet-detection, sc-doublet]
phases: [before_run, on_warning, after_run]
search_terms: [doublet detection, Scrublet, DoubletDetection, DoubletFinder, scDblFinder, scds, expected doublet rate, 单细胞双细胞]
priority: 1.0
source_urls:
  - https://github.com/swolock/scrublet
  - https://github.com/JonathanShor/DoubletDetection
  - https://github.com/chris-mcginnis-ucsf/DoubletFinder
  - https://bioconductor.org/packages/release/bioc/vignettes/scDblFinder/inst/doc/scDblFinder.html
  - https://bioconductor.org/packages/release/bioc/html/scds.html
---

# Single-Cell Doublet Detection Guardrails

- **Inspect first**: confirm whether the data came from one capture or multiple captures/samples, because expected doublet burden and Scrublet batching strategy depend on capture structure.
- **Use method-correct language**:
  - `threshold` only applies to `scrublet`
  - `batch_key` only affects the current `scrublet` wrapper
  - `doubletdetection_n_iters` is the main public tuning knob for `doubletdetection`
  - `scds_mode` only applies to `scds`
- **Do not pretend `expected_doublet_rate` means the same thing for every backend**: it drives Scrublet / DoubletFinder / scDblFinder / scds in the current wrapper, but for `doubletdetection` it is only recorded as context.
- **Preserve matrix semantics honestly**: doublet detection should use raw count-like input when possible, but it should not silently rewrite a normalized `adata.X`.
- **Stop when raw counts are unavailable**: do not run if neither `layers["counts"]`, aligned `adata.raw`, nor count-like `adata.X` exists.
- **Disclose fallbacks explicitly**: if `doubletfinder` falls back to `scdblfinder`, state both the requested and executed methods.
- **Do not overclaim removal**: this skill labels doublets in `obs`; it does not drop cells automatically.
- **After the run**: guide the user to review the calls first, then keep singlets and rerun preprocessing / clustering if the final analysis should exclude doublets.
- **For detailed parameter strategy and interpretation**: see `knowledge_base/skill-guides/singlecell/sc-doublet-detection.md`.
