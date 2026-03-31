---
name: sc-ambient-removal
description: >-
  Remove ambient RNA contamination from droplet-based single-cell RNA-seq using
  a simple subtraction path, CellBender, or SoupX. The wrapper exposes only the
  parameters that are actually wired into the current implementation.
version: 0.5.0
author: OmicsClaw
license: MIT
tags: [singlecell, ambient, cellbender, soupx, qc]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--contamination"
      - "--expected-cells"
      - "--filtered-matrix-dir"
      - "--method"
      - "--raw-h5"
      - "--raw-matrix-dir"
    param_hints:
      simple:
        priority: "contamination"
        params: ["contamination"]
        defaults: {contamination: 0.05}
        requires: ["count_like_matrix_in_X", "scanpy"]
        tips:
          - "--method simple: Python fallback that subtracts a global ambient profile from the matrix."
          - "--contamination: Wrapper-level contamination fraction used directly in the subtraction formula."
      cellbender:
        priority: "raw_h5 -> expected_cells"
        params: ["raw_h5", "expected_cells"]
        defaults: {expected_cells: "input_n_obs"}
        requires: ["cellbender", "10x_raw_h5"]
        tips:
          - "--raw-h5: Required for the CellBender path."
          - "--expected-cells: Main CellBender size prior; defaults to the observed cell count when omitted."
      soupx:
        priority: "raw_matrix_dir -> filtered_matrix_dir"
        params: ["raw_matrix_dir", "filtered_matrix_dir"]
        defaults: {}
        requires: ["SoupX_ready_R_environment", "10x_raw_and_filtered_matrix_dirs"]
        tips:
          - "--method soupx: Requires both raw and filtered 10x matrix directories."
          - "If the required SoupX inputs are missing, OmicsClaw falls back to `simple`."
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
        package: cellbender
        bins: []
    trigger_keywords:
      - ambient RNA
      - ambient removal
      - cellbender
      - contamination
      - background RNA
---

# Single-Cell Ambient RNA Removal

## Why This Exists

- Without it: ambient transcripts from lysed cells bias downstream expression profiles.
- With it: corrected counts are easier to use for annotation, marker discovery, and DE.
- Why OmicsClaw: one wrapper exposes a fast Python fallback and two common method-specific entry paths.

## Scope Boundary

Implemented methods in the current wrapper:

1. `simple` - default Python subtraction path
2. `cellbender` - deep generative correction when `--raw-h5` is provided
3. `soupx` - R-backed 10x matrix correction when raw and filtered directories are provided

The wrapper does not currently expose the full upstream CellBender or SoupX parameter surface.

## Input Contract

- Accepted inputs: `.h5ad` or 10x-like inputs required by the selected method
- `simple`: needs an input AnnData matrix
- `cellbender`: needs `--raw-h5`
- `soupx`: needs both `--raw-matrix-dir` and `--filtered-matrix-dir`

## Workflow Summary

1. Load AnnData or demo data.
2. Validate the selected correction path.
3. Run the requested method or fall back when required inputs are absent.
4. Compare counts before and after correction.
5. Write `corrected.h5ad`, figures, `report.md`, and `result.json`.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --input <data.h5ad> --output <dir>

python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --method cellbender --raw-h5 <raw_feature_bc_matrix.h5> \
  --expected-cells 10000 --output <dir>

python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --input <filtered.h5ad> --method soupx \
  --raw-matrix-dir raw_feature_bc_matrix/ \
  --filtered-matrix-dir filtered_feature_bc_matrix/ \
  --output <dir>
```

## Output Contract

Successful runs write:

- `corrected.h5ad`
- `report.md`
- `result.json`
- `figures/counts_comparison.png`
- `figures/count_distribution.png`

## Current Limitations

- The wrapper does not yet emit the same README/notebook bundle as `sc-qc` or `sc-preprocessing`.
- `simple` is an OmicsClaw fallback, not an upstream CellBender/SoupX equivalent.
