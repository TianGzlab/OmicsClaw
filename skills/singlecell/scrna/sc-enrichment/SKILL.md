---
name: sc-enrichment
description: >-
  Single-cell gene-set activity scoring for annotated scRNA-seq data using the
  official AUCell Bioconductor implementation.
version: 0.1.0
author: OmicsClaw Team
license: MIT
tags: [singlecell, enrichment, pathway, geneset, aucell]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--gene-sets"
      - "--groupby"
      - "--top-pathways"
      - "--aucell-auc-max-rank"
    param_hints:
      aucell_r:
        priority: "gene_sets -> groupby -> aucell_auc_max_rank -> top_pathways"
        params: ["gene_sets", "groupby", "aucell_auc_max_rank", "top_pathways"]
        defaults: {groupby: "leiden", top_pathways: 20, aucell_auc_max_rank: "5% of detected features when omitted"}
        requires: ["AUCell", "GSEABase", "zellkonverter", "gene_sets_gmt"]
        tips:
          - "--method aucell_r: Official AUCell Bioconductor scoring path."
          - "--aucell-auc-max-rank: Official AUCell aucMaxRank override; leave unset to use the wrapper's 5% feature default."
    saves_h5ad: true
    requires_preprocessed: true
    trigger_keywords:
      - pathway enrichment
      - gene set enrichment
      - aucell
      - gene program scoring
      - pathway activity
---

# Single-Cell Enrichment

## Why This Exists

- Without it: per-cell pathway activity often gets conflated with bulk-like DE enrichment.
- With it: AUCell scores gene-set activity at the single-cell level and exports stable cell-wise score columns.
- Why OmicsClaw: one wrapper bundles AUCell scoring, grouped summaries, report output, and reproducibility artifacts.

## Core Capabilities

1. **Official AUCell execution** via the Bioconductor R package.
2. **Per-cell score export** back into `processed.h5ad`.
3. **Optional grouped summaries** using a user-selected `obs` column such as `leiden` or `cell_type`.
4. **Stable exports** for AUCell score matrices and top-ranked pathways.

## Scope Boundary

Implemented method:

1. `aucell_r`

This skill currently focuses on AUCell scoring only. It does not expose ORA, preranked GSEA, or scGSVA-style alternatives.

## Input Expectations

- Input object: preprocessed `.h5ad`
- Required gene-set file: `--gene-sets <path/to/file.gmt>` unless `--demo` is used
- Optional grouping column: `--groupby`

## CLI Reference

```bash
python omicsclaw.py run sc-enrichment \
  --input data.h5ad --gene-sets pathways.gmt --groupby leiden --output out/

python omicsclaw.py run sc-enrichment \
  --input data.h5ad --gene-sets pathways.gmt \
  --aucell-auc-max-rank 250 --top-pathways 25 --output out/
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | enrichment backend | current public value is `aucell_r` |
| `--gene-sets` | GMT gene-set file | required unless demo mode is used |
| `--groupby` | grouping column for summaries | optional but recommended |
| `--top-pathways` | export/plot size control | wrapper-level output control |
| `--aucell-auc-max-rank` | official AUCell `aucMaxRank` override | leave unset for wrapper default |

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/aucell_scores.csv`
- `tables/top_pathways.csv`
- `tables/group_mean_scores.csv` when `groupby` is available
- `figures/top_gene_sets.png`
- `figures/group_mean_heatmap.png` when `groupby` is available

Stable AnnData outputs:

- `adata.obs["aucell__*"]` score columns
- `adata.uns["sc_enrichment"]`

## Current Limitations

- This skill currently expects local GMT files rather than remote MSigDB fetching.
- The current wrapper does not expose AUCell threshold exploration.
