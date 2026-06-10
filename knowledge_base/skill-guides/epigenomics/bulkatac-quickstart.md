---
doc_id: skill-guide-bulkatac-quickstart
title: OmicsClaw Skill Guide — Bulk ATAC-seq Quickstart
doc_type: method-reference
domains: [epigenomics]
related_skills:
  - bulkatac-preprocessing
  - bulkatac-mapping
  - bulkatac-peak-calling
  - bulkatac-DA
  - bulkatac-motif-enrichment
  - bulkatac-footprinting
search_terms: [bulk ATAC quick start, ATAC-seq beginner workflow, FASTQ to peaks, ENCODE ATAC pipeline, novice guide, 批量ATAC新手流程]
priority: 0.95
---

# OmicsClaw Skill Guide — Bulk ATAC-seq Quickstart

**Status**: beginner-oriented navigation guide for users who do not already
know which bulk ATAC-seq skill to run first.

## Who This Is For

Use this guide when the user says something like:

- “我有 bulk ATAC-seq FASTQ，下一步该做什么？”
- “帮我从原始 ATAC 数据一步步跑到 peaks 和 motif”
- “I have ATAC-seq reads — what is the full ENCODE pipeline order?”

This guide is intentionally opinionated and follows the current OmicsClaw bulk
ATAC chain. It is for **bulk** ATAC-seq — single-cell ATAC uses the
`scatac-*` skills, and this is not a ChIP-seq / CUT&RUN path.

## The Full 6-Step Chain

Bulk ATAC-seq in OmicsClaw is a strict linear chain — each step consumes the
previous step's `result.json`:

1. `bulkatac-preprocessing` — sample-sheet parsing, FastQC, adapter trimming
2. `bulkatac-mapping` — Bowtie2/BWA alignment + ENCODE post-alignment QC
3. `bulkatac-peak-calling` — MACS2 peaks + naive-overlap consensus + counts
4. `bulkatac-DA` — pyDESeq2 differential accessibility for one contrast
5. `bulkatac-motif-enrichment` — HOMER TF motif enrichment + de novo discovery
6. `bulkatac-footprinting` — TOBIAS Tn5-bias correction + TF footprinting

Steps 5 and 6 are **parallel downstream branches**, not sequential: both
answer TF-level questions but differently — enrichment surfaces *which motifs
accumulate* in peak sets, footprinting confirms *which TFs are actively bound*.
Run both for a full TF interpretation.

## How The Runner Chains Steps

The OmicsClaw runner requires either `--input` or `--demo` on every `oc run`
invocation:

- **Only `bulkatac-preprocessing` has a `--demo` flag.** It fetches GSE66386
  (*S. cerevisiae* osmotic-stress T0 vs T15, paired-end, sacCer3) and runs
  end-to-end. Every other step has no demo path.
- Every step after preprocessing chains with
  `--input <prev-step>/result.json` — the runner reads the upstream envelope to
  reconstruct sample sheets, BAM paths, consensus peaks, and DA results.
- Internally `--input` is an alias of `--prev-result`, and `--output` is an
  alias of `--wd`. If you keep all steps under one project directory and pass
  only `--output`, each skill can sibling-detect the previous step's
  `result.json` next to it — but passing `--input` explicitly is clearer.

So to smoke-test the whole chain, start with `--demo` on preprocessing, then
feed each `result.json` forward.

## Start Here: What Does The User Actually Have?

### Case 1: The user has raw bulk ATAC-seq FASTQ

This is the most common beginner starting point.

Recommended route:

1. write a sample sheet — TSV/CSV with `sample, condition, replicate, R1 [, R2]`
2. run `bulkatac-preprocessing` to trim adapters
3. run `bulkatac-mapping` on the preprocessing `result.json`
4. run `bulkatac-peak-calling` on the mapping `result.json`
5. continue to DA / motif / footprinting as the question requires

### Case 2: The user already has trimmed FASTQ

Do **not** ask them to re-trim. Start at `bulkatac-mapping` — but it still
needs a Step-1 `result.json` to reconstruct the sample sheet, so either run
`bulkatac-preprocessing` (it will pass clean reads through quickly) or hand
the runner a Step-1-shaped envelope.

### Case 3: The user already has aligned, deduplicated BAMs

Start at `bulkatac-peak-calling`, but it likewise chains off
`mapping/result.json`. The cleanest path for provenance is still to run
`bulkatac-mapping` so the ENCODE filter + QC are recorded.

### Case 4: The user just wants to try it

Run `bulkatac-preprocessing --demo`, then chain the rest with no special data.

## A Beginner-Friendly Command Sequence

Keep every step under one project directory so chaining is obvious.

