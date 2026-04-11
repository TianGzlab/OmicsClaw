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

| Method | Description | Dependencies |
|---|---|---|
| `milo` | Neighborhood-level DA using Milo (replicate-aware) | pertpy |
| `sccoda` | Bayesian compositional analysis | pertpy |
| `simple` | Exploratory proportion screen (no replicates needed) | statsmodels |
| `proportion_test_r` | Monte Carlo permutation test for cell type proportion changes. Produces obs_log2FD with bootstrap 95% CI per cell type per comparison. | base R only |

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

## Usage Examples

```bash
# Proportion test (R, no external deps)
python omicsclaw.py run sc-differential-abundance --demo --method proportion_test_r --output /tmp/prop_test_demo

# Milo (replicate-aware)
python omicsclaw.py run sc-differential-abundance --demo --method milo --output /tmp/milo_demo
```

## Notes

- `milo` is the preferred neighborhood-level DA path when replicate structure is available.
- `sccoda` is a compositional Bayesian path and requires a reference cell type concept.
- `simple` is not a replacement for replicate-aware DA; it is a lightweight fallback.
- `proportion_test_r` uses base R only (zero installs needed). It runs a Monte Carlo permutation test and produces lollipop plots with bootstrap confidence intervals.

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
