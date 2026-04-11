---
name: sc-differential-abundance
description: >-
  Sample-aware differential abundance and compositional analysis for scRNA-seq
  using Milo, scCODA, or an exploratory proportion-based fallback.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, differential-abundance, compositional, milo, sccoda]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--condition-key"
      - "--sample-key"
      - "--cell-type-key"
      - "--contrast"
      - "--reference-cell-type"
      - "--fdr"
      - "--prop"
      - "--n-neighbors"
      - "--min-count"
    saves_h5ad: true
    requires_preprocessed: true
---

# Single-Cell Differential Abundance

## Why This Exists

- Without it: users often confuse differential expression with differential abundance.
- With it: sample-aware changes in cell-state or cell-type prevalence are reported explicitly.

## Current Methods

1. `milo`
2. `sccoda`
3. `simple` (exploratory proportion screen)

## Key Inputs

- a preprocessed `AnnData`
- sample-level replication via `--sample-key`
- biological condition via `--condition-key`
- a grouping column via `--cell-type-key`

## Public Parameters

| Parameter | Meaning |
|---|---|
| `--method` | `milo`, `sccoda`, or exploratory `simple` |
| `--condition-key` | condition column in `adata.obs` |
| `--sample-key` | sample / donor column in `adata.obs` |
| `--cell-type-key` | cell type or state column in `adata.obs` |
| `--contrast` | explicit comparison like `control vs stim` |
| `--reference-cell-type` | scCODA reference cell type |
| `--fdr` | FDR cutoff for reporting |
| `--prop` | Milo neighborhood sampling fraction |
| `--n-neighbors` | KNN size if a graph must be rebuilt |

## Notes

- `milo` is the preferred neighborhood-level DA path when replicate structure is available.
- `sccoda` is a compositional Bayesian path and requires a reference cell type concept.
- `simple` is not a replacement for replicate-aware DA; it is a lightweight fallback.

## Outputs

- `tables/sample_by_celltype_counts.csv`
- `tables/sample_by_celltype_proportions.csv`
- method-specific result tables
- `figures/sample_celltype_proportions.png`
- `result.json` and `report.md`

## References Inside OmicsClaw

- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-differential-abundance-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-differential-abundance.md`.

## Workflow Position

**Upstream:** sc-clustering or sc-cell-annotation (with condition/sample metadata)
**Downstream:** Terminal analysis. Consider: sc-de for gene-level differences
