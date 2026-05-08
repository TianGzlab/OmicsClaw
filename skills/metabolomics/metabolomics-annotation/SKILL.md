---
name: metabolomics-annotation
description: >-
  Metabolite annotation and structural identification using SIRIUS, CSI:FingerID,
  GNPS, or MetFrag.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [metabolomics, annotation, SIRIUS, GNPS, MetFrag]
metadata:
  omicsclaw:
    domain: metabolomics
    emoji: "🏷️"
    trigger_keywords: [metabolite annotation, SIRIUS, GNPS, MetFrag, spectral matching,
      metabolite ID]
    allowed_extra_flags:
    - "--method"
    legacy_aliases: [met-annotate]
    saves_h5ad: false
    script: metabolomics_annotation.py
    param_hints: {}
    requires_preprocessed: false
---

# 🏷️ Metabolite Annotation

Metabolite annotation and structural identification against spectral libraries. Supports SIRIUS/CSI:FingerID, GNPS, and MetFrag.

## CLI Reference

```bash
python omicsclaw.py run met-annotate --demo
python omicsclaw.py run met-annotate --input <features.csv> --output <dir>
```

## Why This Exists

- **Without it**: LC-MS peaks remain anonymous "features" defined only by m/z and retention time
- **With it**: Converts features into candidate chemical structures via spectral networking and in-silico fragmentation
- **Why OmicsClaw**: Centralizes access to fragmented knowledgebases (SIRIUS, GNPS, MetFrag)

## Workflow

1. **Calculate**: Extract pure MS2 spectra representations.
2. **Execute**: Query spectral libraries or generate fragmentation trees.
3. **Assess**: Score candidate chemical formulas and structures.
4. **Generate**: Output structural mappings of features to molecules.
5. **Report**: Tabulate top compound identifications with confidence tiers.

## Example Queries

- "Annotate these metabolomics features using SIRIUS"
- "Match MS2 spectra against GNPS libraries"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── annotated.csv
├── figures/
│   └── chemical_class_distribution.png
├── tables/
│   └── compound_identifications.csv
└── reproducibility/
    ├── commands.sh
    ├── requirements.txt
    └── checksums.sha256
```

## Safety

- **Local-first**: Local database matching where possible; transparent interactions for external APIs (like GNPS).
- **Disclaimer**: Requires OmicsClaw reporting structures and disclaimers.
- **Audit trail**: Hyperparameters and operational flow states are logged fully.

## Integration with Orchestrator

**Trigger conditions**:
- Automatically invoked dynamically based on tool metadata and user intent matching.

**Chaining partners**:
- `peak-detection` — Upstream feature extraction
- `met-diff` — Downstream structural interpretation of significant hits

## Citations

- [SIRIUS](https://doi.org/10.1038/s41592-019-0344-8)
- [GNPS](https://doi.org/10.1038/nbt.3597)
- [MetFrag](https://doi.org/10.1186/s13321-016-0115-9)
