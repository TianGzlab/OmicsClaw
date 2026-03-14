---
name: genomics-qc
description: >-
  Sequencing reads quality control and adapter trimming using FastQC, MultiQC, or fastp.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [genomics, QC, FastQC, fastp, Trimmomatic]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "📊"
    trigger_keywords: [sequencing QC, FastQC, read quality, adapter trimming, fastp]
---

# 📊 Genomics QC

Quality control for genomic sequencing data. Wraps FastQC, MultiQC, and fastp for read-level QC and adapter trimming.

## CLI Reference

```bash
python omicsclaw.py run genomics-qc --demo
python omicsclaw.py run genomics-qc --input <reads.fastq> --output <dir>
```

## Why This Exists

- **Without it**: Traces of adapters, low-quality reads or overrepresented sequences break downstream assemblies/alignments
- **With it**: Reads are automatically trimmed, masked, and summarized
- **Why OmicsClaw**: Simplifies execution of widely used tools like FastQC and fastp simultaneously

## Workflow

1. **Calculate**: Map out local file metadata and basic stats.
2. **Execute**: Calculate quality heuristic per base pair position.
3. **Assess**: Detect adapters and k-mer enrichment.
4. **Generate**: Output trimmed sequences and MultiQC reports.
5. **Report**: Tabulate key pass/fail thresholds.

## Example Queries

- "Run FastQC on these fastq files"
- "Trim adapters using fastp"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.fastq.gz
├── figures/
│   └── gc_content.png
├── tables/
│   └── basic_statistics.csv
└── reproducibility/
    ├── commands.sh
    ├── environment.yml
    └── checksums.sha256
```

## Safety

- **Local-first**: Strict offline processing without external upload.
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `<raw_data_ingest>` — Upstream sample integration
- `align` — Downstream read alignment

## Citations

- [FastQC](https://www.bioinformatics.babraham.ac.uk/projects/fastqc/)
- [fastp](https://doi.org/10.1093/bioinformatics/bty560)
