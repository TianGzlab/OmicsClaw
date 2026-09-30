---
name: genomics-alignment
description: Load when computing alignment QC metrics (mapping rate, MAPQ distribution, insert size, duplicate
  rate, proper-pair rate) from a text SAM file produced by any short-/long-read aligner (BWA / Bowtie2
  / Minimap2); convert a BAM with samtools view -h first. Skip when running the alignment step itself;
  only FASTQ-level QC is needed (use genomics-qc).
trigger: alignment, BWA, Bowtie2, Minimap2, map reads
tags:
- genomics
- alignment
- bam
- sam
- bwa
- bowtie2
- minimap2
---

# genomics-alignment

## When to use

The user has a text SAM file from any aligner (BWA-MEM, Bowtie2,
Minimap2, etc.) and wants standard alignment QC: mapped-read count,
mapping rate, MAPQ distribution, proper-pair rate, duplicate rate.
This skill mirrors `samtools flagstat` + per-MAPQ binning entirely
in pure Python (no `samtools` install needed). It does **not**
perform alignment — feed in an already-aligned `.sam` (convert a BAM first).

For pre-alignment FASTQ QC use `genomics-qc`. For variant calling
on the aligned reads use `genomics-variant-calling`.

## Inputs & Outputs

**Inputs**

- File types: `.sam`

**Outputs**

- `tables/alignment_stats.csv`
- `report.md`
- `result.json`

## Flow

1. Open the SAM in text mode (`genomics_alignment.py` → `open(sam_path, "r")`) or synthesise a demo SAM at `output_dir/demo_alignment.sam`.
2. Stream the records, count flags (mapped / proper-pair / dup / supplementary / secondary).
3. Bin MAPQ; compute insert-size mean / median (paired only).
4. Write `tables/alignment_stats.csv` (`genomics_alignment.py`) + `report.md` + standardised `result.json` envelope.

## Gotchas

- **`--input` REQUIRED unless `--demo`.** `genomics_alignment.py` raises `ValueError("--input required when not using --demo")`; non-existent paths raise `FileNotFoundError`. There is no `parser.error` shortcut — `ValueError` propagates as a Python traceback, exit code 1.
- **Text SAM only — binary BAM raises `UnicodeDecodeError`.** `genomics_alignment.py` calls `open(sam_path, "r")` (text mode); there is no `pysam` import or BAM/CRAM decoder anywhere in the script. Convert BAMs upstream with `samtools view -h aligned.bam > aligned.sam`. The "no pysam dependency" comment documents this intent.
- **No subprocess to `samtools`.** Parsing is pure-Python — the script never shells out. CRAM input is **not** supported either.
- **No alignment is performed.** This skill only summarises an already-aligned file. To produce the SAM/BAM, run BWA / Bowtie2 / Minimap2 yourself first; this skill consumes their output.
- **Demo writes a synthetic SAM into `output_dir`.** `genomics_alignment.py` writes `demo_alignment.sam` directly into the user-specified output directory. If you re-run `--demo` with different parameters in the same dir, the file is overwritten silently.
- **Insert-size statistics are paired-only.** Single-end alignments still emit a row — but the insert-size columns will be 0 / NaN. Inspect `summary['proper_pair_rate']` to confirm the input is paired before drawing conclusions.

## Key CLI

```bash
# Demo (synthetic 1K-read SAM)
python skills/genomics/genomics-alignment/genomics_alignment.py --demo --output /tmp/align_demo

# Real data (convert BAM to text SAM first)
samtools view -h sample.aligned.bam > sample.aligned.sam
python skills/genomics/genomics-alignment/genomics_alignment.py \
  --input sample.aligned.sam --output results/
```

## See also

- `references/parameters.md` — every CLI flag
- `references/methodology.md` — flagstat field semantics, MAPQ interpretation
- `references/output_contract.md` — `tables/alignment_stats.csv` schema
- Adjacent skills: `genomics-qc` (upstream — FASTQ-level QC before alignment), `genomics-variant-calling` (downstream — variant discovery on the BAM), `genomics-cnv-calling` (downstream — depth-of-coverage CNV from the BAM)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`numpy`, `pandas`
