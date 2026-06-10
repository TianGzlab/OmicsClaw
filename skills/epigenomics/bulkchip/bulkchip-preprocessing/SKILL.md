---
name: bulkchip-preprocessing
description: Load when preprocessing bulk ChIP-seq FASTQs — sample-sheet parsing with ChIP/input control pairing, FastQC quality checks, and adapter trimming with fastp or Trim Galore. Skip when reads are already trimmed (go to bulkchip-mapping), for bulk ATAC-seq (use bulkatac-preprocessing), or single-cell assays.
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- chip-seq
- transcription-factor
- histone-mark
- preprocessing
- qc
- fastp
- trim_galore
- fastqc
requires:
- pandas
- numpy
---

> **Status: implemented.** This is the first bulkchip skill with full tool
> execution (FastQC + fastp/Trim Galore) and a working `--demo`. The other
> bulkchip skills (mapping onward) remain methodology scaffolds for now.

## When to use

The user has raw bulk ChIP-seq FASTQs (single-end or paired-end) for one or more ChIP samples **and their matched input/IgG controls**, and wants ENCODE-style preprocessing before alignment: sample-sheet validation (including ChIP↔control pairing), optional FastQC reports, and Illumina adapter trimming. Use `--demo` to fetch the nf-core SPT5 ChIP-seq test set (*S. cerevisiae*, T0 vs T15 ×2 reps + 2 inputs, PE, sacCer3) and run end-to-end. Skip for bulk ATAC (`bulkatac-preprocessing`), single-cell assays, or when reads are already trimmed — go straight to `bulkchip-mapping`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Sample sheet | TSV/CSV: `sample, condition, replicate, R1 [, R2], control, antibody [, peak_mode]` | Yes (unless `--demo`) |
| Output dir | Existing or new directory (`--output` / `--wd`) | Yes |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Sample table (ChIP + control), layout, trim parameters, summary |
| Result envelope | `<output>/result.json` | `skill`, `version`, `steps_completed`, `sample_sheet` (with `control_map`), per-sample trim stats |
| Trimmed FASTQs | `<output>/fastq_trimmed/` | One pair (or singleton) per sample |
| Trim summary | `<output>/fastq_trimmed/trimmed_summary.csv` | Per-sample reads in/out, % passing, tool |
| Reproducibility | `<output>/reproducibility/` | Re-run command + pinned versions |
| Output README | `<output>/README.md` | Orientation note |

All artifacts land directly under `--output` (OmicsClaw per-skill layout — no nested `preprocessing/` subdir).

## Flow

1. Parse args; require `--input` or `--demo`.
2. Parse + validate the sample sheet via `_lib.preprocessing.get_data`; build the `control_map` and fail fast if any ChIP sample references a missing control.
3. Step 1a — FastQC per FASTQ (optional, `--no-fastqc`).
4. Step 1b — adapter trim per sample via `run_all_preprocessing` (fastp / Trim Galore; Illumina universal adapter `AGATCGGAAGAGC`).
5. Write `report.md`, `result.json` (carrying `sample_sheet` + `control_map` forward), `reproducibility/`, and `README.md`.

## Gotchas

- **Controls are first-class samples.** Input/IgG samples appear in the sheet with `is_control=true` (or a blank `antibody`) and are trimmed exactly like ChIP samples — `bulkchip-peak-calling` needs the trimmed, aligned control BAM for `MACS2 -c`.
- **`peak_mode` is metadata here.** Carried in the sheet (`narrow` for TF/sharp, `broad` for broad histone marks) and stashed in `result.json`; it is consumed by `bulkchip-peak-calling`, not used during trimming.
- **`--genome` is metadata only.** Preprocessing never uses it; it is stored in `result.json["params"]["genome"]` for `bulkchip-mapping`.
- **Both `--wd` and `--output` mean the same thing** (`--output` is an alias); the OmicsClaw runner injects `--output`.
- **Adapter default is Illumina universal (`AGATCGGAAGAGC`)**, not the ATAC Nextera adapter — ChIP libraries are typically TruSeq.

## Key CLI

Demo run (downloads the SPT5 ChIP-seq test set, subsamples to 50k reads/FASTQ, runs Step 1):

```bash
python skills/epigenomics/bulkchip/bulkchip-preprocessing/bulkchip-preprocessing.py \
    --demo --wd ./chip_run/preprocessing
```

Real run with paired-end samples + matched inputs:

```bash
python skills/epigenomics/bulkchip/bulkchip-preprocessing/bulkchip-preprocessing.py \
    --input samplesheet.tsv --wd ./chip_run/preprocessing --genome hg38 --threads 32
```

Force Trim Galore + stricter trimming, skip FastQC:

```bash
python skills/epigenomics/bulkchip/bulkchip-preprocessing/bulkchip-preprocessing.py \
    --input samplesheet.tsv --wd ./chip_run \
    --tool trim_galore --quality 25 --min-length 30 --no-fastqc
```

## See also

- `references/parameters.md` — every CLI flag with type + default.
- `references/methodology.md` — fastp vs Trim Galore criteria, control-pairing rules, ENCODE ChIP read-length standards.
- `references/output_contract.md` — output tree + `trimmed_summary.csv` / `result.json` schemas.
- Adjacent skills:
  - Downstream — `bulkchip-mapping` (Step 2: alignment + ENCODE/ChIP QC).
  - Parallel — `bulkatac-preprocessing` (bulk ATAC; Nextera adapters, no control pairing).
