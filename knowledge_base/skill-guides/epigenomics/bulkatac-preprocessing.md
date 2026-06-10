---
doc_id: skill-guide-bulkatac-preprocessing
title: OmicsClaw Skill Guide — Bulk ATAC Preprocessing
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkatac-preprocessing, bulkatac-preprocess]
search_terms: [bulk ATAC preprocessing, FASTQ QC, adapter trimming, fastp, Trim Galore, Nextera adapter, ENCODE ATAC, sample sheet]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ATAC Preprocessing

**Status**: implementation-aligned guide derived from the current OmicsClaw
`bulkatac-preprocessing` skill. This guide explains the real wrapper behavior,
public parameter semantics, and method-selection logic. It is ENCODE Step 1
only (data loading + adapter trimming); alignment, peak calling, and downstream
analysis live in sibling skills.

## Purpose

Use this guide when you need to decide:

- whether the input is raw bulk ATAC-seq FASTQ that still needs preprocessing
- how to explain the fastp vs Trim Galore choice without overclaiming scope
- how to tune the adapter, quality, and length filters before alignment
- how the `--demo` GSE66386 path differs from a real run

This skill is the entry point of the 6-step bulk ATAC chain
(preprocessing → mapping → peak-calling → DA → motif-enrichment → footprinting).
It is the only step that has a `--demo` flag.

## Step 1: Inspect The Data First

Before running preprocessing, check:

- **Read state**:
  - the wrapper assumes raw, untrimmed FASTQ(s) straight off the sequencer
  - if the reads are already adapter-trimmed, skip this skill and go directly
    to `bulkatac-mapping`
- **Sample sheet**:
  - a TSV/CSV with columns `sample, condition, replicate, R1 [, R2]`
  - single-end vs paired-end is auto-detected from presence/absence of `R2`
  - the sheet must have at least one row; multi-condition and arbitrary
    replicate counts are supported
- **Assay type**:
  - this is the bulk ATAC path — for single-cell ATAC use
    `scatac-preprocessing`, and the skill is not for ChIP-seq / CUT&RUN
- **External tools**:
  - `fastp` or `Trim Galore` must be on `PATH` (at least one for `--tool auto`)
  - `fastqc` is optional — skipped silently with a warning if absent
  - `--demo` additionally needs `sra-tools` and network access

Important implementation notes in current OmicsClaw:

- `--input` or `--demo` is required; one of the two must be set.
- `--genome` is metadata only — trimming never touches a reference sequence.
  In `--demo` mode it is silently coerced to `sacCer3` with a warning.
- All artifacts land directly under `--output` (the per-skill layout); there is
  no nested `preprocessing/` subdirectory.
- `--wd` and `--output` are aliases for the same path.

## Step 2: Choose The Trimmer Deliberately

### `fastp` (default when available)

Best when:

- you want the fastest multi-threaded trimming
- you want a machine-readable `<sample>_fastp.json` for downstream tooling
- you want overlap-based adapter detection in addition to the explicit adapter

Wrapper behavior:

- honours `--threads` (genuinely multi-threaded)
- sliding-window quality trimming: window = 4 bp, mean Phred ≥ `--quality`
- discards reads shorter than `--min-length` after trimming
- emits paired `<sample>_R{1,2}_trimmed.fastq.gz` + `_fastp.json` + `_fastp.html`

### `trim_galore` (fallback / opt-in via `--tool trim_galore`)

Best when:

- you specifically need cutadapt-driven adapter matching
- you want to harmonize with a Trim-Galore-based lab pipeline

Wrapper behavior:

- wraps cutadapt; thread count is capped (~8 useful threads regardless of
  `--threads`)
- same Nextera adapter, same quality/length cutoffs
- native `<sample>_R{1,2}_val_{1,2}.fq.gz` output is renamed to the shared
  `<sample>_R{1,2}_trimmed.fastq.gz` convention by `_lib`

`--tool auto` resolves to fastp when it is on `PATH`. The resolved value is
written back into `result.json["params"]["tool"]` — it is never logged as
`auto`, so inspect that field to confirm which trimmer actually ran.

## Step 3: Tune Parameters In A Stable Order

### Adapter

1. `--adapter`

Guidance:

- the default is the Nextera transposase adapter `CTGTCTCTTATACACATCT` — correct
  for standard Tn5-based ATAC libraries
- override only for non-Nextera library prep chemistries

### Quality and length filters

Tune in this order:

1. `--quality`
2. `--min-length`

Guidance:

- `--quality` defaults to Q20 (mean Phred over the sliding window)
- raise `--quality` to Q25 when base-quality tails are poor
- `--min-length` defaults to 36 bp — the ENCODE ATAC pipeline minimum
- raise `--min-length` (e.g. 30–50 bp) if very short post-trim reads inflate
  multi-mapping during alignment; lower it cautiously for short-read runs

### FastQC and demo depth

- `--no-fastqc` skips the optional per-FASTQ FastQC reports (faster iteration)
- `--demo-n-reads` (default 50,000) controls per-FASTQ subsampling in demo mode
  only — enough for sane fastp + alignment QC numbers under a minute

Important warning:

- these filters do not validate the assay — passing scATAC or ChIP-seq FASTQ
  through this skill will still produce trimmed output without complaint

## Step 4: Show An Effective Run Summary Before Execution

Before execution, summarize the real run in a compact block, for example:

```text
About to run bulk ATAC preprocessing
  Mode: real input (samplesheet.tsv) | genome metadata: hg38
  Trimmer: fastp (resolved from --tool auto)
  Adapter: CTGTCTCTTATACACATCT (Nextera default)
  Quality filter: mean Phred >= 20 | min length: 36 bp
  FastQC: on
  Output: <project>/preprocessing  (per-skill layout, no nested subdir)
```

## Step 5: What To Say After The Run

- If many reads were dropped: revisit `--quality` and `--min-length`.
- If adapter content stays high in FastQC: confirm `--adapter` matches the
  library chemistry.
- If demo mode is slow on first run: it is fetching ~12 SRR accessions from
  SRA into `<output>/../fastq/` (~1 GB before subsampling); subsequent demo
  runs reuse the downloads.
- Always state which trimmer actually ran by reading
  `result.json["params"]["tool"]` — never report `auto`.

## Step 6: Explain Outputs Correctly

When summarizing results:

- describe `report.md` as the markdown summary users should read first
- describe `result.json` as the structured envelope — `steps_completed`,
  `sample_sheet`, and the per-sample `preprocessing` array carrying
  `r1_trimmed` / `r2_trimmed` paths
- describe `fastq_trimmed/` as the trimmed FASTQs plus per-sample QC reports
- describe `fastq_trimmed/trimmed_summary.csv` as the per-sample stats table
  (reads in/out, % kept, Q30 rate, adapter %) — note it is NOT under a
  `tables/` directory, so consume it via `result.json["preprocessing"]`
- describe `reproducibility/commands.sh` as the resolved re-run command
- describe demo-only `demo_samplesheet.tsv` + `fastq/` as demo *input* written
  to `--output`'s **parent**, deliberately kept out of the artifact namespace

Do **not** say "alignment completed" or "peak calling completed" — this skill
only loads data and trims adapters. Pass `<project>/preprocessing/result.json`
into `bulkatac-mapping` to continue the chain.
