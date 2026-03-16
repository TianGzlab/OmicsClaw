---
name: genomics-sv-detection
description: >-
  Structural variant detection (DEL/DUP/INV/TRA): SV VCF parsing with BND notation,
  size classification (50bp-10Mb), evidence types. Wraps Manta, Lumpy, Delly, Sniffles.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [genomics, structural-variants, Manta, Delly, Sniffles]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "🧱"
    trigger_keywords: [structural variant, SV, Manta, Delly, Lumpy, Sniffles]
---

# 🧱 Structural Variant Detection

Structural variant calling for deletions, duplications, inversions, and translocations. Wraps Manta, Lumpy, Delly, Sniffles.

## CLI Reference

```bash
python omicsclaw.py run genomics-sv-detection --demo
python omicsclaw.py run genomics-sv-detection --input <data.bam> --output <dir>
```

## Why This Exists

- **Without it**: Conventional SNV callers miss massive >50bp translocations, inversions, or large deletions
- **With it**: Split-reads and paired-end discordance are utilized to find complex structural variation
- **Why OmicsClaw**: Encapsulates multiple specialized SV tools (Manta, Delly) with unified orchestration

## Workflow

1. **Calculate**: Extract discordant read-pairs and split-reads.
2. **Execute**: Build breakpoint graphs and candidate events.
3. **Assess**: Perform read-depth and confidence filtering.
4. **Generate**: Output structured VCF representation of SVs.
5. **Report**: Tabulate key SV counts.

## Example Queries

- "Call structural variants using Manta"
- "Detect chromosomal inversions using Sniffles from long reads"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── variants_sv.vcf.gz
├── figures/
│   └── sv_length_distribution.png
├── tables/
│   └── sv_summary.csv
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
- `align` — Upstream generation of BAM
- `vcf-ops` — Downstream VCF merging logic

## Citations

- [Manta](https://doi.org/10.1093/bioinformatics/btv710)
- [Delly](https://doi.org/10.1093/bioinformatics/bts378)
- [Sniffles](https://doi.org/10.1038/s41592-018-0001-7)
