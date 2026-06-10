---
doc_id: skill-guide-bulkchip-preprocessing
title: OmicsClaw Skill Guide — Bulk ChIP Preprocessing
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkchip-preprocessing, bulkchip-preprocess]
search_terms: [bulk ChIP preprocessing, FASTQ adapter trimming, fastp, Trim Galore, FastQC, input control pairing, Illumina adapter]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ChIP Preprocessing

**Status**: scaffold-stage guide for the `bulkchip-preprocessing` skill. The
entrypoint is a methodology scaffold (prints a notice, no tool execution yet);
apply this methodology directly until `_lib/preprocessing.py` is implemented.
This is ENCODE ChIP-seq Step 1.

## Purpose

Use this guide to decide whether raw ChIP-seq FASTQs are ready for alignment and
how to validate the **ChIP↔input/IgG control pairing** — the defining ChIP-seq
preprocessing concern that ATAC does not have.

## Step 1: Inspect The Data First

- **Sample sheet**: TSV/CSV with `sample, condition, replicate, R1 [, R2],
  control, antibody [, peak_mode]`.
  - Input/IgG samples have `is_control=true` (or an empty `antibody`).
  - Build `control_map = {chip → control}` and **fail fast** if a ChIP sample
    names a missing control.
- **Layout**: paired vs single end inferred from the `R2` column.
- **External tools**: FastQC, fastp / Trim Galore.

## Step 2: Understand The Method Path

- Trim with fastp (default) or Trim Galore (`--tool`, `auto` → fastp).
- Adapter: Illumina universal `AGATCGGAAGAGC` (TruSeq) — **not** the ATAC
  Nextera adapter; ChIP libraries are TruSeq.
- Quality `--quality` (Q20), min length `--min-length` (20; ENCODE processable
  25 bp, recommended 50 bp).

## Step 3: Tune Parameters

1. `--tool` (fastp vs trim_galore) — lab convention.
2. `--quality`, `--min-length` — stricter for low-quality runs.
3. `--no-fastqc` — skip reports for speed.

`--genome` and `peak_mode` are metadata only; they are stashed for
`bulkchip-mapping` / `bulkchip-peak-calling`.

## Step 4: What To Say After The Run

- Report per-sample reads in/out and % passing from
  `fastq_trimmed/trimmed_summary.csv`.
- Confirm every ChIP sample has a trimmed control alongside it.
- Do NOT claim alignment, ChIP QC, or peaks — chain
  `preprocessing/result.json` into `bulkchip-mapping`.
