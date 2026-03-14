---
name: vcf-ops
description: >-
  VCF file operations — filtering, merging, statistics using bcftools and GATK.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [genomics, VCF, bcftools, filtering]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "📋"
    trigger_keywords: [VCF, bcftools, variant filter, merge VCF]
---

# 📋 VCF Operations

VCF manipulation, filtering, merging, and summary statistics. Wraps bcftools and GATK SelectVariants.

## CLI Reference

```bash
python omicsclaw.py run vcf-ops --demo
python omicsclaw.py run vcf-ops --input <data.vcf> --output <dir>
```

## Why This Exists

- **Without it**: Massive cohort VCF files are intractable to manipulate or filter manually
- **With it**: Fast algebraic operations stream variants safely and precisely
- **Why OmicsClaw**: Translates complex bcftools syntax into plain intuitive language prompts

## Workflow

1. **Calculate**: Map sequence ranges or filter criteria strings.
2. **Execute**: Perform stream-based querying over compressed index.
3. **Assess**: Ensure output satisfies the boundary limits dynamically.
4. **Generate**: Output sub-sampled VCF representations.
5. **Report**: Tabulate variant extraction statistics.

## Example Queries

- "Filter this vcf file keeping only PASS variants"
- "Merge these sample vcfs using bcftools"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.vcf.gz
├── figures/
│   └── filter_stats.png
├── tables/
│   └── cohort_summary.csv
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
- `variant-call` — Upstream VCF source
- `annotation` — Downstream downstream impact modeling

## Citations

- [bcftools](https://samtools.github.io/bcftools/)
- [GATK](https://gatk.broadinstitute.org/)
