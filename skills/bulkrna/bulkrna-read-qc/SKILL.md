---
name: bulkrna-read-qc
description: >-
  FASTQ quality assessment for bulk RNA-seq — Phred scores, GC content, adapter detection,
  read length distribution, Q20/Q30 rates.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, FASTQ, QC, Phred, GC-content, adapter, read-quality]
requires: [numpy, pandas, matplotlib]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🔍"
    trigger_keywords: [FASTQ QC, read quality, Phred, FastQC, adapter, GC content,
      Q20, Q30]
    allowed_extra_flags: []
    legacy_aliases: [bulk-fastqc]
    saves_h5ad: false
    script: bulkrna_read_qc.py
    param_hints: {}
    requires_preprocessed: false
---

# Bulk RNA-seq FASTQ Quality Assessment

Quality assessment of raw FASTQ files for bulk RNA-seq experiments. Computes per-base quality scores, GC content, adapter contamination, read length distribution, and Q20/Q30 rates — a Python implementation of core FastQC metrics.

## Core Capabilities

- Per-base Phred quality score profiles
- Q20/Q30 pass rates per sample
- GC content distribution and N content detection
- Adapter sequence contamination check (Illumina TruSeq, Nextera, etc.)
- Read length distribution
- Sequence duplication estimation

## Why This Exists

- **Without it**: Users must install FastQC (Java), run it per file, then use MultiQC to aggregate — a multi-tool, multi-step workflow.
- **With it**: A single Python command performs core FASTQ QC, generates publication-ready figures, and integrates into the OmicsClaw reporting pipeline.
- **Why OmicsClaw**: Provides FASTQ-level QC prior to alignment, completing the full bulk RNA-seq pipeline (FASTQ QC → alignment → count matrix QC → ...).

## Input Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| FASTQ | `.fastq`, `.fq`, `.fastq.gz` | Raw sequencing reads |

## CLI Reference

```bash
python omicsclaw.py run bulkrna-read-qc --demo
python omicsclaw.py run bulkrna-read-qc --input reads.fastq.gz --output results/
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── per_base_quality.png
│   ├── gc_content.png
│   ├── read_length_distribution.png
│   └── quality_score_distribution.png
├── tables/
│   └── qc_summary.csv
└── reproducibility/
    └── commands.sh
```

## Related Skills

- `bulkrna-read-alignment` — Downstream: alignment after QC
- `bulkrna-qc` — Downstream: count matrix QC after quantification
