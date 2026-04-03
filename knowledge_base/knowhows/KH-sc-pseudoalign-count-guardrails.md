---
doc_id: sc-pseudoalign-count-guardrails
title: Single-Cell Pseudoalign Count Guardrails
doc_type: knowhow
critical_rule: MUST explain that sc-pseudoalign-count is a pseudoalignment-based alternative handoff path, not a promise of full chemistry coverage across SimpleAF or kb-python
domains: [singlecell]
related_skills: [sc-pseudoalign-count]
phases: [before_run, on_warning, after_run]
search_terms: [simpleaf, alevin-fry, kb-python, pseudoalign count, kallisto bustools, 单细胞伪比对]
priority: 1.0
source_urls:
  - https://simpleaf.readthedocs.io/en/latest/quant-command.html
  - https://kb-python.readthedocs.io/en/stable/autoapi/kb_python/count/
  - https://nf-co.re/scrnaseq/dev/docs/usage
---

# Single-Cell Pseudoalign Count Guardrails

- **Keep scope honest**: this skill provides a pseudoalignment-based count handoff for mainstream droplet scRNA workflows; it does not claim universal chemistry support.
- **Separate backend choice from output contract**: users choose `simpleaf` or `kb_python`, but the OmicsClaw handoff remains `standardized_input.h5ad`.
- **Prefer import when outputs already exist**: if the user already has an importable `h5ad` or matrix output, do not rerun the backend.
- **Be explicit about kb requirements**: real kb-python runs need both an index and a transcript-to-gene map.
- **Do not overpromise protocol coverage**: upstream tools can expose many chemistry knobs, but the current wrapper intentionally prioritizes mainstream 10x-style droplet use first.
- **Use the downstream bridge correctly**: after this skill, the next steps are still `sc-qc`, `sc-preprocessing`, and the rest of the RNA-first stack.
- **For detailed operator guidance**: see `knowledge_base/skill-guides/singlecell/sc-pseudoalign-count.md`.
