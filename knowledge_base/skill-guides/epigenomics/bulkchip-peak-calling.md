---
doc_id: skill-guide-bulkchip-peak-calling
title: OmicsClaw Skill Guide — Bulk ChIP Peak Calling
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkchip-peak-calling]
search_terms: [bulk ChIP peak calling, MACS2, input control, narrowPeak, broadPeak, naive-overlap consensus, featureCounts, FRiP, IDR]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ChIP Peak Calling

**Status**: scaffold-stage guide for `bulkchip-peak-calling`. The entrypoint is
a methodology scaffold; apply this methodology directly. ENCODE ChIP-seq Step 3.
Annotation/enrichment and differential binding live in sibling skills.

## Purpose

Decide whether dedup ChIP + control BAMs are ready for peak calling, and how to
reason about the two ChIP-defining choices: **calling against the input control**
and **narrow vs broad** peak mode.

## Step 1: Inspect The Data First

- **Upstream**: chains off `<project>/mapping/result.json` (with dedup BAMs +
  `control_map`).
- **Pairing**: every ChIP sample must resolve to a matched control via
  `control_map` — MACS2 `-c` is mandatory for ChIP.
- **External tools**: macs2, bedtools, featureCounts (subread), idr.

## Step 2: Understand The Method Path

### Narrow mode (TF / sharp histone marks)

- `macs2 callpeak -t <chip> -c <control> -g <eff_genome> -q <qvalue>
  --keep-dup all` → narrowPeak + summits.

### Broad mode (broad histone marks: H3K9me3/H3K27me3/H3K36me3, ...)

- add `--broad --broad-cutoff <c>` → broadPeak.

`--peak-mode auto` infers per-sample from the antibody label; `narrow`/`broad`
force globally. `--keep-dup all` because Step 2 already deduped.

### Consensus + counts

- ENCODE naive overlap: per condition pool replicate ChIP BAMs → re-call vs
  pooled control → intersect each replicate at `--overlap-fraction` → union
  conditions → `consensus_peaks.bed` → SAF.
- `featureCounts -F SAF` → raw `peak_counts.txt` for `bulkchip-DA`.

### QC

- FRiP per sample (ENCODE sets no hard ChIP cutoff — report-only).
- Optional IDR (`--idr`, point-source only, ≥ 2 replicates/condition).

## Step 3: Tune Parameters

1. `--peak-mode` — confirm narrow vs broad by antibody.
2. `--qvalue` (narrow) / `--broad-cutoff` (broad).
3. `--overlap-fraction` (consensus stringency).
4. `--idr` (point-source reproducibility).

## Step 4: What To Say After The Run

- Report per-sample n_peaks + FRiP and the consensus count.
- Low peak counts / FRiP for a TF: cross-check Step-2 NSC/RSC and the control.
- `peak_counts.txt` is raw — feed columns 7+ to `bulkchip-DA`; do not normalise.
- Do NOT say "annotated" / "motifs found" / "differential binding" — chain
  `peak_calling/result.json` into `bulkchip-DA`, `bulkchip-motif-enrichment`,
  or `bulkchip-annotation-enrichment`.
