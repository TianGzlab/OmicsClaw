---
doc_id: skill-guide-bulkatac-footprinting
title: OmicsClaw Skill Guide — Bulk ATAC Footprinting
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkatac-footprinting]
search_terms: [bulk ATAC footprinting, TOBIAS, Tn5 bias correction, ATACorrect, ScoreBigwig, BINDetect, TF binding, JASPAR, differential binding]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ATAC Footprinting

**Status**: implementation-aligned guide derived from the current OmicsClaw
`bulkatac-footprinting` skill. This guide explains the real wrapper behavior,
public parameter semantics, and method-selection logic. It does not imply
that scATAC footprinting or TF-to-DA integration are already exposed.

## Purpose

Use this guide when you need to decide:

- whether the input is suitable for TF footprinting right now
- how to explain the TOBIAS pipeline (ATACorrect → ScoreBigwig → BINDetect →
  PlotAggregate) without overclaiming scope
- how to choose the motif database and the differential-contrast ordering
- how to read footprint scores, bound/unbound calls, and the differential
  volcano correctly

## Step 1: Inspect The Data First

Before running footprinting, check:

- **Upstream state**:
  - the wrapper chains off `bulkatac-peak-calling`'s `result.json` — it does
    not start from FASTQs or raw BAMs
  - the `mapping` chain must be present so BAM paths resolve; the script walks
    `prev_result` back to Step 2 if Step 3 didn't carry it
  - if Step 3 predates the mapping-chain change, re-run peak-calling to
    refresh `result.json`
- **BAM state**:
  - BAMs must NOT be Tn5-shifted upstream — TOBIAS `ATACorrect` applies the
    +4/-5 offset and corrects sequence bias internally; pre-shifted BAMs would
    double-correct (`bulkatac-mapping` produces unshifted BAMs by design)
- **Conditions**:
  - with ≥ 2 conditions BINDetect runs a differential contrast; with 1
    condition it silently degrades to single-condition mode (per-TF binding
    scores only, no volcano)
- **Genome / motifs**:
  - the genome FASTA is auto-detected from Step 2 (`.fai` auto-built); the
    JASPAR 2024 CORE set is auto-downloaded by organism group on first run
- **Workflow scope**:
  - footprinting asks which TFs are actively *bound* in vivo — distinct from
    `bulkatac-motif-enrichment` (where motifs accumulate) and `bulkatac-DA`
    (replicate-aware accessibility on peak counts)

Important implementation notes in current OmicsClaw:

- The engine is TOBIAS (Bentsen et al. 2020), run in an isolated
  `omicsclaw_tobias` sub-env auto-provisioned on first use.
- `samtools` and `bedtools` are the only hard-checked PATH prerequisites;
  TOBIAS itself is not on the current PATH.
- BINDetect needs no biological replicates — statistical power comes from
  per-TFBS spatial testing, not replication.

## Step 2: Understand The TOBIAS Sub-Steps

The pipeline is fixed; there is no method switch. Know what each stage does.

### ATACorrect — Tn5 bias correction

- learns the per-position Tn5 insertion-sequence bias from the genome FASTA
  around observed cut sites and subtracts it from the per-condition pileup
- signal at peaks is normalised to `10M / reads_in_peaks` so depth
  differences between conditions don't dominate
- emits a `corrected.bw` / `uncorrected.bw` / `bias.bw` / `expected.bw`
  quartet plus a QC PDF; the `corrected.bw` is the canonical downstream signal

### ScoreBigwig — per-base footprint scoring

- slides over the corrected signal and computes a footprint score per base —
  high values mark a protected window (likely TF occupancy) with flanking
  accessible cuts

### BINDetect — motif scan, binding classification, differential analysis

- scans JASPAR PWMs across the merged consensus peaks → one TFBS BED per TF
- classifies each TFBS as bound / unbound from the bimodal footprint-score
  distribution
- with ≥ 2 conditions: computes per-TF log2 binding-change and a one-sample
  t-test against ~100 random genomic-background log2FCs; a quantile
  normalisation is applied before differential testing
- the p-value reflects how anomalous a TF's binding shift is vs background —
  NOT how reproducible it is across biological replicates

### PlotAggregate — top-TF aggregate footprints

- renders aggregate footprint profiles for the top 20 TFs (by binding score
  in single-condition mode, or differential change with ≥ 2 conditions)

