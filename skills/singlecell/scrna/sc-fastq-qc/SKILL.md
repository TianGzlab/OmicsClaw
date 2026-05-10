---
name: sc-fastq-qc
description: Load when checking raw single-cell FASTQ read quality (Phred / GC / adapter / length) before counting. Skip when reads are already counted (use sc-qc) or for bulk FASTQ (use bulkrna-read-qc).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- fastq
- qc
- read-quality
requires:
- pandas
- matplotlib
---

# sc-fastq-qc

## When to use

The user has raw scRNA-seq FASTQ files (one or more, or a directory of
samples) and wants per-file / per-sample / per-base quality summaries
before running `sc-count` or `cellranger`.  Uses FastQC + MultiQC when
those tools are installed; falls back to a stable Python-only summary
otherwise so the skill always returns something useful.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Raw scRNA reads | `.fastq` / `.fastq.gz` (single file or directory) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Per-file table | `tables/fastq_per_file_summary.csv` | one row per FASTQ |
| Per-sample table | `tables/fastq_per_sample_summary.csv` | aggregated by sample |
| Per-base table | `tables/fastq_per_base_quality.csv` | quality vs read position |
| Quality figures | `figures/per_base_quality.png`, `figures/fastq_file_quality.png` | always rendered |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Discover FASTQ files from `--input` (single file or directory).
2. If `fastqc` is on `$PATH`, run it; if `multiqc` is on `$PATH`, run that too.
3. In parallel run a Python-only fallback that samples up to `--max-reads` per FASTQ for Phred / GC / adapter / length.
4. Merge tool output + fallback into per-file / per-sample / per-base tables.
5. Render quality + adapter / GC diagnostic figures.
6. Emit `report.md` + `result.json`.

## Gotchas

- **`--max-reads 20000` (default) caps the Python-fallback path only.** When FastQC is available the full FASTQ is processed; when not, only the first 20K reads per file are sampled.  Sampling depth is recorded per file in `tables/fastq_per_file_summary.csv`; bump `--max-reads` if a FASTQ has high variance across the file.
- **`--r-enhanced` is accepted but produces no R plots.** This skill emits Python figures only.  Pass freely, expect no R Enhanced output.
- **Per-figure `status: "rendered"` is local, not global.** The `result.json` carries a `status` field per figure (e.g. `figures.per_base_quality.status == "rendered"`); the absence of a *figure* entry means it was not rendered (e.g. paired-read panel only fires when `--read2` is set).  Don't infer skill-wide success from any single status.

## Key CLI

```bash
# Demo (built-in synthetic FASTQ)
python omicsclaw.py run sc-fastq-qc --demo --output /tmp/sc_fastq_qc_demo

# Single-file with paired-end
python omicsclaw.py run sc-fastq-qc \
  --input sample_R1.fastq.gz --read2 sample_R2.fastq.gz --output results/

# Directory of samples, deeper sampling for the Python fallback
python omicsclaw.py run sc-fastq-qc \
  --input fastq_dir/ --output results/ --max-reads 100000 --threads 8
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — FastQC integration + Python fallback rationale
- `references/output_contract.md` — table column schemas + figure roles
- Adjacent skills: `sc-count` (next step — FASTQ → AnnData), `bulkrna-read-qc` (bulk RNA-seq variant), `sc-qc` (downstream count-matrix QC)
