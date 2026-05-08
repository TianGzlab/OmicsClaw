---
name: bulkrna-read-alignment
description: >-
  RNA-seq read alignment and quantification statistics — STAR/HISAT2/Salmon log parsing,
  mapping rate, unique/multi-mapped reads, library strandedness, gene body coverage.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, alignment, STAR, HISAT2, Salmon, mapping-rate, strandedness]
requires: [numpy, pandas, matplotlib]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🧬"
    trigger_keywords: [RNA-seq alignment, STAR, HISAT2, Salmon, mapping rate, read
        alignment, alignment QC]
    allowed_extra_flags:
    - "--method"
    - "--species"
    legacy_aliases: [bulk-align-reads]
    saves_h5ad: false
    script: bulkrna_read_alignment.py
    param_hints: {}
    requires_preprocessed: false
---

# Bulk RNA-seq Read Alignment & Quantification Statistics

Parses alignment logs from STAR, HISAT2, or Salmon to produce comprehensive mapping quality metrics. When run in demo mode, generates synthetic alignment statistics to demonstrate the full reporting pipeline.

## Core Capabilities

- Parse STAR `Log.final.out`, HISAT2 summary, or Salmon `meta_info.json`
- Compute total reads, uniquely mapped, multi-mapped, unmapped rates
- Alignment quality assessment (unmapped > 20% = warning, > 40% = fail)
- Strandedness estimation from alignment stats
- Library complexity estimation
- Gene body coverage distribution (5' to 3')

## Why This Exists

- **Without it**: Users manually inspect STAR/HISAT2/Salmon logs, compute mapping rates in spreadsheets, and lack standardized quality thresholds.
- **With it**: A single command parses any common RNA-seq aligner output and produces publication-ready figures with automatic quality assessment.
- **Why OmicsClaw**: Bridges the gap between raw FASTQ QC and count matrix QC, completing the upstream portion of the bulk RNA-seq pipeline.

## Input Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| STAR log | `Log.final.out` | STAR alignment final summary |
| HISAT2 log | `.log` | HISAT2 alignment summary |
| Salmon log | `meta_info.json` | Salmon quantification metadata |

## CLI Reference

```bash
python omicsclaw.py run bulkrna-read-alignment --demo
python omicsclaw.py run bulkrna-read-alignment --input Log.final.out --output results/
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── mapping_summary.png
│   ├── gene_body_coverage.png
│   └── alignment_composition.png
├── tables/
│   └── alignment_stats.csv
└── reproducibility/
    └── commands.sh
```

## Related Skills

- `bulkrna-read-qc` — Upstream: FASTQ QC before alignment
- `bulkrna-qc` — Downstream: count matrix QC after quantification
