---
name: bulkrna-trajblend
description: >-
  Bulk-to-single-cell trajectory interpolation — uses VAE and GNN to bridge bulk RNA-seq
  with single-cell reference data, generating synthetic single-cell profiles and embedding
  bulk samples into developmental trajectories.
version: 0.3.0
author: OmicsClaw
license: MIT
tags: [bulkrna, trajectory, interpolation, VAE, GNN, deconvolution, single-cell]
requires: [numpy, pandas, matplotlib, scipy, scikit-learn]
optional_requires: [torch, anndata]
metadata:
  omicsclaw:
    domain: bulkrna
    emoji: "🔀"
    trigger_keywords: [trajblend, trajectory, bulk to single cell, interpolation,
      bulk2single, VAE, deconvolution trajectory]
    allowed_extra_flags:
    - "--n-epochs"
    - "--reference"
    legacy_aliases: [bulk-trajblend]
    saves_h5ad: false
    script: bulkrna_trajblend.py
    param_hints: {}
    requires_preprocessed: false
---

# Bulk RNA-seq Trajectory Interpolation (BulkTrajBlend-style)

Bridges bulk RNA-seq data with single-cell reference to interpolate missing cell states and embed bulk samples into developmental trajectories. Implements a simplified BulkTrajBlend-inspired approach using variational autoencoders (VAE) for synthetic cell generation and nearest-neighbor trajectory mapping.

## Core Capabilities

- Estimate cell type fractions from bulk RNA-seq via deconvolution
- Generate synthetic single-cell profiles weighted by estimated fractions (VAE-inspired)
- Map bulk samples onto scRNA-seq trajectory embedding (PCA/UMAP)
- Pseudotime estimation for bulk samples based on nearest reference cells
- Visualization: trajectory plots with bulk-injected positions, fraction heatmaps

## Why This Exists

- **Without it**: Bulk RNA-seq data cannot be placed on developmental trajectories — users must generate new scRNA-seq data.
- **With it**: Existing bulk datasets gain trajectory context by leveraging available single-cell references.
- **Reference**: Inspired by `BulkTrajBlend` (omicverse), `Bulk2Single`, and related deconvolution-trajectory methods.

## Algorithm / Methodology

### Cell Fraction Estimation
- NNLS-based deconvolution against scRNA-seq reference signatures
- Alternative: pre-computed fractions from external tools (CIBERSORTx, etc.)

### Synthetic Cell Generation
- Weighted sampling of reference scRNA-seq cells according to estimated fractions
- Optional Gaussian noise injection to model biological variability
- Fractions serve as mixing weights for trajectory interpolation

### Trajectory Mapping
- Bulk samples projected onto reference PCA/UMAP embedding
- K-nearest reference cells used to estimate pseudotime
- Confidence intervals based on neighbor pseudotime variance

## Input Formats

| Format | Extension | Description |
|--------|-----------|-------------|
| Bulk expression | `.csv`, `.tsv` | Genes × samples count matrix |
| scRNA-seq reference | `.h5ad`, `.csv` | AnnData or matrix with cell type labels |

## CLI Reference

```bash
python omicsclaw.py run bulkrna-trajblend --demo
python omicsclaw.py run bulkrna-trajblend --input bulk_counts.csv \
  --reference scref.h5ad --output results/
```

## Output Structure

```
output_directory/
├── report.md
├── result.json
├── figures/
│   ├── trajectory_embedding.png
│   ├── fraction_heatmap.png
│   ├── pseudotime_distribution.png
│   └── bulk_on_trajectory.png
├── tables/
│   ├── cell_fractions.csv
│   ├── pseudotime_estimates.csv
│   └── synthetic_cells.csv
└── reproducibility/
    └── commands.sh
```

## Related Skills

- `bulkrna-deconvolution` — Upstream: cell type fraction estimation
- `bulkrna-qc` — Upstream: count matrix quality control
- `sc-trajectory` — Complementary: single-cell trajectory analysis
