---
name: sc-perturb-prep
description: >-
  Prepare perturbation-ready scRNA AnnData objects by merging barcode-to-guide
  assignments into expression data and exporting a downstream-safe h5ad for
  `sc-perturb`.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, perturbation, perturb-seq, crispr, sgrna, guide-assignment]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--mapping-file"
      - "--barcode-column"
      - "--sgrna-column"
      - "--target-column"
      - "--sep"
      - "--delimiter"
      - "--gene-position"
      - "--pert-key"
      - "--sgrna-key"
      - "--target-key"
      - "--control-patterns"
      - "--control-label"
      - "--keep-multi-guide"
      - "--species"
    saves_h5ad: true
    requires_preprocessed: false
---

# Single-Cell Perturbation Preparation

## Why This Exists

- Without it: users often have a normal expression AnnData plus a separate sgRNA mapping file, but downstream perturbation methods need one merged object.
- With it: this skill standardizes the expression object, keeps gene-expression features, merges barcode-to-guide assignments, and writes a perturbation-ready `processed.h5ad`.

## Current Method

1. `mapping_tsv`

## Key Inputs

- an expression object: `.h5ad`, 10x `.h5`, or a 10x matrix directory
- a barcode-to-sgRNA mapping file for real runs
- optionally a target-gene column; otherwise the target can be inferred from sgRNA IDs

## Public Parameters

| Parameter | Meaning |
|---|---|
| `--mapping-file` | cell barcode to sgRNA mapping table |
| `--barcode-column` | barcode column name when the mapping file has a header |
| `--sgrna-column` | sgRNA / guide column name |
| `--target-column` | optional target-gene column name |
| `--delimiter` | delimiter used to infer target genes from sgRNA IDs |
| `--gene-position` | token index used when inferring target genes |
| `--pert-key` | output perturbation label column in `adata.obs` |
| `--control-patterns` | comma-separated patterns used to identify control guides |
| `--control-label` | canonical label stored for controls |
| `--keep-multi-guide` | keep multi-guide cells instead of dropping them |

## Notes

- This wrapper does not assign guides from raw FASTQ by itself.
- For real perturbation FASTQ, users still need an upstream guide-assignment pipeline such as Cell Ranger Feature Barcode / CRISPR Guide Capture or a CROP-seq mapping workflow.
- The output is designed to feed directly into `sc-perturb`.

## Outputs

- `processed.h5ad`
- `tables/perturbation_assignments.csv`
- `tables/assignment_status_counts.csv`
- `tables/perturbation_counts.csv`
- `tables/dropped_multi_guide_cells.csv` when applicable
- `figures/perturbation_counts.png`
- `result.json` and `report.md`
