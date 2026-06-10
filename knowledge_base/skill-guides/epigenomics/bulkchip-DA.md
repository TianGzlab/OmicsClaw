---
doc_id: skill-guide-bulkchip-DA
title: OmicsClaw Skill Guide — Bulk ChIP Differential Binding
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkchip-DA, bulkchip-da, bulkchip-differential-binding]
search_terms: [bulk ChIP differential binding, pyDESeq2, DESeq2, volcano, contrast, gained lost peaks, DiffBind]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ChIP Differential Binding

**Status**: scaffold-stage guide for `bulkchip-DA`. The entrypoint is a
methodology scaffold; apply this methodology directly. ENCODE ChIP-seq Step 4.

## Purpose

Decide whether a consensus peak count matrix can support a two-condition
differential-binding test, and how to interpret the result as changes in
**occupancy/mark deposition**, not expression.

## Step 1: Inspect The Data First

- **Upstream**: chains off `<project>/peak_calling/result.json` with
  `consensus.count_matrix` (raw featureCounts).
- **Design**: needs ≥ 2 conditions WITH replicates; a single condition or no
  replicates cannot be contrasted — stop and say so.
- **External tools**: pydeseq2, matplotlib.

## Step 2: Understand The Method Path

- pyDESeq2 `DeseqDataSet(design="~condition")` on raw counts → size factors →
  dispersion → Wald test → LFC shrinkage (`apeglm`/`ashr`).
- Threshold up/down at `padj < --padj` and `|log2FC| > --lfc`.
- Outputs: `differential_binding.csv`, `volcano.png`, `up_peaks.bed`,
  `down_peaks.bed`.

Mirrors `bulkatac-DA` exactly (identical count-matrix schema) — accessibility
there, binding here.

## Step 3: Tune Parameters

1. `--treat` / `--control` — set the contrast direction explicitly.
2. `--padj`, `--lfc` — stricter for a higher-confidence set.

## Step 4: What To Say After The Run

- Report the contrast, n gained / lost peaks, and top peaks by padj.
- Describe results as differential **binding** (occupancy), NOT expression.
- Feed `up_peaks.bed` / `down_peaks.bed` into `bulkchip-motif-enrichment` or
  `bulkchip-annotation-enrichment` for biological interpretation.
