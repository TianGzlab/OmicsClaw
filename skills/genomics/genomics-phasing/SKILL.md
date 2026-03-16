---
name: genomics-phasing
description: >-
  Haplotype phasing analysis: phase block N50, phased fraction, PS (Phase Set) field parsing,
  pipe-delimited genotype detection. Wraps WhatsHap, SHAPEIT5, Eagle2.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [genomics, phasing, haplotype, WhatsHap, SHAPEIT]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "🔀"
    trigger_keywords: [haplotype phasing, WhatsHap, SHAPEIT, Eagle, phasing]
---

# 🔀 Haplotype Phasing

Haplotype phasing for variant data. Wraps WhatsHap, SHAPEIT, and Eagle.

## CLI Reference

```bash
python omicsclaw.py run genomics-phasing --demo
python omicsclaw.py run genomics-phasing --input <data.vcf> --output <dir>
```

## Why This Exists

- **Without it**: Variants remain independent loci without knowledge of allelic connectivity
- **With it**: Haplotypes are formed spanning genes, essential for compound heterozygote analysis
- **Why OmicsClaw**: Standardizes input and output across read-backed and population-backed phasing tools

## Workflow

1. **Calculate**: Prepare VCF indices and sequence mappings.
2. **Execute**: Run haplotype graph resolution algorithms.
3. **Assess**: Perform switch error evaluation and quality flagging.
4. **Generate**: Output structured phased VCF representation.
5. **Report**: Synthesize N50 phase block stats into tables.

## Example Queries

- "Phase this vcf file using WhatsHap"
- "Use SHAPEIT for population phasing of variants"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── phased.vcf.gz
├── figures/
│   └── phase_block_distribution.png
├── tables/
│   └── phasing_metrics.csv
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
- `variant-call` — Upstream generation of raw VCFs
- `annotation` — Downstream annotation of phased haplotypes

## Citations

- [WhatsHap](https://doi.org/10.1089/cmb.2014.0157)
- [SHAPEIT](https://doi.org/10.1038/nmeth.4507)
