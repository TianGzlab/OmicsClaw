---
name: struct-proteomics
description: >-
  Structural proteomics and cross-linking MS analysis using XlinkX, pLink, or xiSEARCH.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [proteomics, structural, cross-linking, XL-MS, XlinkX, pLink]
metadata:
  omicsclaw:
    domain: proteomics
    emoji: "🏗️"
    trigger_keywords: [structural proteomics, cross-linking MS, XL-MS, XlinkX, pLink, xiSEARCH]
---

# 🏗️ Structural Proteomics

Cross-linking mass spectrometry (XL-MS) analysis. Identifies protein-protein interaction interfaces and distance constraints.

## CLI Reference

```bash
python omicsclaw.py run struct-proteomics --demo
python omicsclaw.py run struct-proteomics --input <data.csv> --output <dir>
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | `xlinkx` | xlinkx, plink, or xisearch |

## Why This Exists

- **Without it**: Identifying inter-linked peptides is a computational nightmare computationally mapping combinatorial massive search spaces
- **With it**: Efficiently deconvolutes cross-linker mass shifts to prove physical protein-protein interactions
- **Why OmicsClaw**: Standardizes structural XL-MS parsing which is traditionally highly vendor-locked

## Workflow

1. **Calculate**: Generate combinatorial databases based on cross-linker specificity.
2. **Execute**: Score intra- and inter-peptide linkages.
3. **Assess**: Estimate coordinate FDR constraints.
4. **Generate**: Output structural distance restraints.
5. **Report**: Synthesize 2D interaction network topologies.

## Example Queries

- "Analyze cross-linking MS data with XlinkX"
- "Find protein interactions from this pLink output"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── crosslinks.csv
├── figures/
│   └── interaction_network.png
├── tables/
│   └── specific_linkages.csv
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
- `data-import` — Upstream format parsing

## Citations

- [XlinkX](https://doi.org/10.1038/nmeth.3603)
- [pLink](https://doi.org/10.1038/nmeth.2099)
