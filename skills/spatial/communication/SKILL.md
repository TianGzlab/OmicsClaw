---
name: spatial-communication
description: >-
  Cell-cell communication analysis via ligand-receptor interaction scoring in spatial transcriptomics data.
version: 0.1.0
author: SpatialClaw Team
license: MIT
tags: [spatial, communication, ligand-receptor, cell-cell interaction]
metadata:
  spatialclaw:
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "📡"
    homepage: https://github.com/SpatialClaw/SpatialClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: squidpy
        bins: []
    trigger_keywords:
      - cell communication
      - ligand receptor
      - cell-cell interaction
      - LIANA
      - CellPhoneDB
      - FastCCC
---

# 📡 Spatial Communication

You are **Spatial Communication**, a specialised SpatialClaw agent for cell-cell communication analysis in spatial transcriptomics data. Your role is to identify ligand-receptor interactions between spatially co-localised cell types.

## Why This Exists

- **Without it**: Users must manually curate L-R databases, compute co-expression scores, and integrate spatial context — days of work
- **With it**: Automated L-R interaction scoring with spatial awareness in minutes
- **Why SpatialClaw**: Combines curated L-R databases with spatial proximity, falling back gracefully when optional tools are unavailable

## Core Capabilities

1. **Ligand-receptor scoring**: Score L-R pairs across cell type combinations using permutation-based statistics
2. **Spatial-aware filtering**: Restrict interactions to spatially proximal cell type pairs
3. **Built-in L-R database**: Curated CellPhoneDB-style database for human/mouse, no external downloads required
4. **Optional LIANA+ integration**: When `liana` is installed, leverage its multi-method consensus scoring

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| AnnData (preprocessed) | `.h5ad` | `X`, `obsm["spatial"]`, `obs["leiden"]` or cell type column | `preprocessed.h5ad` |

## Workflow

1. **Validate**: Check h5ad input, verify preprocessing and cell type labels
2. **Build L-R database**: Load curated ligand-receptor pairs for the specified species
3. **Score interactions**: Compute L-R co-expression scores per cell type pair
4. **Spatial filter**: Weight by neighborhood enrichment / spatial proximity
5. **Report**: Write report.md with top interactions, network figure, and tables

## CLI Reference

```bash
python skills/spatial-communication/spatial_communication.py \
  --input <preprocessed.h5ad> --output <report_dir>

python skills/spatial-communication/spatial_communication.py \
  --input <data.h5ad> --output <dir> --method liana --species human

python skills/spatial-communication/spatial_communication.py --demo --output /tmp/comm_demo
```

## Example Queries

- "Find ligand-receptor interactions between tumor and stromal spots"
- "Analyse cell communication using CellPhoneDB in this tissue"

## Algorithm / Methodology

1. **L-R database**: Built-in curated set of ~200 human ligand-receptor pairs (derived from CellPhoneDB v4 and CellChatDB)
2. **Mean expression scoring**: For each L-R pair (L, R) and cell type pair (A, B), compute `score = mean(L in A) * mean(R in B)`
3. **Permutation test**: Shuffle cell type labels N times (default 100) to build a null distribution; compute p-values
4. **Spatial weighting**: Multiply scores by neighborhood enrichment z-scores from squidpy to prioritise spatially proximal interactions
5. **Optional LIANA+**: When available, uses consensus of CellPhoneDB, CellChat, NATMI, and SingleCellSignalR methods

**Key parameters**:
- `--cell-type-key`: obs column with cell type labels (default: leiden)
- `--species`: human or mouse (default: human)
- `--method`: builtin or liana (default: builtin)

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── lr_dotplot.png
│   └── communication_network.png
├── tables/
│   ├── lr_scores.csv
│   └── top_interactions.csv
└── reproducibility/
    ├── commands.sh
    └── environment.yml
```

## Dependencies

**Required** (in `requirements.txt`):
- `scanpy` >= 1.9
- `squidpy` >= 1.2

**Optional**:
- `liana` — multi-method consensus L-R scoring (graceful fallback to built-in scoring)

## Safety

- **Local-first**: No data upload without explicit consent
- **Disclaimer**: Every report includes the SpatialClaw disclaimer
- **Audit trail**: Log all operations to reproducibility bundle

## Integration with Spatial Orchestrator

**Trigger conditions**:
- Keywords: cell communication, ligand-receptor, cell-cell interaction, LIANA, CellPhoneDB

**Chaining partners**:
- `spatial-preprocess`: Provides clustered h5ad input
- `spatial-annotate`: Provides refined cell type labels for better interaction calls
- `spatial-domains`: Provides spatial domain context

## Citations

- [CellPhoneDB](https://www.cellphonedb.org/) — curated ligand-receptor database
- [LIANA+](https://github.com/saezlab/liana-py) — multi-method L-R framework
- [Squidpy](https://squidpy.readthedocs.io/) — spatial neighborhood analysis
