---
name: genomics-alignment
description: >-
  Alignment statistics from SAM/BAM files: mapping rate, MAPQ distribution,
  insert size, duplicate rate, proper pair rate. Mirrors samtools-flagstat.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [genomics, alignment, BWA, Bowtie2, Minimap2]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "🎯"
    trigger_keywords: [alignment, BWA, Bowtie2, Minimap2, map reads]
---

# 🎯 Genomics Read Alignment

Short and long read alignment to reference genomes. Supports BWA-MEM, Bowtie2, and Minimap2.

## CLI Reference

```bash
python omicsclaw.py run genomics-alignment --demo
python omicsclaw.py run genomics-alignment --input <reads.fastq> --output <dir>
```

## Why This Exists

- **Without it**: Alignment is run with disparate tools and ad-hoc flags causing unrecoverable errors downstream
- **With it**: Unified syntax automatically scaling threads and standardizing BAM/CRAM outputs
- **Why OmicsClaw**: Provides a standard local-first interface with built-in QC logging.

## Workflow

1. **Calculate**: Prepare sequences and parameterize indexing.
2. **Execute**: Run primary alignment heuristics over genomes.
3. **Assess**: Perform mapping quality filtering and deduplication.
4. **Generate**: Output structural mappings or sorted BAMs.
5. **Report**: Synthesize alignment stats into tables.

## Example Queries

- "Run alignment on my fastq data using BWA"
- "Map long reads using Minimap2 to reference"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.bam
├── figures/
│   └── mapping_stats.png
├── tables/
│   └── alignment_metrics.csv
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
- `genomics-qc` — Upstream quality checks
- `variant-call` — Downstream variant discovery

## Citations

- [BWA-MEM](https://doi.org/10.1093/bioinformatics/btp324)
- [Minimap2](https://doi.org/10.1093/bioinformatics/bty191)
