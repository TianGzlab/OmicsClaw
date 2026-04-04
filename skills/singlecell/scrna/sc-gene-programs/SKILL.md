---
name: sc-gene-programs
description: >-
  Discover de novo gene programs and per-cell usage scores from scRNA-seq data
  using cNMF-compatible or NMF workflows.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, gene-programs, cnmf, nmf]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--n-programs"
      - "--n-iter"
      - "--seed"
      - "--layer"
      - "--top-genes"
    saves_h5ad: true
    requires_preprocessed: true
---

# Single-Cell Gene Programs

## Why This Exists

- Without it: users rely only on marker ranking and miss continuous programs.
- With it: coordinated expression modules and per-cell program usage become explicit outputs.

## Current Methods

1. `cnmf`
2. `nmf`

## Public Parameters

| Parameter | Meaning |
|---|---|
| `--method` | `cnmf` or `nmf` |
| `--n-programs` | number of latent programs |
| `--n-iter` | factorization iteration budget |
| `--seed` | random seed |
| `--layer` | optional expression layer |
| `--top-genes` | top genes reported per program |

## Outputs

- `tables/program_usage.csv`
- `tables/program_weights.csv`
- `tables/top_program_genes.csv`
- `figures/mean_program_usage.png`
- `result.json` and `report.md`

## References Inside OmicsClaw

- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-gene-programs-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-gene-programs.md`.
