---
name: peptide-id
description: >-
  Database search for peptide/protein identification using MaxQuant, MS-GF+, Comet, or Mascot.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [proteomics, peptide-identification, MaxQuant, MS-GF+, Comet]
metadata:
  omicsclaw:
    domain: proteomics
    emoji: "🔬"
    trigger_keywords: [peptide identification, database search, MaxQuant, MS-GF+, Comet, Mascot]
---

# 🔬 Peptide Identification

Peptide and protein identification from MS/MS spectra. Wraps MaxQuant/Andromeda, MS-GF+, and Comet.

## CLI Reference

```bash
python omicsclaw.py run peptide-id --demo
python omicsclaw.py run peptide-id --input <spectra.mzml> --output <dir>
```

## Why This Exists

- **Without it**: Raw mzML spectra are just m/z peaks, lacking biological meaning
- **With it**: Compares experimental MS/MS to in silico digested protein databases accurately
- **Why OmicsClaw**: Standardizes execution of major engines (MaxQuant, Comet) avoiding complex GUIs

## Workflow

1. **Calculate**: Prepare target-decoy databases and enzyme rules.
2. **Execute**: Run spectral similarity searches.
3. **Assess**: Perform FDR filtering via Percolator or Andromeda.
4. **Generate**: Output structural mappings of Peptides to Proteins.
5. **Report**: Tabulate key identification metrics.

## Example Queries

- "Identify peptides using MaxQuant on this mzML"
- "Search this raw file with MS-GF+"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── identified.csv
├── figures/
│   └── fdr_distribution.png
├── tables/
│   └── peptide_evidence.csv
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
- `ms-qc` — Upstream quality checks
- `quantification` — Downstream quantitative aggregation

## Citations

- [MaxQuant](https://doi.org/10.1038/nbt.1511)
- [MS-GF+](https://doi.org/10.1038/ncomms6277)
