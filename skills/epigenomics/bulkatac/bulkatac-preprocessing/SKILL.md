---
name: bulkatac-preprocessing
description: Load when preprocessing bulk ATAC-seq FASTQs — sample-sheet parsing, FastQC quality checks, and adapter trimming with fastp or Trim Galore. Skip when reads are already trimmed (go to bulkatac-mapping), when the data is single-cell ATAC (use scatac-preprocessing), or for ChIP-seq / CUT&RUN.
version: 0.1.0
author: OmicsClaw
license: MIT
tags:
- epigenomics
- atac-seq
- chromatin-accessibility
- preprocessing
- qc
- fastp
- trim_galore
- fastqc
requires:
- pandas
- numpy
---

## When to use

The user has raw bulk ATAC-seq FASTQs (single-end or paired-end) from one or more samples / conditions / replicates and wants ENCODE-style preprocessing before alignment: sample-sheet validation, optional FastQC reports, and Nextera adapter trimming. Use `--demo` to fetch GSE66386 (*S. cerevisiae* osmotic-stress T0 vs T15, paired-end, sacCer3) and run end-to-end. Skip for scATAC (`scatac-preprocessing`), ChIP-seq, or when reads are already trimmed — go straight to `bulkatac-mapping`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Sample sheet | TSV or CSV with columns `sample, condition, replicate, R1 [, R2]` | Yes (unless `--demo`) |
| Output dir | Existing or new directory (`--output` / `--wd`) | Yes |

| Output | Path | Notes |
|---|---|---|
| Markdown report | `<output>/report.md` | Sample table, layout, trim parameters, summary table |
| Result envelope | `<output>/result.json` | `skill`, `version`, `steps_completed`, `sample_sheet`, per-sample trim stats |
| Trimmed FASTQs | `<output>/fastq_trimmed/` | One pair (or singleton) per sample |
| Trim summary | `<output>/fastq_trimmed/trimmed_summary.csv` | Per-sample reads in/out, % passing, tool |
| Reproducibility | `<output>/reproducibility/{commands.sh,environment.txt}` | Re-run command + pinned versions |
| Output README | `<output>/README.md` | Orientation note (start with `report.md`) |

All artifacts land directly under `--output` (the OmicsClaw per-skill layout — no nested `preprocessing/` subdir). Demo-mode also writes `demo_samplesheet.tsv` and `fastq/` (raw + subsampled downloads) to **`--output`'s parent directory**, beside `--output` rather than inside it — that data is demo *input*, standing in for a fastq/ dir a real user prepares separately, so it is kept out of the skill's own artifact namespace.

## Flow

1. Parse args; require `--input` or `--demo` (`bulkatac-preprocessing.py:281-282`).
2. Resolve `--genome`: force `sacCer3` in `--demo` mode regardless of what the user passed (`bulkatac-preprocessing.py:289-296`).
3. Create the `--output` directory — the skill's own root, no nested subdir (`bulkatac-preprocessing.py:315-316`).
4. Step 1a — load the sample sheet via `_lib.preprocessing.get_data`; in demo mode this downloads GSE66386 FASTQs into `<output>/../fastq/` (beside `--output`) and subsamples to `--demo-n-reads` (`bulkatac-preprocessing.py:338-348`).
5. Step 1b — run FastQC (optional) + adapter trim per sample via `run_all_preprocessing`; pick fastp or Trim Galore based on `--tool` (`bulkatac-preprocessing.py:350-356`).
6. Resolve `--tool auto` to the actual tool used, then write `report.md`, `result.json`, `reproducibility/`, and the output `README.md` (`bulkatac-preprocessing.py:359-371`).

## Gotchas

- **Both `--wd` and `--output` mean the same thing.** `bulkatac-preprocessing.py:221` registers `--output` as an alias of `--wd` (`dest="wd"`); one is required. Internal code references `args.wd`. Direct invocations may use either; the OmicsClaw runner injects `--output` so it just works.
- **Outputs land directly at `--output`, not in a nested subdir.** `bulkatac-preprocessing.py:315-316` treats `--output` as the skill's own directory — `report.md`, `result.json`, `fastq_trimmed/`, `reproducibility/` all sit at its root (the OmicsClaw per-skill layout). For the pipeline, pass a step-specific dir, e.g. `--output <project>/preprocessing`, so `bulkatac-mapping` sibling-detects it at `<project>/preprocessing/result.json`.
- **`--genome` is metadata only — silently coerced to `sacCer3` in `--demo`.** `bulkatac-preprocessing.py:289-296` overwrites any passed value with a warning. Preprocessing itself never uses the genome string; it's stashed in `result.json["params"]["genome"]` so `bulkatac-mapping` can pick it up.
- **`--tool auto` is resolved post-trim, never logged as `auto`.** `bulkatac-preprocessing.py:359` overwrites `params["tool"]` with the first sample's actual tool (`fastp` or `trim_galore`) before writing `result.json` / `commands.sh`. Inspect `result.json["params"]["tool"]` to confirm which trimmer ran.
- **Demo mode hits SRA — first run needs network + `sra-tools`.** `bulkatac-preprocessing.py:338-348` calls into `_lib.preprocessing.get_data` which `fastq-dump`s ~12 SRR accessions from GSE66386 into `<output>/../fastq/` (beside `--output`, not inside it — see the layout note above). ~1 GB raw before `--demo-n-reads` subsampling. Subsequent demo runs reuse the downloads.
- **No `tables/` directory by convention.** The per-sample trim stats live at `fastq_trimmed/trimmed_summary.csv` — see `bulkatac-preprocessing.py:349`. Tooling that scans the standard `tables/*.csv` output namespace for results will miss this file; consume it via `result.json["preprocessing"]` instead.
- **No `mark_result_status` call at exit.** `bulkatac-preprocessing.py:373` ends with a `print(...)` and returns normally. The OmicsClaw runner falls back to the process exit code to decide success, so partial failures recorded in `result.json["steps_completed"]` will not block the runner if the script otherwise exits 0.

## Key CLI

Demo run (downloads GSE66386, subsamples to 50k reads/FASTQ, runs Step 1):

```bash
python skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py \
    --demo --wd /tmp/bulkatac-preprocessing-demo
```

Real run with paired-end human samples:

```bash
python skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py \
    --input samplesheet.tsv --wd ./atac_run --genome hg38 --threads 32
```

Force Trim Galore + stricter trimming (Q25, ≥30 bp post-trim), skip FastQC:

```bash
python skills/epigenomics/bulkatac/bulkatac-preprocessing/bulkatac-preprocessing.py \
    --input samplesheet.tsv --wd ./atac_run \
    --tool trim_galore --quality 25 --min-length 30 --no-fastqc
```

## See also

- `references/parameters.md` — every CLI flag with type + default (auto-generated from `parameters.yaml`).
- `references/methodology.md` — fastp vs Trim Galore decision criteria, Nextera adapter rationale, ENCODE QC thresholds, demo dataset details.
- `references/output_contract.md` — full output tree with file schemas (`trimmed_summary.csv` columns, `result.json` keys).
- Adjacent skills:
  - Downstream — `bulkatac-mapping` (Step 2a: Bowtie2/BWA alignment + ENCODE BAM filtering); `bulkatac-peak-calling` (Step 3a: MACS2 + consensus peaks).
  - Parallel — `scatac-preprocessing` (single-cell ATAC; different QC + chromatin assumptions).
