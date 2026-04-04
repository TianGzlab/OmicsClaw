---
name: sc-metacell
description: >-
  Compress scRNA-seq data into metacell-level summaries using SEACells or a
  lightweight k-means aggregation fallback.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, metacell, seacells, compression]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--use-rep"
      - "--n-metacells"
      - "--celltype-key"
      - "--min-iter"
      - "--max-iter"
    saves_h5ad: true
    requires_preprocessed: true
---

# Single-Cell Metacell

## Why This Exists

- Without it: large noisy single-cell datasets are hard to summarize stably.
- With it: cells are compressed into metacell-level profiles for downstream DE, trajectory, and visualization.

## Current Methods

1. `seacells`
2. `kmeans`

## Key Parameters

| Parameter | Meaning |
|---|---|
| `--method` | `seacells` or `kmeans` |
| `--use-rep` | embedding in `adata.obsm` used for aggregation |
| `--n-metacells` | target metacell count |
| `--celltype-key` | optional label column for dominant-type summary |
| `--min-iter` / `--max-iter` | SEACells optimization controls |

## Outputs

- `metacells.h5ad`
- `tables/cell_to_metacell.csv`
- `tables/metacell_summary.csv`
- centroid plot when embedding is available

## References Inside OmicsClaw

- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-metacell-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-metacell.md`.
