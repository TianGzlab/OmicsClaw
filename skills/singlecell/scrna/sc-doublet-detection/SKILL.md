---
name: sc-doublet-detection
description: >-
  Annotate putative doublets in single-cell RNA-seq data using Scrublet,
  DoubletDetection, DoubletFinder, scDblFinder, or scds. The wrapper preserves
  the current AnnData matrix semantics, standardizes output columns in `obs`,
  and exports a reusable figure/table gallery.
version: 0.6.0
author: OmicsClaw
license: MIT
tags: [singlecell, doublet, scrublet, doubletdetection, doubletfinder, scdblfinder, scds, qc]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--expected-doublet-rate"
      - "--threshold"
      - "--batch-key"
      - "--doubletdetection-n-iters"
      - "--doubletdetection-standard-scaling"
      - "--no-doubletdetection-standard-scaling"
      - "--scds-mode"
    param_hints:
      scrublet:
        priority: "expected_doublet_rate -> batch_key -> threshold"
        params: ["expected_doublet_rate", "batch_key", "threshold"]
        defaults: {expected_doublet_rate: 0.06, threshold: auto}
        requires: ["scrublet", "raw_count_like_input"]
        tips:
          - "--method scrublet: default Python-native path."
          - "--batch-key: useful when captures/samples are mixed and Scrublet should run per batch."
          - "--threshold: manual cutoff overriding Scrublet's automatic call."
      doubletdetection:
        priority: "doubletdetection_n_iters"
        params: ["doubletdetection_n_iters", "doubletdetection_standard_scaling"]
        defaults: {doubletdetection_n_iters: 10, doubletdetection_standard_scaling: false}
        requires: ["doubletdetection", "raw_count_like_input"]
        tips:
          - "--method doubletdetection: consensus Python path borrowed from SCOP's method surface."
          - "The current wrapper records expected_doublet_rate for context, but the native DoubletDetection classifier does not use it directly."
      doubletfinder:
        priority: "expected_doublet_rate"
        params: ["expected_doublet_rate"]
        defaults: {expected_doublet_rate: 0.06}
        requires: ["R_doubletfinder_stack"]
        tips:
          - "--method doubletfinder: R-backed Seurat path."
          - "If the R runtime fails, the wrapper falls back to scDblFinder and reports both methods."
      scdblfinder:
        priority: "expected_doublet_rate"
        params: ["expected_doublet_rate"]
        defaults: {expected_doublet_rate: 0.06}
        requires: ["R_scdblfinder_stack"]
        tips:
          - "--method scdblfinder: fast Bioconductor path with a compact wrapper surface."
      scds:
        priority: "expected_doublet_rate -> scds_mode"
        params: ["expected_doublet_rate", "scds_mode"]
        defaults: {expected_doublet_rate: 0.06, scds_mode: cxds}
        requires: ["R_scds_stack"]
        tips:
          - "--method scds: Bioconductor score family from SCOP."
          - "--scds-mode chooses which score (`hybrid`, `cxds`, or `bcds`) becomes the public call surface."
          - "In the current environment, `cxds` is the safest first-pass default."
    legacy_aliases: [sc-doublet]
    saves_h5ad: true
    requires_preprocessed: false
---

# Single-Cell Doublet Detection

## Why This Exists

- Without it: artificial multiplets can masquerade as transitional or mixed cell states.
- With it: cells receive standardized doublet scores and labels before final clustering, annotation, or DE interpretation.
- Why OmicsClaw: one wrapper harmonizes multiple common backends into the same output columns and gallery layout.

## Scope Boundary

Implemented method families:

1. `scrublet`
2. `doubletdetection`
3. `doubletfinder`
4. `scdblfinder`
5. `scds` (`hybrid`, `cxds`, `bcds`)

This skill annotates doublets in `obs`. It does **not** silently remove cells.

## Input Expectations

- Preferred state: raw count-like input in `layers["counts"]`, aligned `adata.raw`, or count-like `adata.X`
- Typical stage: after QC review and before final clustering / annotation / DE interpretation
- Important nuance: if the object is already normalized, the wrapper still uses raw counts for calling and preserves the current `adata.X` semantics

## Public Parameters

Shared controls:

- `--method`
- `--expected-doublet-rate`

Method-specific controls:

- `scrublet`
  - `--batch-key`
  - `--threshold`
- `doubletdetection`
  - `--doubletdetection-n-iters`
  - `--doubletdetection-standard-scaling`
- `scds`
  - `--scds-mode`

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/doublet_score_distribution.png`
- `figures/doublet_call_summary.png`
- `figures/embedding_doublet_calls.png` when an embedding exists or a preview embedding can be computed
- `figures/embedding_doublet_scores.png` when an embedding exists or a preview embedding can be computed
- `figures/embedding_doublet_vs_group.png` when a useful batch/sample grouping is available
- `figures/doublet_score_by_group.png` when a useful grouping is available
- `tables/summary.csv`
- `tables/doublet_calls.csv`
- `figure_data/`

## What Users Should Inspect First

1. `report.md`
2. `figures/doublet_score_distribution.png`
3. `figures/embedding_doublet_calls.png`
4. `tables/doublet_calls.csv`
5. `processed.h5ad`

## Guardrails

- Explain whether `expected_doublet_rate` truly drives the selected backend.
- `threshold` only applies to `scrublet`.
- `batch_key` currently only affects `scrublet`.
- If `doubletfinder` falls back to `scdblfinder`, report both the requested and executed methods.
- After inspection, keep singlets and rerun preprocessing / clustering if the final downstream object should exclude doublets.

For concise execution guardrails, see `knowledge_base/knowhows/KH-sc-doublet-detection-guardrails.md`. For longer interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-doublet-detection.md`.
