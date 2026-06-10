---
doc_id: bulkchip-peak-calling-guardrails
title: Bulk ChIP Peak Calling Guardrails
doc_type: knowhow
critical_rule: MUST verify a Step-2 bulkchip-mapping result.json is chained in, ALWAYS call MACS2 against the matched input control, pick narrow vs broad mode correctly, explain q-value/broad-cutoff/overlap before running, and never claim annotation/enrichment/motifs/differential-binding — this skill stops at the consensus count matrix + FRiP
domains: [epigenomics]
related_skills: [bulkchip-peak-calling]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ChIP peak calling, MACS2, input control, narrowPeak, broadPeak, naive overlap consensus, featureCounts, FRiP, IDR, ChIP峰检测]
priority: 1.0
---

# Bulk ChIP Peak Calling Guardrails

- **Scaffold status**: methodology scaffold — the entrypoint prints a notice and does not execute tools yet. Apply the methodology in the skill guide / `references/methodology.md`.
- **Inspect first**: confirm a Step-2 `mapping/result.json` (with dedup ChIP + control BAMs and `control_map`) is resolvable via `--prev-result` (alias `--input`) or sibling-detected next to `--output`.
- **Control is mandatory**: every ChIP sample is called with `MACS2 -c <control>` resolved from `control_map`; a ChIP sample with no matched input is an error (ENCODE requirement). Never call ChIP peaks without a control.
- **Narrow vs broad**: TFs / sharp marks → narrow `--qvalue` (default 0.05); broad histone marks (H3K9me3/H3K27me3/H3K36me3, ...) → `--broad --broad-cutoff` (default 0.1). `--peak-mode auto` infers from the antibody label; confirm the choice.
- **Do not overclaim scope**: this skill calls peaks, builds the ENCODE naive-overlap consensus, the featureCounts matrix, and FRiP (+ optional IDR) — it does NOT annotate (`bulkchip-annotation-enrichment`), find motifs (`bulkchip-motif-enrichment`), or run differential binding (`bulkchip-DA`).
- **Explain the run before execution**: state `--peak-mode`, `--qvalue`/`--broad-cutoff`, `--overlap-fraction` (default 0.5), `--threads`, and whether `--idr` is set (point-source only; needs ≥ 2 replicates/condition).
- **Interpret outputs correctly**: `peak_counts.txt` holds raw featureCounts (columns 7+) for DESeq2/edgeR — do NOT normalise here; ENCODE sets no hard ChIP FRiP cutoff (report-only tier).
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, `peak_calling_summary.csv`, `peaks/<sample>/`, `consensus/` (`consensus_peaks.bed/.saf`, `peak_counts.txt`), `qc/{frip,IDR}/`.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkchip-peak-calling.md`.
