---
name: bulkrna-read-qc
description: Load when checking raw FASTQ quality (Phred / GC / adapter / Q20-Q30) before alignment in
  bulk RNA-seq. Skip when reads are already aligned (use bulkrna-read-alignment); counted (use bulkrna-qc);
  single-cell FASTQ (use sc-fastq-qc).
trigger: FASTQ QC, read quality, Phred, FastQC, adapter, GC content, Q20, Q30
tags:
- bulkrna
- FASTQ
- QC
- Phred
- GC-content
- adapter
- read-quality
---

# bulkrna-read-qc

## When to use

Run as the first step on raw bulk RNA-seq FASTQ files (single or paired-end)
before aligning.  Reports per-base Phred quality, GC content, adapter
contamination signals, read length distribution, and Q20/Q30 fractions —
the metrics needed to decide whether trimming is worth the trouble.

## Inputs & Outputs

**Inputs**

- File types: `.fastq`, `.fq`

**Outputs**

- `tables/qc_summary.csv`
- `figures/gc_content.png`
- `figures/per_base_quality.png`
- `figures/quality_score_distribution.png`
- `figures/read_length_distribution.png`
- `report.md`
- `result.json`

## Flow

1. Open the FASTQ (auto-decompresses `.gz` per `bulkrna_read_qc.py`).
2. Sample reads, decode Phred quality from header line 4 of each record.
3. Compute per-base quality, GC content, length distribution, adapter motif counts.
4. Render figures and write `report.md` + `result.json`.

## Gotchas

- **This is a pure-Python reimplementation of FastQC core metrics, not FastQC itself.**  Coverage of the more obscure FastQC modules (overrepresented sequences, k-mer enrichment, per-tile quality) is intentionally omitted to keep the skill dependency-free.  For full FastQC parity, run FastQC directly and feed the report into MultiQC.
- **Phred encoding is assumed to be Phred+33 (Sanger / Illumina 1.8+).**  Older Illumina 1.3–1.7 platforms used Phred+64 — the per-base quality values will look ~31 points too high if such input is fed in unchanged.  Confirm the source platform before trusting Q20/Q30 numbers.
- **`.gz` detection is filename-suffix only** (`bulkrna_read_qc.py` checks `.endswith(".gz")`).  A gzipped file misnamed without `.gz` will be opened as text and silently produce garbage; rename or symlink before running.

## Key CLI

```bash
python skills/bulkrna/bulkrna-read-qc/bulkrna_read_qc.py --demo --output /tmp/bulkrna-read-qc_demo
python skills/bulkrna/bulkrna-read-qc/bulkrna_read_qc.py --input reads.fastq.gz --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — Phred decoding, sampling strategy, adapter detection
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-read-alignment` (downstream after alignment), `bulkrna-qc` (downstream after counting), `sc-fastq-qc` (single-cell sibling), `genomics-qc` (genomic-DNA sibling)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`matplotlib`, `numpy`, `pandas`
