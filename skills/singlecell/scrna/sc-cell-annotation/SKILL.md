---
name: sc-cell-annotation
description: >-
  Annotate cell types from normalized scRNA-seq data using marker scoring,
  CellTypist, PopV-style reference mapping, lightweight KNNPredict-style
  mapping, SingleR, or scmap through shared Python/R backends.
version: 0.9.0
author: OmicsClaw
license: MIT
tags: [singlecell, annotation, celltypist, popv, knnpredict, singler, scmap]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--manual-map"
      - "--manual-map-file"
      - "--cluster-key"
      - "--method"
      - "--model"
      - "--reference"
      - "--celltypist-majority-voting"
      - "--no-celltypist-majority-voting"
    param_hints:
      manual:
        priority: "cluster_key -> manual_map/manual_map_file"
        params: ["cluster_key", "manual_map", "manual_map_file"]
        defaults: {cluster_key: auto}
        requires: ["cluster_labels_in_obs"]
        tips:
          - "--method manual: explicit relabeling from user-provided cluster mappings."
          - "--manual-map example: `0=T cell;1,2=Myeloid`."
      markers:
        priority: "cluster_key"
        params: ["cluster_key"]
        defaults: {cluster_key: auto}
        requires: ["normalized_expression", "cluster_labels_in_obs"]
        tips:
          - "--method markers: use when clusters already exist and you want a quick label proposal from known markers."
      celltypist:
        priority: "model -> celltypist_majority_voting"
        params: ["model", "celltypist_majority_voting"]
        defaults: {model: "Immune_All_Low", celltypist_majority_voting: false}
        requires: ["celltypist", "normalized_expression_matrix"]
        tips:
          - "--model: CellTypist model name or model file stem."
          - "--celltypist-majority-voting: optional neighborhood/cluster smoothing for CellTypist labels."
      popv:
        priority: "reference -> cluster_key"
        params: ["reference", "cluster_key"]
        defaults: {cluster_key: auto}
        requires: ["labeled_reference_h5ad", "normalized_expression_matrix"]
        tips:
          - "--method popv: official PopV path when possible, else lightweight reference mapping fallback."
      knnpredict:
        priority: "reference -> cluster_key"
        params: ["reference", "cluster_key"]
        defaults: {cluster_key: auto}
        requires: ["labeled_reference_h5ad", "normalized_expression_matrix"]
        tips:
          - "--method knnpredict: lightweight AnnData-first projection inspired by SCOP KNNPredict."
      singler:
        priority: "reference"
        params: ["reference"]
        defaults: {reference: "HPCA"}
        requires: ["R_SingleR_stack"]
        tips:
          - "--method singler: R SingleR path using celldex / ExperimentHub atlases or a labeled local H5AD reference."
      scmap:
        priority: "reference"
        params: ["reference"]
        defaults: {reference: "HPCA"}
        requires: ["R_scmap_stack"]
        tips:
          - "--method scmap: R scmap path using celldex / ExperimentHub atlases or a labeled local H5AD reference."
    legacy_aliases: [sc-annotate]
    saves_h5ad: true
    requires_preprocessed: true
---

# Single-Cell Cell Annotation

## Why This Exists

- Without it: users hand-label clusters inconsistently or trust opaque defaults.
- With it: annotation method, reference/model choice, label outputs, and figures are standardized.
- Why OmicsClaw: one wrapper unifies marker-based and reference-style annotation while preserving an AnnData-first workflow.

## Scope Boundary

Implemented methods:

1. `manual`
2. `markers`
3. `celltypist`
4. `popv`
5. `knnpredict`
6. `singler`
7. `scmap`

This skill annotates cells or clusters. It does not replace marker discovery or replicate-aware DE.

## Input Expectations

- Expected state: normalized expression in `adata.X`
- Typical upstream step: `sc-clustering`
- Typical downstream steps: `sc-markers`, `sc-de`, or interpretation/reporting
- Marker mode needs an existing cluster/label column; it will not auto-cluster anymore

## Public Parameters

- `--method`
- `--manual-map`
- `--manual-map-file`
- `--cluster-key`
- `--model`
- `--reference`
- `--celltypist-majority-voting`

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/embedding_cell_type.png`
- `figures/embedding_cluster_vs_cell_type.png`
- `figures/cluster_to_cell_type_heatmap.png`
- `figures/cell_type_counts.png`
- `figures/embedding_annotation_score.png` when scores are available
- `figures/manifest.json`
- `figure_data/manifest.json`
- `tables/annotation_summary.csv`
- `tables/cell_type_counts.csv`
- `tables/cluster_annotation_matrix.csv`
- `reproducibility/commands.sh`

## What Users Should Inspect First

1. `report.md`
2. `figures/embedding_cell_type.png`
3. `figures/embedding_cluster_vs_cell_type.png`
4. `tables/annotation_summary.csv`
5. `processed.h5ad`

## Guardrails

- Treat `method` and its corresponding `model` / `reference` / `cluster_key` as the key scientific choices.
- Use normalized expression for public annotation workflows.
- If CellTypist falls back to `markers`, report both requested and executed methods.
- If `singler` / `scmap` use celldex atlases, remember they may still fail in restricted-network or empty-cache environments even when R packages are installed.
