---
name: sc-in-silico-perturbation
description: >-
  In-silico perturbation analysis for scRNA-seq. Simulates the effect of
  knocking out a target gene and identifies differentially regulated genes.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [singlecell, virtual-knockout, grn, perturbation, sctenifoldknk]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--ko-gene"
      - "--n-top-genes"
      - "--corr-threshold"
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

# In-Silico Perturbation

## Why This Exists

- Without it: virtual perturbation analysis requires manual GRN construction and comparison, or running R scripts outside the scRNA pipeline.
- With it: this skill provides a unified interface for in-silico gene knockout simulation, ranking downstream-affected genes.

## Data / State Requirements

- **Input matrix**: raw counts preferred (in `layers["counts"]` or `X`).
- **Gene names**: the KO gene must exist in `adata.var_names`.
- **No upstream clustering required**: this skill operates on the expression matrix directly.

### Upstream Step

Run `sc-preprocessing` first if your data is not yet in AnnData format. If you already have a count matrix (h5ad, CSV, or 10X), this skill can load it directly.

## Methods

### Method Selection Table

| Scenario | Recommended method | Example |
|----------|-------------------|---------|
| Quick Python-only analysis | `grn_ko` (default) | `--method grn_ko --ko-gene TP53` |
| Need official scTenifoldKnk results | `sctenifoldknk` | `--method sctenifoldknk --ko-gene TP53` |
| No R installed | `grn_ko` | `--method grn_ko` |

### grn_ko (Python, default)

Builds a Pearson correlation-based gene regulatory network from the expression matrix, zeroes the KO gene's edges, and scores differential regulation per gene. Fast, no R required.

### sctenifoldknk (R)

Official scTenifoldKnk pipeline via Rscript. Constructs multiple subnetworks via pcNet, applies tensor decomposition, aligns WT and KO manifolds, and tests for differential regulation. Requires R with the `scTenifoldKnk` package installed.

## Public Parameters

### Shared

| Parameter | Meaning |
|---|---|
| `--method` | `grn_ko` (Python, default) or `sctenifoldknk` (R) |
| `--ko-gene` | Target gene to virtually knock out |

### grn_ko parameters

| Parameter | Default | Meaning |
|---|---|---|
| `--n-top-genes` | 2000 | Number of HVGs used for GRN construction |
| `--corr-threshold` | 0.05 | Minimum absolute Pearson correlation for GRN edges |

### sctenifoldknk parameters (R only)

| Parameter | Default | Meaning |
|---|---|---|
| `--qc` | off | Enable official internal QC |
| `--qc-min-lib-size` | 0 | Minimum library size for QC |
| `--qc-min-cells` | 10 | Minimum cells per gene after QC |
| `--n-net` | 2 | Number of subnetworks to construct |
| `--n-cells` | 100 | Cells subsampled per network |
| `--n-comp` | 3 | Principal components used in network construction |
| `--q` | 0.8 | Top-edge quantile retained |
| `--td-k` | 2 | CP tensor rank |
| `--ma-dim` | 2 | Manifold alignment dimensions |
| `--n-cores` | 1 | Parallel cores used by the R backend |

## Workflow

1. Load expression data (h5ad or demo)
2. Preflight: validate KO gene exists, check matrix semantics, detect species
3. Build GRN from WT expression matrix
4. Simulate knockout by removing the target gene's edges
5. Score and rank differentially regulated genes
6. Persist results: `processed.h5ad`, tables, figures
7. Render gallery and write manifests

## Outputs

- `processed.h5ad` -- annotated AnnData with perturbation scores in `adata.var`
- `tables/diff_regulation.csv` -- full differential regulation table
- `figures/top_perturbed_genes.png` -- bar chart of top perturbed genes
- `figures/pvalue_distribution.png` -- p-value distribution histogram
- `figures/manifest.json` -- figure gallery manifest
- `figure_data/manifest.json` -- plot-ready data manifest
- `result.json` -- machine-readable results with diagnostics
- `report.md` -- human-readable analysis report

## Matrix Contract

This skill reads raw counts and preserves them:
- `X = raw_counts`
- `layers["counts"] = raw_counts`
- Output `processed.h5ad` includes `omicsclaw_input_contract` and `omicsclaw_matrix_contract`

## Reference Data Guide

This skill does not require external reference data. All computation is performed on the input expression matrix.

## Usual Next Step

After identifying perturbed genes, consider:
- `sc-enrichment` -- pathway enrichment on the top perturbed genes
- `sc-grn` -- full gene regulatory network inference for deeper analysis

## Workflow Position

**Upstream:** sc-clustering or sc-cell-annotation
**Downstream:** sc-enrichment (enrich perturbed genes)
