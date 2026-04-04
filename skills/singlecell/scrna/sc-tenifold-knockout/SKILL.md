---
name: sc-tenifold-knockout
description: >-
  Virtual knockout analysis for scRNA-seq using the official scTenifoldKnk R
  workflow on a wild-type expression matrix.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, virtual-knockout, grn, sctenifoldknk, perturbation]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--ko-gene"
      - "--qc"
      - "--qc-min-lib-size"
      - "--qc-min-cells"
      - "--n-net"
      - "--n-cells"
      - "--n-comp"
      - "--q"
      - "--td-k"
      - "--ma-dim"
      - "--n-cores"
---

# scTenifoldKnk Virtual Knockout

## Why This Exists

- Without it: virtual knockout analysis is usually left outside standard scRNA pipelines.
- With it: the official scTenifoldKnk workflow can predict downstream perturbed genes from a wild-type single-cell expression matrix.

## Current Method

1. `sctenifoldknk`

## Key Inputs

- a wild-type expression matrix with genes in rows and cells in columns
- a target gene via `--ko-gene`

## Public Parameters

| Parameter | Meaning |
|---|---|
| `--ko-gene` | target gene to virtually knock out |
| `--qc` | enable official internal QC |
| `--qc-min-lib-size` | minimum library size for QC |
| `--qc-min-cells` | minimum cells per gene after QC |
| `--n-net` | number of subnetworks to construct |
| `--n-cells` | cells subsampled per network |
| `--n-comp` | principal components used in network construction |
| `--q` | top-edge quantile retained |
| `--td-k` | CP tensor rank |
| `--ma-dim` | manifold alignment dimensions |
| `--n-cores` | parallel cores used by the R backend |

## Outputs

- `tables/tenifold_diff_regulation.csv`
- `figures/tenifold_top_fc.png`
- `result.json` and `report.md`
