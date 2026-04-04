---
name: sc-perturb
description: >-
  Single-cell perturbation analysis for scRNA-seq perturbation screens using
  the official pertpy Mixscape workflow.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, perturbation, perturb-seq, crispr, mixscape, pertpy]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--pert-key"
      - "--control"
      - "--split-by"
      - "--n-neighbors"
      - "--logfc-threshold"
      - "--pval-cutoff"
      - "--perturbation-type"
    saves_h5ad: true
---

# Single-Cell Perturbation

## Why This Exists

- Without it: perturbation screens often stop at naive grouping and miss responder versus non-responder structure.
- With it: the official pertpy Mixscape workflow computes perturbation signatures and classifies perturbed subpopulations.

## Current Methods

1. `mixscape`

## Key Inputs

- a perturbation-aware `AnnData`
- a perturbation column via `--pert-key`
- a control label via `--control`
- optional replicate / batch split via `--split-by`

## Public Parameters

| Parameter | Meaning |
|---|---|
| `--method` | currently `mixscape` |
| `--pert-key` | perturbation or guide label column in `adata.obs` |
| `--control` | control category in the perturbation column |
| `--split-by` | biological replicate or condition column |
| `--n-neighbors` | neighbors used for perturbation signature |
| `--logfc-threshold` | DE threshold used inside Mixscape |
| `--pval-cutoff` | DE p-value cutoff used inside Mixscape |
| `--perturbation-type` | expected perturbation label such as `KO` |

## Notes

- This wrapper uses the official `pertpy.tools.Mixscape` workflow.
- Mixscape is best suited for Perturb-seq or CRISPR perturbation screens with a clear control population.
- If the input AnnData does not already contain perturbation labels in `adata.obs`, prepare them upstream first; OmicsClaw now provides `sc-perturb-prep` for expression data plus barcode-to-guide mapping files.

## Outputs

- `tables/mixscape_class_counts.csv`
- `tables/mixscape_global_class_counts.csv`
- `tables/mixscape_cell_classes.csv`
- `figures/mixscape_global_classes.png`
- `perturbation_annotated.h5ad`
- `result.json` and `report.md`
