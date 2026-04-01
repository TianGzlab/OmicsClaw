---
name: sc-doublet-detection
description: >-
  Detect putative doublets in single-cell RNA-seq data using Scrublet,
  DoubletFinder, or scDblFinder. The wrapper standardizes output columns and
  keeps the public parameter surface compact.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [singlecell, doublet, scrublet, doubletfinder, scdblfinder, qc]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--expected-doublet-rate"
      - "--method"
      - "--threshold"
    param_hints:
      scrublet:
        priority: "expected_doublet_rate -> threshold"
        params: ["expected_doublet_rate", "threshold"]
        defaults: {expected_doublet_rate: 0.06}
        requires: ["scrublet", "count_like_matrix_in_X"]
        tips:
          - "--method scrublet: Python-native default path."
          - "--threshold: Optional manual cutoff overriding Scrublet's automatic decision boundary."
      doubletfinder:
        priority: "expected_doublet_rate"
        params: ["expected_doublet_rate"]
        defaults: {expected_doublet_rate: 0.06}
        requires: ["R_doubletfinder_stack"]
        tips:
          - "--method doubletfinder: R-backed path."
          - "If the R runtime fails, the current wrapper falls back to `scdblfinder`."
      scdblfinder:
        priority: "expected_doublet_rate"
        params: ["expected_doublet_rate"]
        defaults: {expected_doublet_rate: 0.06}
        requires: ["R_scdblfinder_stack"]
        tips:
          - "--method scdblfinder: Fast R/Bioconductor path with the cleanest current wrapper contract."
    legacy_aliases: [sc-doublet]
    saves_h5ad: true
    requires_preprocessed: false
    requires:
      bins: [python3]
      env: []
      config: []
    emoji: "S"
    homepage: https://github.com/OmicsClaw/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scrublet
        bins: []
    trigger_keywords:
      - doublet detection
      - doublet removal
      - scrublet
      - doubletfinder
      - scdblfinder
---

# Single-Cell Doublet Detection

## Why This Exists

- Without it: artificial multiplets can form misleading intermediate clusters.
- With it: cells are annotated with standardized doublet scores and labels before downstream analysis.
- Why OmicsClaw: one wrapper normalizes three common entry paths into the same output columns.

## Scope Boundary

Implemented methods:

1. `scrublet` - Python-native default
2. `doubletfinder` - R-backed path
3. `scdblfinder` - R-backed path

The wrapper writes classification columns but does not automatically drop doublets from the AnnData object.

## Input Contract

- Accepted input: `.h5ad`
- Expected data state: count-like matrix in `X`
- Useful upstream step: run this before final clustering and annotation

## Workflow Summary

1. Load AnnData or demo data.
2. Run the selected detector.
3. Write `doublet_score`, `predicted_doublet`, and `doublet_classification` into `obs`.
4. Export figures, summary tables, and `processed.h5ad`.
5. Record the chosen method and thresholds in `result.json`.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py \
  --input <data.h5ad> --output <dir>

python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py \
  --input <data.h5ad> --method scdblfinder --output <dir>

python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py \
  --input <data.h5ad> --method scrublet \
  --expected-doublet-rate 0.08 --threshold 0.25 --output <dir>
```

## Output Contract

Successful runs write:

- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/doublet_histogram.png`
- `figures/umap_doublets.png` when a UMAP is available or can be computed
- `tables/summary.csv`

## Current Limitations

- The wrapper now writes README and notebook-style reproducibility artifacts when notebook export dependencies are available.
- `doubletfinder` can fall back to `scdblfinder` at runtime if the R path fails.
