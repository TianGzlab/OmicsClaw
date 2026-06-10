---
doc_id: bulkchip-motif-enrichment-guardrails
title: Bulk ChIP Motif Enrichment Guardrails
doc_type: knowhow
critical_rule: MUST verify an upstream peak-calling/DA result.json is chained in, require a HOMER genome, explain the peak subset + size/len before running, interpret motifs by target type (TF expects its own motif; histone marks surface co-bound TFs), and never claim differential binding or annotation
domains: [epigenomics]
related_skills: [bulkchip-motif-enrichment, bulkchip-motif]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ChIP motif enrichment, HOMER, findMotifsGenome, known motifs, de novo motifs, transcription factor motif, ChIP基序富集]
priority: 1.0
---

# Bulk ChIP Motif Enrichment Guardrails

- **Scaffold status**: methodology scaffold — the entrypoint prints a notice and does not execute tools yet. Apply the methodology in the skill guide / `references/methodology.md`.
- **Inspect first**: confirm an upstream `result.json` is resolvable — `bulkchip-peak-calling` (consensus / per-condition) or `bulkchip-DA` (up/down via `--de-result`).
- **Require a HOMER genome**: `findMotifsGenome.pl` needs an installed HOMER genome package (or a FASTA path); without it the run cannot proceed — flag this before claiming results.
- **Explain the run before execution**: state `--peak-subset` (default consensus; up/down need `--de-result`), `--size` (200 = summit-centered point-source default; `given` = full peaks for broad marks), `--len` (8,10,12).
- **Interpret by target type**: TF ChIP → the factor's own motif should top the list (a key quality signal); broad histone marks → co-localized TF motifs, NOT a single "mark motif".
- **Do not overclaim scope**: this skill runs HOMER motif enrichment only — it does NOT call peaks, run differential binding (`bulkchip-DA`), or annotate genes / pathways (`bulkchip-annotation-enrichment`).
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, `motif_enrichment_summary.csv`, and per-subset HOMER dirs (`knownResults.*`, `homerResults.html`).
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkchip-motif-enrichment.md`.
