---
name: genomics-variant-annotation
description: >-
  Variant annotation and functional effect prediction using VEP, snpEff, or ANNOVAR.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [genomics, annotation, VEP, snpEff, ANNOVAR]
metadata:
  omicsclaw:
    domain: genomics
    emoji: "📝"
    trigger_keywords: [variant annotation, VEP, snpEff, ANNOVAR, functional effect]
---

# 📝 Variant Annotation

Variant annotation and functional effect prediction. Supports VEP, snpEff, and ANNOVAR.

## CLI Reference

```bash
python omicsclaw.py run genomics-variant-annotation --demo
python omicsclaw.py run genomics-variant-annotation --input <data.vcf> --output <dir>
```

## Why This Exists

- **Without it**: Variants lack biological context, remaining as simple coordinate tuples
- **With it**: Transforms structural variation into biological impact and transcript-level consequences
- **Why OmicsClaw**: Unified framework for multiple ontology backends like VEP or ANNOVAR without custom parsing

## Workflow

1. **Calculate**: Prepare genome indices and transcript boundary maps.
2. **Execute**: Run annotation search across known consequence states.
3. **Assess**: Filter variants by putative pathological score.
4. **Generate**: Save annotated VCFs with strict ontologies.
5. **Report**: Tabulate key functionally relevant variants.

## Example Queries

- "Annotate this vcf file using VEP"
- "Run snpEff and summarize high impact variants"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── annotated.vcf.gz
├── figures/
│   └── impact_distribution.png
├── tables/
│   └── top_variants.csv
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
- `variant-call` — Upstream raw variation
- `vcf-ops` — Upstream filtering steps

## Citations

- [VEP](https://doi.org/10.1186/s13059-016-0974-4) — Variant Effect Predictor
- [snpEff](https://doi.org/10.4161/fly.19695)
- [ANNOVAR](https://doi.org/10.1093/nar/gkq603)
