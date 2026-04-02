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

## Core Capabilities

1. **Four DE paths**: Wilcoxon, t-test, MAST, and DESeq2 pseudobulk.
2. **Separation of statistical questions**: exploratory single-cell ranking versus replicate-aware pseudobulk inference.
3. **Matrix-aware contract**: normalized expression for ranking paths, raw counts for DESeq2 pseudobulk.
4. **Direct DE figure exports**: marker dotplot and rank-gene summary where supported.
5. **Downstream-ready export**: processed AnnData, DE tables, report, structured result JSON, README, and notebook artifacts.

## Scope Boundary

Implemented methods:

1. `wilcoxon`
2. `t-test`
3. `mast` for R-backed hurdle-model DE
4. `deseq2_r` for pseudobulk DE

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | current direct input path |
| Demo | `--demo` | yes | bundled fallback |

### Input Expectations

- Accepted input: preprocessed `.h5ad`
- `wilcoxon`, `t-test`, and `mast` expect log-normalized expression, preferably in `adata.raw`
- `deseq2_r` expects raw counts, preferably in `layers["counts"]`; it may read `adata.X` only when `X` itself is still an unnormalized count matrix, plus `group1`, `group2`, `sample_key`, and `celltype_key`
- All methods require a grouping column in `obs`

## Workflow

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

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | DE backend | `wilcoxon`, `t-test`, `mast`, or `deseq2_r` |
| `--groupby` | grouping column | core comparison axis |
| `--group1` / `--group2` | comparison levels | especially important for `mast` and `deseq2_r` |
| `--n-top-genes` | compact export size | ranking-output control |
| `--sample-key` | replicate/sample column | required by `deseq2_r` |
| `--celltype-key` | pseudobulk aggregation label | used by `deseq2_r` |

## Algorithm / Methodology

### Exploratory ranking paths

Current OmicsClaw exploratory DE includes:

1. `wilcoxon`
2. `t-test`
3. `mast`

These paths answer the cluster-marker or group-ranking question on normalized expression, ideally from `adata.raw`.

### Replicate-aware pseudobulk path

Current OmicsClaw `deseq2_r`:

1. expects raw counts, ideally from `layers["counts"]`
2. aggregates counts to pseudobulk using `sample_key` and `celltype_key`
3. runs DESeq2 through the shared R bridge

Important implementation note:

- `deseq2_r` is the only path here that is explicitly replicate-aware in the current wrapper.

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `tables/de_full.csv`
- `tables/markers_top.csv`
- `reproducibility/commands.sh`

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/marker_dotplot.png` when ranking outputs support it
- `figures/rank_genes_groups.png` when ranking outputs support it

### What Users Should Inspect First

1. `report.md`
2. `tables/de_full.csv`
3. `tables/markers_top.csv`
4. `figures/rank_genes_groups.png` when available
5. `processed.h5ad`

## Current Limitations

- `mast` requires an R environment with `MAST`, `SingleCellExperiment`, and `zellkonverter`.
- `deseq2_r` requires an R environment with `DESeq2`, `SingleCellExperiment`, and `zellkonverter`.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
