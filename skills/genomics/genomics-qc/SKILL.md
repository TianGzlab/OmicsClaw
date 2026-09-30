---
name: genomics-qc
description: Load when running pre-alignment FASTQ quality control — Phred quality scores, Q20/Q30 rates,
  GC / N content, read-length distribution, adapter-contamination detection. Skip when working with already-aligned
  BAMs (use genomics-alignment); peak / variant files are the input (use the relevant downstream skill).
trigger: sequencing QC, FastQC, read quality, adapter trimming, fastp
tags:
- genomics
- qc
- fastq
- phred
- adapter
- fastqc
---

# genomics-qc

## When to use

The user has a raw FASTQ file (`.fastq` or `.fastq.gz`) and wants
standard pre-alignment QC: total reads, mean Phred quality, Q20 /
Q30 rates, GC / N content, mean read length, adapter contamination
percentage, per-base quality profile. This skill mirrors a subset
of FastQC / fastp metrics in pure Python.

It does NOT trim adapters or filter reads — it only measures.
For BAM-level alignment QC use `genomics-alignment`.

## Inputs & Outputs

**Inputs**

- File types: `.fastq`, `.fq`

**Outputs**

- `tables/per_base_quality.csv`
- `tables/qc_metrics.csv`
- `tables/read_length_distribution.csv`
- `report.md`
- `result.json`

## Flow

1. Load FASTQ (`--input <reads.fastq[.gz]>`) or synthesise demo reads at `output_dir/demo_reads.fastq` (`genomics_qc.py`).
2. Stream up to `--max-reads` records (default 500_000); aggregate Phred / GC / N / length stats.
3. Detect adapter contamination via fixed adapter motif scan.
4. Write `tables/qc_metrics.csv` (`genomics_qc.py`) + `tables/per_base_quality.csv` + `report.md` + `result.json`.

## Gotchas

- **`--max-reads` defaults to 500 000** (`genomics_qc.py`). For very deep libraries this is a hard cap — increase it for full-flowcell QC. Reads beyond the cap are silently ignored.
- **Empty FASTQ raises `ValueError("No reads found in {fastq_path}")`** at `genomics_qc.py`. A truncated upload manifests as exit-1; check the file size first.
- **`--input` REQUIRED unless `--demo`.** `genomics_qc.py` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError`.
- **No trimming or filtering happens here.** This is a pure measurement skill — to actually trim adapters or quality-filter, run fastp / Trimmomatic outside OmicsClaw before re-running this for post-trim QC.
- **Phred encoding is assumed Phred+33.** Old Solexa / Illumina 1.3+ Phred+64 files would mis-score; the script does NOT auto-detect encoding.
- **Demo writes a synthetic FASTQ into `output_dir`.** `genomics_qc.py` writes `demo_reads.fastq` directly into the user-supplied output directory — re-running `--demo` overwrites silently.

## Key CLI

```bash
# Demo (synthetic FASTQ)
python skills/genomics/genomics-qc/genomics_qc.py --demo --output /tmp/qc_demo

# Real FASTQ
python skills/genomics/genomics-qc/genomics_qc.py \
  --input reads.fastq.gz --output results/ \
  --max-reads 1000000
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — Phred / Q20 / Q30 definitions, adapter motifs
- `references/output_contract.md` — `tables/qc_metrics.csv` + per-base schema
- Adjacent skills: `genomics-alignment` (downstream — alignment QC after mapping), `bulkrna-read-qc` (parallel — RNA-seq-flavoured FASTQ QC), `sc-qc` (parallel — single-cell QC after mapping)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
