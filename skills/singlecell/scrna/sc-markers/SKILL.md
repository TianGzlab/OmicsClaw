---
name: sc-markers
description: >-
  Rank cluster marker genes from normalized single-cell AnnData using Scanpy-backed
  Wilcoxon, t-test, or logistic-regression methods. The wrapper standardizes
  outputs for downstream annotation and review.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [singlecell, markers, cluster-markers, annotation, differential-expression]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--groupby"
      - "--method"
      - "--n-genes"
      - "--n-top"
      - "--min-in-group-fraction"
      - "--min-fold-change"
      - "--max-out-group-fraction"
    param_hints:
      wilcoxon:
        priority: "groupby -> n_genes -> n_top"
        params: ["groupby", "n_genes", "n_top", "min_in_group_fraction", "min_fold_change", "max_out_group_fraction"]
        defaults: {n_genes: all, n_top: 10, min_in_group_fraction: 0.25, min_fold_change: 0.25, max_out_group_fraction: 0.5}
        requires: ["normalized_expression", "group_labels_in_obs"]
        tips:
          - "--method wilcoxon: safest first-pass default for cluster marker ranking."
      t-test:
        priority: "groupby -> n_genes -> n_top"
        params: ["groupby", "n_genes", "n_top", "min_in_group_fraction", "min_fold_change", "max_out_group_fraction"]
        defaults: {n_genes: all, n_top: 10, min_in_group_fraction: 0.25, min_fold_change: 0.25, max_out_group_fraction: 0.5}
        requires: ["normalized_expression", "group_labels_in_obs"]
        tips:
          - "--method t-test: parametric alternative when users want a simple mean-shift test."
      logreg:
        priority: "groupby -> n_genes -> n_top"
        params: ["groupby", "n_genes", "n_top", "min_in_group_fraction", "min_fold_change", "max_out_group_fraction"]
        defaults: {n_genes: all, n_top: 10, min_in_group_fraction: 0.25, min_fold_change: 0.25, max_out_group_fraction: 0.5}
        requires: ["normalized_expression", "group_labels_in_obs"]
        tips:
          - "--method logreg: classification-style ranking for discriminative genes."
    saves_h5ad: true
    requires_preprocessed: true
---

# Single-Cell Markers

## Why This Exists

- Without it: users jump straight from clusters to labels without a stable marker evidence layer.
- With it: OmicsClaw exports cluster-level marker tables, summary figures, and a downstream-ready `processed.h5ad`.
- Why OmicsClaw: it keeps marker ranking separate from replicate-aware condition DE.

## Scope Boundary

Implemented methods:

1. `wilcoxon`
2. `t-test`
3. `logreg`

This skill is for cluster or label marker ranking. For treated-vs-control or replicate-aware DE, use `sc-de`.

## Input Expectations

- Expected state: normalized expression in `adata.X`
- Typical upstream step: `sc-clustering`
- Typical downstream step: `sc-cell-annotation`
- Required metadata: an existing grouping column such as `leiden`, `louvain`, or `cell_type`

## Public Parameters

- `--groupby`
- `--method`
- `--n-genes`
- `--n-top`
- `--min-in-group-fraction`
- `--min-fold-change`
- `--max-out-group-fraction`

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/markers_heatmap.png`
- `figures/markers_dotplot.png`
- `figures/marker_effect_summary.png`
- `figures/marker_cluster_summary.png`
- `figures/marker_fraction_scatter.png` when fraction statistics are available
- `tables/markers_all.csv`
- `tables/markers_top.csv`
- `tables/cluster_summary.csv`
- `figure_data/`

## What Users Should Inspect First

1. `report.md`
2. `tables/markers_top.csv`
3. `figures/markers_dotplot.png`
4. `figures/marker_effect_summary.png`
5. `processed.h5ad`

## Guardrails

- Treat `groupby` as the main scientific parameter.
- Do not present cluster markers as replicate-aware condition DE.
- Use normalized expression, not raw counts, for the public marker workflow.
- After marker review, the usual next step is `sc-cell-annotation`.

For concise execution rules, see `knowledge_base/knowhows/KH-sc-markers-guardrails.md`. For longer interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-markers.md`.
