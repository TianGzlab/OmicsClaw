---
name: sc-standardize-input
description: >-
  Canonicalize single-cell input into a stable AnnData contract for downstream
  OmicsClaw scRNA skills.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, scrna, input, standardization, anndata, preprocessing]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--species"
    saves_h5ad: true
    requires_preprocessed: false
    emoji: "🧱"
    trigger_keywords:
      - standardize AnnData
      - fix scRNA input
      - canonicalize single-cell input
      - prepare AnnData
      - input contract
---

# 🧱 Single-Cell Input Standardization

You are **SC Standardize Input**, the OmicsClaw skill for turning heterogeneous
single-cell inputs into a stable AnnData contract before downstream analysis.

## What This Skill Does

1. loads user input through the shared single-cell loader
2. chooses the best available count-like expression source (`layers['counts']`, `adata.raw`, or `adata.X`)
3. standardizes feature names for downstream QC and analysis
4. ensures `adata.layers['counts']` exists as the canonical raw-count layer
5. records provenance in `adata.uns['omicsclaw_input_contract']`
6. saves a downstream-ready `standardized_input.h5ad`

## What This Skill Does Not Do

1. it does not filter cells or genes
2. it does not normalize or cluster the data
3. it does not run biological analysis; it only stabilizes the input contract

## Recommended Usage

Run this skill first when:
- users provide arbitrary `.h5ad` files from outside OmicsClaw
- raw counts may live in `adata.raw` or `layers['counts']` instead of `adata.X`
- gene identifiers may need harmonization before QC or downstream scRNA skills

## CLI

```bash
python skills/singlecell/scrna/sc-standardize-input/sc_standardize_input.py \
  --input <data.h5ad> --output <dir>

oc run sc-standardize-input --input <data.h5ad> --output <dir>
```
