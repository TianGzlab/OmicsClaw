---
name: sc-filter
description: >-
  Filter cells and genes based on QC metrics. Supports custom thresholds
  and tissue-specific presets.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [singlecell, filter, QC, preprocessing]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--max-counts"
      - "--max-genes"
      - "--max-mt-percent"
      - "--min-cells"
      - "--min-counts"
      - "--min-genes"
      - "--tissue"
    saves_h5ad: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🔍"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install: []
    trigger_keywords:
      - filter cells
      - cell filtering
      - gene filtering
      - remove low quality
      - QC filtering
      - tissue-specific thresholds
---

# 🔍 Single-Cell Filter

Filter cells and genes based on QC metrics with support for tissue-specific thresholds.

## Why This Exists

- **Without it**: Low-quality cells and genes contaminate downstream analysis
- **With it**: Automated filtering with configurable or tissue-specific thresholds
- **Why OmicsClaw**: Tissue-specific presets (PBMC, brain, tumor, etc.)

## Core Capabilities

1. **Cell filtering**: Remove cells by gene counts, UMI counts, MT%
2. **Gene filtering**: Remove genes expressed in too few cells
3. **Tissue presets**: Pre-configured thresholds for common tissues
4. **Before/after comparison**: Visualize impact of filtering

## Workflow

1. **Load QC metrics**: Calculate or load existing QC metrics
2. **Apply filters**: Filter by customizable thresholds
3. **Filter genes**: Remove low-expression genes
4. **Report**: Generate summary statistics and comparison plots

## CLI Reference

```bash
# Basic usage
python skills/singlecell/scrna/sc-filter/sc_filter.py --input <data.h5ad> --output <dir>

# With tissue-specific thresholds
python skills/singlecell/scrna/sc-filter/sc_filter.py --input <data.h5ad> --output <dir> --tissue pbmc

# Custom thresholds
python skills/singlecell/scrna/sc-filter/sc_filter.py --input <data.h5ad> --output <dir> \
  --min-genes 200 --max-genes 6000 --max-mt-percent 15

# Demo mode
python omicsclaw.py run sc-filter --demo
```

## Tissue-Specific Thresholds

| Tissue | Min Genes | Max Genes | Max MT% |
|--------|-----------|-----------|---------|
| PBMC | 200 | 6000 | 5% |
| Brain | 500 | 8000 | 10% |
| Tumor | 200 | 8000 | 20% |
| Heart | 300 | 7000 | 15% |
| Liver | 300 | 7000 | 15% |
| Kidney | 300 | 7000 | 15% |
| Lung | 200 | 7000 | 15% |

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--min-genes` | 200 | Minimum genes per cell |
| `--max-genes` | None | Maximum genes per cell |
| `--min-counts` | None | Minimum UMIs per cell |
| `--max-counts` | None | Maximum UMIs per cell |
| `--max-mt-percent` | 20.0 | Maximum mitochondrial % |
| `--min-cells` | 3 | Minimum cells per gene |
| `--tissue` | None | Use tissue-specific thresholds |

## Example Queries

- "Filter cells using PBMC thresholds"
- "Remove low-quality cells with MT% > 15"
- "Filter genes expressed in < 3 cells"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── filtered.h5ad
├── figures/
│   ├── filter_comparison.png
│   └── filter_summary.png
├── tables/
│   └── filter_stats.csv
└── reproducibility/
    ├── commands.sh
    └── requirements.txt
```

## Dependencies

**Required**: scanpy, numpy, pandas

## Integration with Orchestrator

**Trigger conditions**:
- Query mentions "filter cells", "filter genes", "remove cells"
- Query mentions tissue-specific QC thresholds

**Chaining partners**:
- `sc-qc` — Calculate QC metrics before filtering
- `sc-preprocessing` — Continue with normalization after filtering
