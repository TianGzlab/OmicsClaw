---
doc_id: skill-guide-bulkatac-mapping
title: OmicsClaw Skill Guide — Bulk ATAC Mapping
doc_type: method-reference
domains: [epigenomics]
related_skills: [bulkatac-mapping]
search_terms: [bulk ATAC mapping, alignment, Bowtie2, BWA, ENCODE BAM filter, NRF, PBC1, PBC2, TSS enrichment, fragment length, RPGC BigWig]
priority: 0.8
---

# OmicsClaw Skill Guide — Bulk ATAC Mapping

**Status**: implementation-aligned guide derived from the current OmicsClaw
`bulkatac-mapping` skill. This guide explains the real wrapper behavior,
public parameter semantics, and method-selection logic. It is ENCODE Step 2
(alignment + post-alignment QC); peak calling and downstream analysis live in
sibling skills.

## Purpose

Use this guide when you need to decide:

- whether trimmed FASTQs from `bulkatac-preprocessing` are ready for alignment
- how to explain the Bowtie2 vs BWA choice without overclaiming scope
- how to reason about the ENCODE BAM filter, library-complexity metrics, and
  the opt-in cross-sample downsampling debate
- how to interpret TSS enrichment and fragment-length QC

This is Step 2 of the 6-step bulk ATAC chain. It has **no `--demo` flag** — to
smoke-test, run `bulkatac-preprocessing --demo` first and chain off its
`result.json`.

## Step 1: Inspect The Data First

Before running mapping, check:

- **Upstream result**:
  - the skill chains off `<project>/preprocessing/result.json` produced by
    `bulkatac-preprocessing`
  - pass it via `--prev-result` (alias `--input`), or let sibling-detection
    find `preprocessing/result.json` next to `--wd`
  - hard-fails if neither resolves
- **Genome**:
  - `--genome` must resolve — CLI overrides the value carried from Step 1; if
    both are absent the run hard-fails
- **Aligner index**:
  - a pre-built Bowtie2 or BWA index can be passed; otherwise the reference
    FASTA + ENCODE blacklist are auto-downloaded and indexed into `--ref-dir`
  - `--bwa-index` and `--bowtie2-index` are mutually exclusive, and the index
    format must match `--aligner`
- **External tools**:
  - `bowtie2` or `bwa` (matching `--aligner`), `samtools`, `deeptools`;
    `bedtools` only when a blacklist subtract triggers; `wget`/`curl` only for
    auto-download

Important implementation notes in current OmicsClaw:

- BAMs are **not** Tn5-shifted (+4/-5) — the offset is deliberately left to
  downstream tools (TOBIAS `ATACorrect`, MACS2 `--shift`/`--extsize`).
  Pre-shifting here would double-correct.
- MAPQ ≥ 30 is hard-coded in the ENCODE filter; it is not a CLI flag.
- Auto-downloading a reference writes ~3-5 GB and can take 30-60 min wall
  clock on hg38/mm10; subsequent runs reuse the index.

## Step 2: Choose The Aligner Deliberately

### `bowtie2` (default)

Best when:

- you want the ENCODE / CebolaLab standard ATAC alignment path
- the dataset is standard short-read paired-end ATAC

Wrapper behavior:

- paired-end: `--very-sensitive --no-mixed --no-discordant -I 25 -X 700` —
  retains only proper pairs with insert size 25–700 bp
- single-end: `--very-sensitive` (no insert-size constraint)

### `bwa` (opt-in via `--aligner bwa`)

Best when:

- you want BWA MEM to match an existing lab pipeline

Wrapper behavior:

- `bwa mem -t <threads>` with default flags (no `-k`/`-r`/`-M` overrides)
- uniqueness is enforced downstream by the ENCODE `-q 30` filter, not by BWA

After alignment both paths go through the same ENCODE filter chain:
ENCODE BAM filter → chrM removal → `samtools markdup -r` → optional blacklist
subtract → NRF/PBC1/PBC2 → optional cross-sample downsample.

## Step 3: Tune Parameters In A Stable Order

### Reference and blacklist

1. `--genome` (or rely on the Step-1 value)
2. `--bowtie2-index` / `--bwa-index` (skip download)
3. `--blacklist` / `--no-blacklist`

Guidance:

- supply a pre-built index whenever one exists — it skips the slow download
- `--no-blacklist` disables the ENCODE blacklist subtract; keep it on for
  hg38/mm10 to drop artefact-prone regions

### QC tiering

1. `--cell-type`

Guidance:

- `--cell-type cell_line` raises the TSS-enrichment tier cutoffs
  (`> 7.0` ideal, `> 5.0` acceptable); tissue cohorts use `> 5.0` / `> 3.0`
- omitting `--cell-type` still computes the TSS score but skips tier labels

### Downsampling

1. `--downsample`

Guidance:

- OFF by default — ENCODE relies on RPGC for visualisation and DESeq2/edgeR
  size factors for differential accessibility
- turn it ON when one sample is markedly shallower than the others; Reske
  et al. 2020 (PMID 32321567) showed complexity differences confound DA
- when set, all samples are downsampled to `min(n_usable)` across the cohort

`--keep-intermediates` retains `raw`/`filtered`/`no_mito` BAMs for debugging.

## Step 4: Show An Effective Run Summary Before Execution

Before execution, summarize the real run in a compact block, for example:

```text
About to run bulk ATAC mapping
  Upstream: <project>/preprocessing/result.json
  Aligner: bowtie2 (ENCODE PE params -I 25 -X 700)
  Genome: hg38 | reference: auto-download to reference_hg38/
  ENCODE filter: -F 1804 -f 2 -q 30 (PE), MAPQ >= 30 hard-coded
  Blacklist subtract: on | downsample: off | cell-type: cell_line
  Note: BAMs are NOT Tn5-shifted by design.
```

## Step 5: What To Say After The Run

- If usable depth is low: MAPQ ≥ 30 drops MAPQ 1–29 reads — substantial on
  repeat-rich genomes; check `align_rate` and `n_uniquely_mapped`.
- If NRF / PBC1 / PBC2 are low: report a PCR-bottleneck concern — `PBC1 < 0.50`
  is severe; these come from the deduplicated BAM per the ENCODE SOP.
- If %mito is high: many reads landed on chrM before removal — flag library
  quality.
- If the fragment-length plot loses nucleosome periodicity: suspect
  over-digestion or low signal-to-noise.

## Step 6: Explain Outputs Correctly

When summarizing results:

- describe `report.md` as the four-section markdown summary (alignment,
  post-alignment QC, ENCODE thresholds, usable-read rule)
- describe `result.json` as the chained envelope carrying `mapping`,
  `qc_after_mapping`, `encode_qc_thresholds`, `genome_files`, and the
  forward-carried `sample_sheet`
- describe `mapping_summary.csv` as the per-sample alignment + complexity table
  (align rate, %mito, NRF/PBC, tiers, downsample target)
- describe `bam/<sample>.dedup.bam` as the filtered + deduplicated BAM
  (renamed `.no_blacklist.bam` when a blacklist applied); `.ds.bam` only with
  `--downsample`
- describe `bigwig/<sample>.rpgc.bw` as the RPGC-normalised deepTools track
- describe `qc_after_mapping/` as TSS-enrichment profiles + fragment-length
  histograms + cohort overlays plus `qc_after_mapping_summary.csv`

Do **not** say "peaks called" or "differential accessibility computed" — this
skill stops at filtered BAMs + QC. Pass `<project>/mapping/result.json` into
`bulkatac-peak-calling` to continue the chain.
