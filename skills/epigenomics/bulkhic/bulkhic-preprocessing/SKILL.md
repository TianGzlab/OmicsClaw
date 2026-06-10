---
name: bulkhic-preprocessing
description: "Load when starting a bulk Hi-C analysis from FASTQ: sample-sheet loading plus FastQC. Reads mapped RAW by default (bwa-mem2 -SP5M and pairtools handle ligation junctions); fastp trimming is opt-in via --trim. Samples grouped by condition and replicate. Skip for bulk ATAC/ChIP (use bulkatac-/bulkchip-preprocessing); next step is bulkhic-mapping."
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
  - epigenomics
  - hi-c
  - 3c
  - chromosome-conformation
  - preprocessing
  - fastqc
  - fastp
requires:
  - pandas
---

> **Status: implemented** (fastp + FastQC). First step of the bulk Hi-C suite.

## When to use

The user has paired-end bulk Hi-C FASTQs (one or more libraries, grouped by
biological condition + replicate) and wants raw-read QC + light adapter/quality
trimming before mapping. Hi-C is always paired-end and has **no input/IgG
control and no antibody** (unlike ChIP) — the sheet is just
`sample, condition, replicate, r1, r2 [, genome]`. Skip for bulk ATAC/ChIP
(`bulkatac-preprocessing` / `bulkchip-preprocessing`).

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Sample sheet | TSV/CSV: `sample, condition, replicate, r1, r2` (+ optional `genome, adapter_r1, adapter_r2`) | Yes (unless `--demo`) |
| Demo data | `--demo` streams a small D. melanogaster S2R+ Hi-C test set (dm6; Wang et al. 2018, GSE101317; 2 conditions × 2 reps) | Optional |

| Output | Path | Notes |
|---|---|---|
| Report | `<output>/report.md` | per-sample trimming table |
| Result envelope | `<output>/result.json` | `sample_sheet` + `preprocessing[]` (trimmed FASTQ paths) for bulkhic-mapping |
| Trimmed FASTQs | `<output>/fastq_trimmed/` | per-sample trimmed reads + `trimmed_summary.csv` |
| Reproducibility | `<output>/reproducibility/` | `commands.sh`, `requirements.txt` |

## Flow

1. Load the sample sheet (or download the `--demo` Hi-C test set + write `demo_samplesheet.tsv`).
2. FastQC on raw reads; fastp adapter + quality trim (light — the two mates are mapped *separately* downstream, so no PE overlap correction here).
3. Write `report.md`, `result.json` (with `sample_sheet` + `preprocessing[]`), `reproducibility/`, `README.md`.

## Gotchas

- **No control / antibody columns.** Hi-C has no input; those ChIP-only columns are not part of the sheet.
- **Paired-end only.** Hi-C requires R1+R2; a single-end sheet is warned about.
- **Light trimming by design.** Hi-C reads are mapped end-by-end (`bwa mem -SP5M`); aggressive PE-merge trimming would corrupt ligation junctions.

## Key CLI

```bash
# demo (D. melanogaster S2R+ Hi-C, dm6 — GSE101317; streams 3M read pairs/file)
python skills/epigenomics/bulkhic/bulkhic-preprocessing/bulkhic-preprocessing.py \
    --demo --output ./hic_run/preprocessing

# real data
python .../bulkhic-preprocessing.py --input samples.tsv --output ./hic_run/preprocessing
```

## See also

- `references/methodology.md` — sheet schema, trimming rationale.
- Downstream — `bulkhic-mapping` (reads → `.pairs`), then `bulkhic-matrix`.
- Parallel — `bulkatac-preprocessing`, `bulkchip-preprocessing`.
