---
name: bulkrna-read-qc
description: Load when checking raw FASTQ quality (Phred / GC / adapter / Q20-Q30) before alignment in bulk RNA-seq. Skip if reads are already aligned (use bulkrna-read-alignment) or counted (use bulkrna-qc), or for single-cell FASTQ (use sc-fastq-qc).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- FASTQ
- QC
- Phred
- GC-content
- adapter
- read-quality
requires:
- numpy
- pandas
- matplotlib
---

# bulkrna-read-qc

## When to use

Run as the first step on raw bulk RNA-seq FASTQ files (single or paired-end)
before aligning.  Reports per-base Phred quality, GC content, adapter
contamination signals, read length distribution, and Q20/Q30 fractions —
the metrics needed to decide whether trimming is worth the trouble.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| FASTQ file | `.fastq` or `.fastq.gz` | yes (or `--demo`) |

| Output | Path | Notes |
|---|---|---|
| QC report | `report.md` + `result.json` | always |
| Per-base quality | `figures/per_base_quality.png` | Phred profile across read positions |
| GC distribution | `figures/gc_content.png` | per-read GC% histogram |
| Length distribution | `figures/read_length_dist.png` | for variable-length / trimmed input |

## Flow

1. Open the FASTQ (auto-decompresses `.gz` per `bulkrna_read_qc.py:70`).
2. Sample reads, decode Phred quality from header line 4 of each record.
3. Compute per-base quality, GC content, length distribution, adapter motif counts.
4. Render figures and write `report.md` + `result.json`.

## Gotchas

- **This is a pure-Python reimplementation of FastQC core metrics, not FastQC itself.**  Coverage of the more obscure FastQC modules (overrepresented sequences, k-mer enrichment, per-tile quality) is intentionally omitted to keep the skill dependency-free.  For full FastQC parity, run FastQC directly and feed the report into MultiQC.
- **Phred encoding is assumed to be Phred+33 (Sanger / Illumina 1.8+).**  Older Illumina 1.3–1.7 platforms used Phred+64 — the per-base quality values will look ~31 points too high if such input is fed in unchanged.  Confirm the source platform before trusting Q20/Q30 numbers.
- **`.gz` detection is filename-suffix only** (`bulkrna_read_qc.py:70` checks `.endswith(".gz")`).  A gzipped file misnamed without `.gz` will be opened as text and silently produce garbage; rename or symlink before running.

## Key CLI

```bash
python omicsclaw.py run bulkrna-read-qc --demo
python omicsclaw.py run bulkrna-read-qc --input reads.fastq.gz --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — Phred decoding, sampling strategy, adapter detection
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-read-alignment` (downstream after alignment), `bulkrna-qc` (downstream after counting), `sc-fastq-qc` (single-cell sibling), `genomics-qc` (genomic-DNA sibling)
