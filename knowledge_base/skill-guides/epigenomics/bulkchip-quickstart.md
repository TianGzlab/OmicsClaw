---
doc_id: skill-guide-bulkchip-quickstart
title: OmicsClaw Skill Guide — Bulk ChIP-seq Quickstart
doc_type: method-reference
domains: [epigenomics]
related_skills:
  - bulkchip-preprocessing
  - bulkchip-mapping
  - bulkchip-peak-calling
  - bulkchip-DA
  - bulkchip-motif-enrichment
  - bulkchip-annotation-enrichment
search_terms: [bulk ChIP quick start, ChIP-seq beginner workflow, FASTQ to peaks, ENCODE ChIP pipeline, input control, TF vs histone, 批量ChIP新手流程]
priority: 0.95
---

# OmicsClaw Skill Guide — Bulk ChIP-seq Quickstart

**Status**: beginner-oriented navigation guide for the bulk ChIP-seq chain.
These skills currently ship as methodology scaffolds — the entrypoints print a
notice instead of running tools; apply each skill's methodology guide directly.
This is for **bulk** ChIP-seq, not single-cell, and is distinct from the bulk
ATAC (`bulkatac-*`) chain.

## Who This Is For

Use this when the user says:

- "I have ChIP-seq FASTQ — what is the full ENCODE pipeline order?"
- "我有 ChIP-seq 数据和 input，下一步该做什么？"
- "help me go from raw ChIP reads to peaks, motifs, and target pathways"

## The Full 6-Step Chain

Bulk ChIP-seq in OmicsClaw is a linear chain — each step consumes the previous
step's `result.json`:

1. `bulkchip-preprocessing` — sample-sheet parsing (ChIP↔input pairing), FastQC, adapter trimming
2. `bulkchip-mapping` — Bowtie2/BWA alignment + ENCODE/ChIP QC (NRF/PBC, NSC/RSC, fingerprint)
3. `bulkchip-peak-calling` — MACS2 vs input control (narrow/broad), consensus, featureCounts, FRiP
4. `bulkchip-DA` — pyDESeq2 differential binding for one contrast
5. `bulkchip-motif-enrichment` — HOMER motif enrichment + de novo discovery
6. `bulkchip-annotation-enrichment` — peak→gene annotation + GO/KEGG functional enrichment

Steps 5 and 6 are **parallel downstream branches** off peaks (or DA up/down
subsets): motif enrichment answers *which sequences*, annotation/enrichment
answers *which genes/pathways*. Run both for full interpretation.

## What Makes ChIP Different From ATAC

- **Input/IgG control is mandatory** — every ChIP sample is paired with a
  control sample in the sheet and called with `MACS2 -c`.
- **Narrow vs broad** — TFs / sharp marks → narrow peaks; broad histone marks
  (H3K9me3/H3K27me3/H3K36me3) → `--broad`.
- **ChIP QC** uses NSC/RSC cross-correlation + deepTools fingerprint (not ATAC's
  TSS enrichment / fragment-length ladder).
- **No footprinting** — TOBIAS is ATAC-only; the ChIP downstream is
  annotation + functional enrichment.

## A Beginner-Friendly Command Sequence

Keep every step under one project directory so chaining is obvious.

```bash
oc run bulkchip-preprocessing --input samplesheet.tsv --genome hg38 --output chip_run/preprocessing
oc run bulkchip-mapping       --input chip_run/preprocessing/result.json --genome hg38 --output chip_run/mapping
oc run bulkchip-peak-calling  --input chip_run/mapping/result.json --peak-mode auto --output chip_run/peak_calling
oc run bulkchip-DA            --input chip_run/peak_calling/result.json --treat treated --control control --output chip_run/DA
oc run bulkchip-motif-enrichment      --input chip_run/peak_calling/result.json --output chip_run/motif
oc run bulkchip-annotation-enrichment --input chip_run/peak_calling/result.json --output chip_run/annotation
```

The sample sheet needs columns `sample, condition, replicate, R1 [, R2],
control, antibody [, peak_mode]` — the `control` column is what pairs each ChIP
to its input.

## The Main User Mistakes To Prevent

1. **Calling ChIP peaks without a control** — ENCODE requires a matched
   input/IgG; `bulkchip-peak-calling` errors if a ChIP sample has no control.
2. **Using narrow mode for broad histone marks** — set `--peak-mode broad` (or
   let `auto` infer from the antibody label) for H3K9me3/H3K27me3/H3K36me3.
3. **Expecting ATAC QC** — ChIP reports NSC/RSC + fingerprint, not TSS
   enrichment / fragment-length NFR.
4. **Running DA on a single-condition cohort** — `bulkchip-DA` needs ≥ 2
   conditions with replicates.
5. **Looking for footprinting** — there is no ChIP footprinting skill; use
   `bulkchip-annotation-enrichment` for the gene/pathway downstream.

## Simple Decision Rule For Routing

- "ChIP-seq FASTQ / raw ChIP reads" → `bulkchip-preprocessing`
- "I have ChIP BAMs" → `bulkchip-peak-calling` (chain off a mapping result)
- "which peaks change between conditions?" → `bulkchip-DA`
- "which TF motifs are enriched?" → `bulkchip-motif-enrichment`
- "which genes / pathways do the peaks regulate?" → `bulkchip-annotation-enrichment`
- "ATAC-seq" → the `bulkatac-*` chain; "single-cell" → outside this chain.
