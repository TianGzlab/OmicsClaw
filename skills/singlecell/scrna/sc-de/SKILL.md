---
name: sc-de
description: >-
  Differential expression for single-cell RNA-seq using Scanpy marker tests or
  an R-backed DESeq2 pseudobulk path. The wrapper separates exploratory
  cluster-level marker ranking from sample-aware pseudobulk analysis.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [singlecell, differential-expression, markers, wilcoxon, deseq2]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--celltype-key"
      - "--group1"
      - "--group2"
      - "--groupby"
      - "--method"
      - "--n-top-genes"
      - "--sample-key"
    param_hints:
      wilcoxon:
        priority: "groupby -> n_top_genes -> group1/group2"
        params: ["groupby", "n_top_genes", "group1", "group2"]
        defaults: {groupby: "leiden", n_top_genes: 10}
        requires: ["preprocessed_anndata", "scanpy"]
        tips:
          - "--method wilcoxon: Default exploratory marker-ranking path."
      t-test:
        priority: "groupby -> n_top_genes -> group1/group2"
        params: ["groupby", "n_top_genes", "group1", "group2"]
        defaults: {groupby: "leiden", n_top_genes: 10}
        requires: ["preprocessed_anndata", "scanpy"]
        tips:
          - "--method t-test: Parametric alternative to Wilcoxon."
      mast:
        priority: "groupby -> group1/group2 -> n_top_genes"
        params: ["groupby", "group1", "group2", "n_top_genes"]
        defaults: {groupby: "leiden", n_top_genes: 10}
        requires: ["R_MAST_stack", "log_normalized_expression_matrix"]
        tips:
          - "--method mast: R-backed MAST hurdle-model path on log-normalized expression."
      deseq2_r:
        priority: "groupby -> group1/group2 -> sample_key -> celltype_key"
        params: ["groupby", "group1", "group2", "sample_key", "celltype_key"]
        defaults: {sample_key: "sample_id", celltype_key: "cell_type"}
        requires: ["raw_counts_or_raw_layer", "biological_replicates", "R_DESeq2_stack"]
        tips:
          - "--method deseq2_r: Sample-aware pseudobulk path."
          - "--group1 and --group2 are required for the DESeq2 path."
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - differential expression
      - marker genes
      - de analysis
      - wilcoxon
      - pseudo-bulk
---

# Single-Cell Differential Expression

## Why This Exists

- Without it: users mix exploratory marker tests with replicate-aware inference and misread the results.
- With it: the wrapper makes the statistical path explicit and preserves the public DE contract.
- Why OmicsClaw: one interface covers quick Scanpy ranking and the heavier pseudobulk route.

## Scope Boundary

Implemented methods:

1. `wilcoxon`
2. `t-test`
3. `mast` for R-backed hurdle-model DE
4. `deseq2_r` for pseudobulk DE

## Input Contract

- Accepted input: preprocessed `.h5ad`
- `wilcoxon`, `t-test`, and `mast` expect log-normalized expression, preferably in `adata.raw`
- `deseq2_r` expects raw counts, preferably in `layers["counts"]`; it may read `adata.X` only when `X` itself is still an unnormalized count matrix, plus `group1`, `group2`, `sample_key`, and `celltype_key`
- All methods require a grouping column in `obs`

## Workflow Summary

1. Validate the requested DE mode.
2. Run Scanpy ranking or pseudobulk DESeq2.
3. Export full and top-hit tables.
4. Save `processed.h5ad`, `report.md`, and `result.json`.
5. Record the chosen method and grouping variables for downstream traceability.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-de/sc_de.py \
  --input <processed.h5ad> --groupby leiden --method wilcoxon --output <dir>

python skills/singlecell/scrna/sc-de/sc_de.py \
  --input <processed.h5ad> --groupby condition \
  --group1 treated --group2 control --method t-test --output <dir>

python skills/singlecell/scrna/sc-de/sc_de.py \
  --input <processed.h5ad> --method deseq2_r \
  --groupby condition --group1 treated --group2 control \
  --sample-key sample_id --celltype-key cell_type --output <dir>
```

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/de_full.csv`
- `tables/markers_top.csv`
- `reproducibility/commands.sh`

## Current Limitations

- `mast` requires an R environment with `MAST`, `SingleCellExperiment`, and `zellkonverter`.
- `deseq2_r` requires an R environment with `DESeq2`, `SingleCellExperiment`, and `zellkonverter`.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