### Demo route (no data required)

```bash
oc run bulkatac-preprocessing --demo --output atac_run/preprocessing
oc run bulkatac-mapping        --input atac_run/preprocessing/result.json --output atac_run/mapping
oc run bulkatac-peak-calling   --input atac_run/mapping/result.json       --output atac_run/peak_calling
oc run bulkatac-DA             --input atac_run/peak_calling/result.json  --output atac_run/DA
oc run bulkatac-motif-enrichment --input atac_run/DA/result.json          --output atac_run/motif_enrichment
oc run bulkatac-footprinting   --input atac_run/peak_calling/result.json  --output atac_run/footprinting
```

### Real-data route

```bash
oc run bulkatac-preprocessing --input samplesheet.tsv --genome hg38 --output atac_run/preprocessing
oc run bulkatac-mapping       --input atac_run/preprocessing/result.json --genome hg38 --output atac_run/mapping
oc run bulkatac-peak-calling  --input atac_run/mapping/result.json       --output atac_run/peak_calling
oc run bulkatac-DA            --input atac_run/peak_calling/result.json   --treat T15 --control T0 --output atac_run/DA
oc run bulkatac-motif-enrichment --input atac_run/DA/result.json          --output atac_run/motif_enrichment
oc run bulkatac-footprinting  --input atac_run/peak_calling/result.json   --output atac_run/footprinting
```

Note the two downstream branches both consume Step-3 lineage:
`bulkatac-motif-enrichment` chains off the **DA** `result.json` (it walks back
to peak-calling internally for the consensus BED), while
`bulkatac-footprinting` chains directly off the **peak-calling** `result.json`.

## What Each Step Produces

- **preprocessing** → `report.md`, `result.json`, `fastq_trimmed/` (trimmed
  FASTQs + `trimmed_summary.csv`)
- **mapping** → `mapping_summary.csv`, `bam/<sample>.dedup.bam`,
  `bigwig/<sample>.rpgc.bw`, `qc_after_mapping/` (TSS enrichment +
  fragment-length QC)
- **peak-calling** → `peaks/<sample>/`, `consensus/qvalue<q>/`
  (`consensus_peaks.bed`, `consensus_peaks.saf`, `peak_counts.txt`),
  `annotation/`, `qc_after_peak_calling/` (FRiP, PCA, optional IDR)
- **DA** → `DA/<contrast>/<param_tag>/` (`da_results_<contrast>.tsv`,
  up/down/all BED tracks for IGV), `plots/<contrast>/` volcano
- **motif-enrichment** → `{all_peaks,da_up,da_down}/` HOMER outputs,
  `top_motif_summary.tsv`, top-motif plots
- **footprinting** → `atacorrect/`, `footprints/`, `bindetect/`
  (`bindetect_results.txt`), `top_tf_ranking.tsv`, aggregate footprint plots

## The Main User Mistakes To Prevent

### Mistake 1: Jumping straight from FASTQ to peak calling

Correct route: preprocessing → mapping → peak-calling. Each step needs the
prior `result.json`.

### Mistake 2: Expecting `--demo` on every step

Only `bulkatac-preprocessing` has `--demo`. Every other step requires
`--input <prev-step>/result.json`.

### Mistake 3: Tn5-shifting BAMs manually

`bulkatac-mapping` deliberately leaves BAMs unshifted — MACS2 (`--shift`/
`--extsize` for SE) and TOBIAS `ATACorrect` apply the +4/-5 offset themselves.
Pre-shifting double-corrects.

### Mistake 4: Running DA on a single-condition cohort

`bulkatac-DA` hard-fails with fewer than two conditions. Add a comparator
condition to the sample sheet, or skip DA / motif-enrichment entirely.

### Mistake 5: Pointing motif-enrichment at the wrong result.json

`bulkatac-motif-enrichment` hard-checks that its `--input` is a **DA**
`result.json`. `bulkatac-footprinting` instead chains off the **peak-calling**
`result.json`. Do not swap them.

## Simple Decision Rule For Routing

If the user only says:

- “bulk ATAC FASTQ” / “raw ATAC reads” → start at `bulkatac-preprocessing`

If they say:

- “I have ATAC BAMs” → `bulkatac-peak-calling` (chain off a mapping result)

If they say:

- “which peaks change between conditions?” → `bulkatac-DA`

If they say:

- “which TF motifs are enriched?” → `bulkatac-motif-enrichment`

If they say:

- “which TFs are actually bound / footprints” → `bulkatac-footprinting`

If they say:

- “single-cell ATAC” / “scATAC” → this is outside the bulk chain; route to
  the `scatac-*` single-cell skills instead.