## Step 3: Tune Parameters In A Stable Order

### Motif database

Tune in this order:

1. `--motifs`

Guidance:

- leave `--motifs` unset to auto-download the JASPAR 2024 CORE set matching
  the genome's organism group (vertebrates / plants / insects / fungi /
  nematodes)
- pass `--motifs /path/to/local.jaspar` for offline / proxied environments
  or to use a curated PWM set

Important warning:

- unknown genomes silently fall back to JASPAR vertebrates — for any
  exotic organism pass `--motifs` explicitly so motifs are not mis-routed

### Differential contrast ordering

Tune in this order:

1. `--treat`
2. `--control`

Guidance:

- these flags only set BINDetect's numerator/denominator ordering for the
  log2 binding-change — they do NOT affect significance
- omit them and BINDetect picks alphabetically (consistent with
  `bulkatac-DA`'s auto-contrast)

### Genome and blacklist

Guidance:

- `--genome-fasta` overrides the Step-2 auto-detected reference
- `--blacklist` overrides the auto-detected ENCODE blacklist BED (optional)
- `--threads` parallelises the TOBIAS sub-tools

## Step 4: Show An Effective Run Summary Before Execution

Before execution, summarize the real run in a compact block, for example:

```text
About to run bulk ATAC footprinting
  Engine: TOBIAS (ATACorrect -> ScoreBigwig -> BINDetect -> PlotAggregate)
  Conditions: T0, T15 (differential mode)
  Contrast ordering: treat=T15, control=T0
  Motifs: JASPAR2024 CORE (auto, organism group from genome)
  Note: BAMs must be unshifted; ATACorrect handles the +4/-5 offset.
```

## Step 5: What To Say After The Run

- If `is_differential` is `false`: only one condition was detected — per-TF
  binding scores are still emitted, but no differential volcano.
- If motifs look wrong for the organism: the JASPAR auto-routing fell back to
  vertebrates — re-run with `--motifs` pointing at the correct set.
- If the JASPAR download fails: the run hit the network on first use — supply
  `--motifs` from a local cache for offline environments.
- If BAM paths fail to resolve: the Step-3 `result.json` predates the
  mapping-chain change — re-run `bulkatac-peak-calling`.
- If a TF's differential p-value is significant: that means its binding shift
  is anomalous vs genomic background, not that it is replicate-reproducible.

## Step 6: Explain Outputs Correctly

When summarizing results:

- describe `atacorrect/<cond>/<prefix>_corrected.bw` as the Tn5-bias-corrected
  signal (the canonical downstream track); `_uncorrected` / `_bias` /
  `_expected` are reference / diagnostic tracks
- describe `atacorrect/<cond>/<prefix>_atacorrect.pdf` as the bias-correction
  QC PDF
- describe `footprints/<cond>/<cond>_footprints.bw` as the per-base footprint
  score BigWig — larger values mean a deeper protein-protection footprint
- describe `bindetect/bindetect_results.txt` as the per-TF table — TF
  identity, `total_tfbs`, per-condition mean score and bound count, plus the
  log2 binding-change and t-test p-value (differential mode only)
- describe `bindetect/bindetect_figures.pdf` as TOBIAS's built-in score
  distributions and per-TF volcanos
- describe `bindetect/<TF>/beds/<TF>_<cond>_all.bed` (with `_bound` /
  `_unbound` siblings) as the per-TF, per-condition scanned TFBSs
- describe `top_tf_ranking.tsv` as the canonical top-TF short-list for
  downstream interpretation
- describe `plots/aggregate/aggregate_<tf>.png` as the aggregate footprint
  profile per top TF
- describe `plots/tf_differential_volcano.{pdf,png}` as the per-TF
  differential-binding volcano — emitted only with ≥ 2 conditions
- describe `result.json["footprinting"]` as the structured envelope; check
  `bindetect.is_differential` before calling the run a contrast

Do **not** say a TF is "differentially expressed" — footprinting measures
binding occupancy, not transcript abundance. Do **not** present the BINDetect
p-value as a replicate-reproducibility statistic.

OmicsClaw is a research and educational tool for multi-omics analysis. It is
not a medical device and does not provide clinical diagnoses. Consult a
domain expert before making decisions based on these results.
