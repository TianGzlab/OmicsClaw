---
name: assemble
description: >-
  De novo genome assembly using SPAdes, Megahit, Flye, or Canu.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [genomics, assembly, SPAdes, Flye, Canu]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "🧬"
    trigger_keywords: [genome assembly, de novo, SPAdes, Megahit, Flye, Canu]
---

# 🧬 Genome Assembly

De novo genome assembly for short and long reads. Wraps SPAdes, Megahit, Flye, and Canu.

## CLI Reference

```bash
python omicsclaw.py run assemble --demo
python omicsclaw.py run assemble --input <reads.fastq> --output <dir>
```

## Why This Exists

- **Without it**: Assemblies require intense memory management and parameter orchestration per graph build
- **With it**: Automated contig building and K-mer tuning logic across read modalities
- **Why OmicsClaw**: Unified containerized or local graph assembler invocation

## Workflow

1. **Calculate**: Prepare k-mer frequencies or long-read overlaps.
2. **Execute**: Build de Bruijn or string graphs.
3. **Assess**: Perform contig polishing and scaffolding.
4. **Generate**: Output structural FASTA representations.
5. **Report**: Synthesize N50 stats and completeness metrics.

## Example Queries

- "Assemble my isolate using SPAdes"
- "De novo genome assembly using Flye"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── assembled.fa
├── figures/
│   └── assembly_graph.png
├── tables/
│   └── quast_metrics.csv
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
- `genomics-qc` — Upstream read trimming
- `annotation` — Downstream genome annotation

## Citations

- [SPAdes](https://doi.org/10.1089/cmb.2012.0021)
- [Flye](https://doi.org/10.1038/s41587-019-0072-8)
