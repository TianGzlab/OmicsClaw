---
doc_id: bulkchip-DA-guardrails
title: Bulk ChIP Differential Binding Guardrails
doc_type: knowhow
critical_rule: MUST verify a Step-3 bulkchip-peak-calling result.json with a consensus count matrix is chained in, require >= 2 conditions with replicates, feed RAW counts to pyDESeq2, explain the contrast + thresholds, and describe results as differential BINDING (occupancy), not expression
domains: [epigenomics]
related_skills: [bulkchip-DA, bulkchip-da, bulkchip-differential-binding]
phases: [before_run, on_warning, after_run]
search_terms: [bulk ChIP differential binding, pyDESeq2, DESeq2, volcano, contrast, gained lost peaks, DiffBind, ChIP差异结合]
priority: 1.0
---

# Bulk ChIP Differential Binding Guardrails

- **Scaffold status**: methodology scaffold — the entrypoint prints a notice and does not execute tools yet. Apply the methodology in the skill guide / `references/methodology.md`.
- **Inspect first**: confirm a Step-3 `peak_calling/result.json` with `consensus.count_matrix` is resolvable via `--prev-result` (alias `--input`) or sibling-detected next to `--output`.
- **Require a valid design**: pyDESeq2 needs ≥ 2 conditions WITH replicates; a single-condition or no-replicate cohort cannot be contrasted — say so and stop, do not fabricate a contrast.
- **Raw counts only**: feed the raw featureCounts matrix to pyDESeq2 — it computes its own size factors; pre-normalised input biases dispersion.
- **Explain the run before execution**: state the resolved `--treat` (numerator) / `--control` (denominator) contrast, `--padj` (default 0.05), `--lfc` (default 1.0).
- **Use the right language**: results are differential **binding** (factor occupancy / mark deposition at peaks), NOT differential expression. Do not equate gained peaks with up-regulated genes.
- **Preserve the contract**: successful runs emit `report.md`, `result.json`, `differential_binding.csv` (peak, baseMean, log2FC, pvalue, padj), `volcano.png`, `up_peaks.bed`, `down_peaks.bed`.
- **For detailed method strategy**: see `knowledge_base/skill-guides/epigenomics/bulkchip-DA.md`.
