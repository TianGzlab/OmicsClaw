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

## Data / State Requirements

- **Matrix**: expects normalized expression (log1p); if raw counts are detected, the skill normalizes automatically
- **Layers**: `layers["counts"]` preserved when present
- **Required metadata**: a perturbation label column in `adata.obs` (default: `perturbation`) with a control label (default: `NT`)
- **PCA**: if `X_pca` is missing, the skill computes it automatically

## Upstream Step

Run `sc-perturb-prep` first if you have raw expression + a barcode-to-sgRNA mapping file.
If your AnnData already has perturbation labels in `.obs`, you can use it directly.

## Workflow

1. Load input or generate demo data
2. Preflight: validate perturbation column and control label exist
3. Ensure PCA is available
4. Run Mixscape (perturbation signature + classification)
5. Detect degenerate output (all NP)
6. Persist results: `processed.h5ad` with contract metadata
7. Render gallery and export tables

## Outputs

- `processed.h5ad` (canonical output with contract metadata)
- `tables/mixscape_class_counts.csv`
- `tables/mixscape_global_class_counts.csv`
- `tables/mixscape_cell_classes.csv`
- `figures/mixscape_global_classes.png`
- `figure_data/` (plot-ready CSVs)
- `reproducibility/commands.sh`
- `result.json` and `report.md`

## Workflow Position

**Upstream:** sc-perturb-prep
**Downstream:** sc-de (DE between perturbed and control), sc-enrichment
