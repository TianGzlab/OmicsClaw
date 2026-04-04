---
doc_id: sc-metacell-guardrails
title: Single-Cell Metacell Guardrails
doc_type: knowhow
critical_rule: MUST explain that metacells are aggregation units for stability and compression, not new biological ground-truth cell types
domains: [singlecell]
related_skills: [sc-metacell]
phases: [before_run, after_run]
search_terms: [metacell, seacells, aggregation, compression, denoise]
priority: 1.0
source_urls:
  - https://github.com/dpeerlab/SEACells
---

# Single-Cell Metacell Guardrails

- **Inspect first**: confirm the embedding used for aggregation is biologically meaningful.
- **Explain the abstraction honestly**: metacells stabilize downstream analyses, but they can blur rare states if compression is too aggressive.
- **Do not oversell fallback methods**: a lightweight clustering average is not equivalent to SEACells.
- **Report compression level**: always state how many cells were summarized into how many metacells.
- **For longer tuning and interpretation guidance**: see `knowledge_base/skill-guides/singlecell/sc-metacell.md`.
