---
doc_id: skill-guide-bulkatac-peak-calling
title: OmicsClaw Skill Guide — Bulk ATAC Peak Calling
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkatac-peak-calling]
search_terms: [bulk ATAC peak calling, MACS2, narrowPeak, naive-overlap consensus, featureCounts, FRiP, IDR, peak annotation, HOMER]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ATAC Peak Calling

**Status**: implementation-aligned guide derived from the current OmicsClaw
`bulkatac-peak-calling` skill. This guide explains the real wrapper behavior,
public parameter semantics, and method-selection logic. It is ENCODE Step 3
(peak calling, consensus, annotation, post-peak QC); differential accessibility
and downstream analysis live in sibling skills.

## Purpose

Use this guide when you need to decide:

- whether deduplicated BAMs from `bulkatac-mapping` are ready for peak calling
- how to explain MACS2 parameter derivation for PE vs SE input
- how to reason about the ENCODE naive-overlap consensus and the
  featureCounts count matrix that feeds differential accessibility
- how to interpret FRiP, peak counts, and the optional IDR reproducibility

This is Step 3 of the 6-step bulk ATAC chain. It has **no `--demo` flag** — to
smoke-test, run the full Step 1 → 2 chain first and chain off
`mapping/result.json`.

## Step 1: Inspect The Data First

Before running peak calling, check:

- **Upstream result**:
  - the skill chains off `<project>/mapping/result.json` produced by
    `bulkatac-mapping`
  - pass it via `--prev-result` (alias `--input`), or let sibling-detection
    find `mapping/result.json` next to `--wd`
  - hard-fails if neither resolves
- **Layout**:
  - paired-end vs single-end comes from Step 2's `sample_sheet` — there is no
    override, and it determines the MACS2 model used
- **Annotation source**:
  - peak annotation needs a GTF or HOMER; the GTF is auto-detected from Step 2's
    `genome_files`, and `--gtf` overrides it
  - if neither GTF nor HOMER is available, annotation is silently skipped with
    a warning and the report's Step 3b section is absent
- **External tools**:
  - `macs2` (≥ 2.2), `samtools`, `bedtools` (≥ 2.30), `featureCounts` (≥ 2.0),
    `deeptools`; `annotatePeaks.pl` (HOMER) optional; `idr` only with `--idr`

Important implementation notes in current OmicsClaw:

- `--keep-dup all` is supplied to MACS2 internally — duplicates were already
  removed by `samtools markdup -r` in Step 2, so MACS2 must not double-filter.
- The `qvalue<q>` tag is baked into most output subdirectories; re-running with
  a different `--qvalue` writes a parallel tree rather than overwriting.

## Step 2: Understand The Method Path

There is one peak caller (MACS2); the parameter set is chosen by layout.

### Paired-end input

- `macs2 callpeak --format BAMPE --nomodel -g <eff_genome_size> -q <qvalue>`
- BAMPE uses the actual fragment endpoints, so the empirical shift/extsize
  model is unnecessary — `--shift` / `--extsize` are **ignored** for PE input

### Single-end input

- `--shift -37 --extsize 73 --nomodel` — the half-nucleosome window (73 bp)
  centered on the Tn5 cut site; `--shift -37` recenters the read on the
  insertion site (ENCODE / Buenrostro 2013 default)

### Consensus, count matrix, annotation, QC

- **Consensus (ENCODE naive overlap)**: per condition, pool replicate BAMs →
  re-call MACS2 on the pooled set → intersect with each replicate at
  `--overlap-fraction` reciprocal overlap → union conditions via `bedtools
  merge` into `consensus_peaks.bed`
- **Count matrix**: `featureCounts -F SAF` on `consensus_peaks.saf` using
  full-depth dedup BAMs (PE uses `-p --countReadPairs` fragment counting);
  raw counts ready for DESeq2 / edgeR
- **Annotation**: HOMER `annotatePeaks.pl` when available and the genome is
  HOMER-recognised, else GTF-based `bedtools closest`
- **Post-peak QC**: FRiP per sample, TSS + peak-centered heatmaps, PCA
  (DESeq2 VST) and sample correlation when ≥ 2 conditions, optional IDR

## Step 3: Tune Parameters In A Stable Order

### Significance threshold

1. `--qvalue`

Guidance:

- defaults to `0.05` (ENCODE standard)
- lower to `0.01` for a stricter, higher-confidence peak set
- remember the value is baked into output subdirectory names

### Consensus stringency

1. `--overlap-fraction`

Guidance:

- defaults to `0.50` (ENCODE reciprocal-overlap standard)
- lower (e.g. `0.30`) for a more permissive consensus — more peaks survive
  replicate disagreement

### Single-end model (SE only)

1. `--shift`
2. `--extsize`

Guidance:

- leave the `-37` / `73` half-nucleosome defaults unless harmonising with
  another pipeline; they have no effect on PE input

### Stage toggles

- `--skip-annotation` — skip Step 3b for faster iteration / no GTF dependency
- `--skip-qc` — skip Step 3c (the count matrix is still produced)
- `--idr` — opt-in ENCODE IDR; needs ≥ 2 replicates per condition, conditions
  with a single replicate are silently skipped

## Step 4: Show An Effective Run Summary Before Execution

Before execution, summarize the real run in a compact block, for example:

```text
About to run bulk ATAC peak calling
  Upstream: <project>/mapping/result.json
  Caller: MACS2 | layout: paired-end -> --format BAMPE --nomodel
  q-value: 0.05 | consensus overlap fraction: 0.50
  Annotation: HOMER (or GTF bedtools-closest fallback)
  Post-peak QC: FRiP + heatmaps + PCA (>= 2 conditions) | IDR: off
  Output tree tagged qvalue0.05/
```

## Step 5: What To Say After The Run

- If peak counts are low: report the ENCODE tier from `peak_count_tier`;
  consider relaxing `--qvalue` or `--overlap-fraction`.
- If FRiP is low: `> 0.3` is ideal, `> 0.2` acceptable — low FRiP signals poor
  signal-to-noise; cross-check Step 2 TSS enrichment.
- If the Step 3b section is missing from the report: no GTF and no HOMER were
  available — provide `--gtf` or install HOMER and re-run.
- If PCA / sample-correlation output is absent: the cohort had only one
  condition (`≥ 2` required); the count matrix is still emitted.
- If IDR output is sparse: conditions with a single replicate were skipped.

## Step 6: Explain Outputs Correctly

When summarizing results:

- describe `report.md` as the four-section markdown summary (peak calling,
  annotation, post-peak QC, disclaimer)
- describe `result.json` as the chained envelope carrying `peak_calling`,
  `consensus`, `genome_files`, and the forward-carried `mapping` + `sample_sheet`
- describe `peak_calling_summary.csv` as per-sample peak counts + ENCODE tier,
  with a final literal `consensus` row
- describe `consensus/qvalue<q>/consensus_peaks.bed` as the final naive-overlap
  consensus (0-based BED) and `consensus_peaks.saf` as the 1-based featureCounts
  annotation
- describe `consensus/qvalue<q>/peak_counts.txt` as the featureCounts raw count
  matrix (peaks × samples) — feed columns 7+ to DESeq2 / edgeR, do not normalise
- describe `annotation/qvalue<q>/` as per-condition pies + TSS-distance
  histograms; `qc_after_peak_calling/` as FRiP, PCA, correlation, optional IDR

Do **not** say "differential accessibility computed" or "motifs found" — this
skill stops at peaks + consensus + QC. Pass
`<project>/peak_calling/result.json` into `bulkatac-DA` to continue the chain.
