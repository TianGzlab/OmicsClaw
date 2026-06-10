---
doc_id: skill-guide-bulkchip-motif-enrichment
title: OmicsClaw Skill Guide — Bulk ChIP Motif Enrichment
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkchip-motif-enrichment, bulkchip-motif]
search_terms: [bulk ChIP motif enrichment, HOMER, findMotifsGenome, known motifs, de novo motifs, transcription factor motif]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ChIP Motif Enrichment

**Status**: scaffold-stage guide for `bulkchip-motif-enrichment`. The entrypoint
is a methodology scaffold; apply this methodology directly. ChIP-seq Step 5a.

## Purpose

Decide which peak subset to scan with HOMER and how to interpret motif results
by ChIP target type.

## Step 1: Inspect The Data First

- **Upstream**: `bulkchip-peak-calling` (consensus / per-condition) or
  `bulkchip-DA` (up/down via `--de-result`).
- **HOMER genome**: `findMotifsGenome.pl` needs an installed HOMER genome
  package or a FASTA path — flag if absent.

## Step 2: Understand The Method Path

- `findMotifsGenome.pl <peaks.bed> <genome> <out> -size <size> -len <len>
  -p <threads>`.
- `-size 200` centers a 200 bp window on summits (point-source default);
  `-size given` scans full intervals (broad marks).
- Emits known-motif enrichment (`knownResults.txt`) + de novo motifs
  (`homerResults.html`).

## Step 3: Tune Parameters

1. `--peak-subset` (consensus / condition / up / down; up/down need
   `--de-result`).
2. `--size` (200 vs given).
3. `--len` (de novo motif widths).

## Step 4: What To Say After The Run

- For TF ChIP: the factor's own motif should rank at/near the top — call this
  out as a quality signal.
- For histone marks: report co-localized TF motifs, not a single "mark motif".
- Do NOT claim differential binding or gene/pathway annotation — those are
  `bulkchip-DA` and `bulkchip-annotation-enrichment`.
