---
name: sc-de
description: >-
  Differential expression for single-cell RNA-seq using exploratory Scanpy
  ranking, R-backed MAST, or replicate-aware pseudobulk DESeq2. The wrapper
  separates cluster/group marker ranking from sample-aware condition DE.
version: 0.6.0
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
      - "--log2fc-threshold"
      - "--logreg-solver"
      - "--method"
      - "--n-top-genes"
      - "--padj-threshold"
      - "--pseudobulk-min-cells"
      - "--pseudobulk-min-counts"
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
      logreg:
        priority: "groupby -> logreg_solver -> n_top_genes"
        params: ["groupby", "logreg_solver", "n_top_genes"]
        defaults: {groupby: "leiden", logreg_solver: "lbfgs", n_top_genes: 10}
        requires: ["preprocessed_anndata", "scanpy"]
        tips:
          - "--method logreg: Logistic-regression ranking, useful when you want genes that best separate one group from the others."
      mast:
        priority: "groupby -> group1/group2 -> n_top_genes"
        params: ["groupby", "group1", "group2", "n_top_genes"]
        defaults: {groupby: "leiden", n_top_genes: 10}
        requires: ["R_MAST_stack", "log_normalized_expression_matrix"]
        tips:
          - "--method mast: R-backed MAST hurdle-model path on log-normalized expression."
      deseq2_r:
        priority: "groupby -> group1/group2 -> sample_key -> celltype_key -> pseudobulk thresholds"
        params: ["groupby", "group1", "group2", "sample_key", "celltype_key", "pseudobulk_min_cells", "pseudobulk_min_counts"]
        defaults: {sample_key: "sample_id", celltype_key: "cell_type", pseudobulk_min_cells: 10, pseudobulk_min_counts: 1000}
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

1. **Five DE paths**: Wilcoxon, t-test, logistic regression, MAST, and DESeq2 pseudobulk.
2. **Separation of statistical questions**: exploratory single-cell ranking versus replicate-aware pseudobulk inference.
3. **Matrix-aware contract**: normalized expression for ranking paths, raw counts for DESeq2 pseudobulk.
4. **Direct DE figure exports**: marker dotplot and rank-gene summary where supported.
5. **Downstream-ready export**: processed AnnData, DE tables, report, structured result JSON, README, and notebook artifacts.

## Scope Boundary

Implemented methods:

1. `wilcoxon`
2. `t-test`
3. `logreg`
4. `mast` for R-backed hurdle-model DE
5. `deseq2_r` for pseudobulk DE

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | current direct input path |
| Demo | `--demo` | yes | bundled fallback |

### Input Expectations

- Accepted input: processed `.h5ad`
- `wilcoxon`, `t-test`, `logreg`, and `mast` expect `X = normalized_expression`
- `deseq2_r` expects raw counts, preferably in `layers["counts"]`, otherwise aligned raw counts in `adata.raw`, otherwise count-like `adata.X`
- All methods require a grouping column in `obs`
- If you want cluster markers, this skill usually comes **after `sc-clustering`**
- If you want replicate-aware treated-vs-control DE, this skill usually comes **after `sc-cell-annotation`** or another step that defines `celltype_key`

## Workflow

1. Load the AnnData object and inspect the matrix contract.
2. Preflight the statistical question: exploratory ranking vs replicate-aware condition DE.
3. Validate matrix state and required metadata for the requested method.
4. Run Scanpy ranking, MAST, or pseudobulk DESeq2.
5. Export tables, figures, `figure_data`, and `processed.h5ad`.
6. Record method metadata for downstream traceability.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-de/sc_de.py \
  --input <processed.h5ad> --groupby leiden --method wilcoxon --output <dir>

python skills/singlecell/scrna/sc-de/sc_de.py \
  --input <processed.h5ad> --groupby condition \
  --group1 treated --group2 control --method t-test --output <dir>

python skills/singlecell/scrna/sc-de/sc_de.py \
  --input <processed.h5ad> --groupby leiden --method logreg \
  --logreg-solver saga --output <dir>

python skills/singlecell/scrna/sc-de/sc_de.py \
  --input <processed.h5ad> --method deseq2_r \
  --groupby condition --group1 treated --group2 control \
  --sample-key sample_id --celltype-key cell_type \
  --pseudobulk-min-cells 10 --pseudobulk-min-counts 1000 --output <dir>
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | DE backend | `wilcoxon`, `t-test`, `logreg`, `mast`, or `deseq2_r` |
| `--groupby` | grouping column | core comparison axis |
| `--group1` / `--group2` | comparison levels | especially important for `mast` and `deseq2_r` |
| `--n-top-genes` | compact export size | ranking-output control |
| `--logreg-solver` | logistic-regression optimizer | `logreg` only |
| `--sample-key` | replicate/sample column | required by `deseq2_r` |
| `--celltype-key` | pseudobulk aggregation label | used by `deseq2_r` |
| `--pseudobulk-min-cells` | minimum cells per pseudobulk bin | `deseq2_r` only |
| `--pseudobulk-min-counts` | minimum counts per pseudobulk bin | `deseq2_r` only |
| `--padj-threshold` / `--log2fc-threshold` | figure summary thresholds | mostly affects exported volcano/summary figures |

## Algorithm / Methodology

### Exploratory ranking paths

Current OmicsClaw exploratory DE includes:

1. `wilcoxon`
2. `t-test`
3. `logreg`
4. `mast`

These paths answer the cluster-marker or group-ranking question on normalized expression from `adata.X`.

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
- `figure_data/manifest.json`
- `reproducibility/commands.sh`

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- exploratory methods:
  - `figures/marker_dotplot.png`
  - `figures/rank_genes_groups.png`
  - `figures/de_effect_summary.png`
  - `figures/de_group_summary.png`
- pseudobulk paths:
  - `figures/pseudobulk_group_summary.png`
  - per-celltype `*_volcano.png`
  - per-celltype `*_ma.png`

### What Users Should Inspect First

1. `report.md`
2. `tables/de_full.csv`
3. `tables/markers_top.csv`
4. `figures/de_group_summary.png` or pseudobulk summary figures
5. `processed.h5ad`

## Current Limitations

- `mast` requires an R environment with `MAST`, `SingleCellExperiment`, and `zellkonverter`.
- `deseq2_r` requires an R environment with `DESeq2`, `SingleCellExperiment`, and `zellkonverter`.
- This skill writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.

## Safety And Guardrails

- Distinguish exploratory marker-style DE from replicate-aware pseudobulk inference before running.
- If the user only has a base-preprocessed object and wants cluster markers, point them to `sc-clustering` first.
- If the user wants treated-vs-control inference without replicates, warn that exploratory DE is not replicate-aware.
- `mast` and `deseq2_r` are real public methods but require their R stacks up front in the current wrapper.
- Treat `sample_key` and `celltype_key` as part of the statistical design for `deseq2_r`, not as cosmetic metadata.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-de-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-de.md`.
