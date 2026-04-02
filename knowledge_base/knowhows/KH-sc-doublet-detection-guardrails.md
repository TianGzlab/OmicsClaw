---
doc_id: sc-doublet-detection-guardrails
title: Single-Cell Doublet Detection Guardrails
doc_type: knowhow
critical_rule: MUST explain the expected doublet-rate assumption before running sc-doublet-detection and must not invent unsupported backend-specific tuning knobs
domains: [singlecell]
related_skills: [sc-doublet-detection, sc-doublet]
phases: [before_run, on_warning, after_run]
search_terms: [doublet detection, Scrublet, DoubletFinder, scDblFinder, expected doublet rate, 单细胞双细胞, 双细胞检测, 调参]
priority: 1.0
source_urls:
  - https://github.com/swolock/scrublet
  - https://github.com/chris-mcginnis-ucsf/DoubletFinder
  - https://bioconductor.org/packages/release/bioc/vignettes/scDblFinder/inst/doc/scDblFinder.html
---

# Single-Cell Doublet Detection Guardrails

- **Inspect first**: confirm whether the input is a single capture or mixed samples, because doublet expectations depend on capture structure.
- **Key wrapper controls**: explain `method`, `expected_doublet_rate`, and `threshold` before running.
- **Use method-correct language**: `threshold` only applies to the Scrublet path in the current wrapper.
- **Do not invent unsupported knobs**: official DoubletFinder and scDblFinder document extra controls such as `pK`, `nExp`, `dbr`, `samples`, or `clusters`, but the current OmicsClaw wrapper does not expose them.
- **Do not overclaim removal**: this skill annotates doublets in `obs`; it does not silently drop them from the dataset.
- **For detailed parameter strategies**: see `knowledge_base/skill-guides/singlecell/sc-doublet-detection.md`.
