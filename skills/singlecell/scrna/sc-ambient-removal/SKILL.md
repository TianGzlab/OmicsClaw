---
name: sc-ambient-removal
description: >-
  Remove ambient RNA contamination from single-cell data using CellBender,
  SoupX, or simple subtraction methods.
version: 0.4.0
author: OmicsClaw
license: MIT
tags: [singlecell, ambient, cellbender, contamination, QC]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--contamination"
      - "--expected-cells"
      - "--filtered-matrix-dir"
      - "--method"
      - "--raw-h5"
      - "--raw-matrix-dir"
    saves_h5ad: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧹"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: cellbender
        bins: []
    trigger_keywords:
      - ambient RNA
      - ambient removal
      - cellbender
      - contamination
      - background RNA
---

# 🧹 Single-Cell Ambient RNA Removal

Remove ambient RNA contamination from droplet-based scRNA-seq data.

## Why This Exists

- **Without it**: Ambient RNA from lysed cells contaminates expression profiles
- **With it**: Cleaner gene expression for better cell type annotation
- **Why OmicsClaw**: Multiple methods with automatic contamination estimation

## Core Capabilities

1. **CellBender**: Deep learning-based ambient removal (recommended for 10X)
2. **SoupX (R)**: Ambient RNA estimation using raw/filtered 10X matrix pairs
3. **Simple subtraction**: Quick ambient profile subtraction
4. **Contamination estimation**: Automatic or manual contamination fraction

## Workflow

1. **Load data**: Load raw or filtered count matrix
2. **Estimate contamination**: Calculate ambient RNA fraction
3. **Correct counts**: Remove ambient RNA contribution
4. **Report**: Compare before/after counts

## CLI Reference

```bash
# Basic usage with simple method
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py --input <data.h5ad> --output <dir>

# With CellBender (requires raw H5)
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py --raw-h5 <raw.h5> \
  --output <dir> --method cellbender --expected-cells 10000

# With SoupX (requires raw + filtered 10X directories)
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --input <filtered.h5ad> --method soupx \
  --raw-matrix-dir raw_feature_bc_matrix/ \
  --filtered-matrix-dir filtered_feature_bc_matrix/ \
  --output <dir>

# Specify contamination fraction
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py --input <data.h5ad> \
  --output <dir> --contamination 0.05

# Demo mode
python omicsclaw.py run sc-ambient-removal --demo
```

## Methods

### CellBender (Recommended)
- Uses deep generative model
- Requires raw Feature-Barcode Matrix
- GPU recommended for speed

### Simple Subtraction
- Estimates ambient profile from data
- Fast, works with any count matrix
- Good for quick cleanup

### SoupX
- Requires both `--raw-matrix-dir` and `--filtered-matrix-dir`
- Best suited for 10x raw/filtered matrix pairs
- Runs through the R bridge and writes the corrected counts back into AnnData

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--method` | simple | cellbender, soupx, simple |
| `--contamination` | 0.05 | Contamination fraction |
| `--expected-cells` | None | Expected cells (CellBender) |
| `--raw-h5` | None | Raw H5 file (CellBender) |
| `--raw-matrix-dir` | None | 10x raw matrix directory for SoupX |
| `--filtered-matrix-dir` | None | 10x filtered matrix directory for SoupX |

## Example Queries

- "Remove ambient RNA contamination"
- "Run CellBender on my data"
- "Clean up ambient RNA from 10X data"

## Output Structure

```
output_dir/
├── report.md
├── result.json
├── corrected.h5ad
├── figures/
│   ├── counts_comparison.png
│   └── count_distribution.png
└── reproducibility/
    ├── commands.sh
    └── requirements.txt
```

## Dependencies

**Required**: scanpy, numpy, pandas
**Optional**: cellbender (for CellBender method), R + packages `SoupX` and `Seurat` (executed via native R scripts)

## Citations

- [CellBender](https://doi.org/10.1016/j.cels.2018.11.005) — Fleming et al.
- [SoupX](https://doi.org/10.15252/msb.202110382) — Young & Behjati

## Integration with Orchestrator

**Trigger conditions**:
- Query mentions "ambient RNA", "CellBender", "contamination"

**Chaining partners**:
- `sc-qc` — QC before ambient removal
- `sc-filter` — Filter after ambient removal
