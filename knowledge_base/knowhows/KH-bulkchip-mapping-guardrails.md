---
doc_id: bulkchip-mapping-guardrails
title: Bulk ChIP Mapping Guardrails
doc_type: knowhow
critical_rule: MUST verify a Step-1 bulkchip-preprocessing result.json is chained in, explain the aligner and ENCODE BAM filter before running, and report ChIP signal-to-noise via NSC/RSC + fingerprint (NOT ATAC TSS-enrichment/fragment-length) — this skill stops at dedup BAMs + ChIP QC
domains: [epigenomics]
related_skills: [bulkchip-mapping, bulkchip-alignment]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ChIP mapping, Bowtie2, BWA, ENCODE BAM filter, NRF PBC, NSC RSC cross-correlation, deepTools fingerprint, ChIP比对]
priority: 1.0
---

# Bulk ChIP Mapping Guardrails

- **Scaffold status**: methodology scaffold — the entrypoint prints a notice and does not execute tools yet. Apply the methodology in the skill guide / `references/methodology.md`.
- **Inspect first**: confirm a Step-1 `preprocessing/result.json` is resolvable via `--prev-result` (alias `--input`) or sibling-detected next to `--output`. Controls are aligned alongside ChIP samples.
- **Do not overclaim scope**: this skill aligns, ENCODE-filters, dedups, computes NRF/PBC1/PBC2, and runs ChIP QC (NSC/RSC + fingerprint) + bigWig — it does NOT call peaks (`bulkchip-peak-calling`) or annotate.
- **ChIP QC ≠ ATAC QC**: report signal-to-noise via strand cross-correlation (NSC > 1.05, RSC > 0.8) and the deepTools ChIP-vs-input fingerprint. Do NOT report TSS enrichment or the fragment-length nucleosome ladder — those are ATAC-specific.
- **Stricter PBC2**: ENCODE ChIP wants PBC2 > 10 (ATAC: > 3); usable-read depth is peak-mode dependent (≥20 M TF/narrow, ≥45 M broad histone).
- **No Tn5 shift**: ChIP BAMs are not `+4/-5` shifted; the fragment offset is estimated by cross-correlation and applied by MACS2 (SE) in Step 3.
- **Preserve the contract**: successful runs emit `report.md`, `result.json` (carrying `mapping`, `qc_after_mapping`, `control_map`, `genome_files`), `mapping_summary.csv`, `bam/`, `bigwig/`, `qc_after_mapping/{cross_correlation,fingerprint}/`.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkchip-mapping.md`.
