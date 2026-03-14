---
name: proteomics-ms-qc
description: >-
  Mass spectrometry raw data quality control using PTXQC, rawTools, or MSstatsQC.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [proteomics, QC, mass-spectrometry, PTXQC]
metadata:
  omicsclaw:
    domain: proteomics
    emoji: "📊"
    trigger_keywords: [MS QC, mass spec QC, PTXQC, rawTools]
---

# 📊 Proteomics MS-QC

Mass spectrometry data quality control. Computes basic QC statistics for protein/peptide abundance tables.

## CLI Reference

```bash
python omicsclaw.py run proteomics-ms-qc --demo
python omicsclaw.py run proteomics-ms-qc --input <data.csv> --output <dir>
```

## Why This Exists

- **Without it**: Instrument drift, missed cleavages, or poor LC gradients ruin quantitative integrity
- **With it**: Identifies bad samples early before costly downstream statistical processing
- **Why OmicsClaw**: Provides a unified mass-spectrometer agnostic report dashboard

## Workflow

1. **Calculate**: Extract basic peptide features and contaminant ratios.
2. **Execute**: Run descriptive statistics across raw files.
3. **Assess**: Flag outliers outside expected robust median ranges.
4. **Generate**: Output normalized QC matrices.
5. **Report**: Synthesize multiple metric traces across runs.

## Example Queries

- "Run mass spec QC on this data using PTXQC"
- "Assess proteomics instrument performance"

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── metrics.csv
├── figures/
│   └── qc_dashboard.pdf
├── tables/
│   └── qc_summary.csv
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
- `quantification` — Downstream normalized feature tables

## Citations

- [PTXQC](https://doi.org/10.1021/acs.jproteome.5b00780)
