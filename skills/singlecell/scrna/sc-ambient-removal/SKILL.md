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

## Core Capabilities

1. **Three entry paths**: lightweight subtraction, CellBender, and SoupX.
2. **Method-aware input contract**: raw `.h5` for CellBender, paired 10x directories for SoupX, AnnData for the simple path.
3. **Correction summary figures**: count-comparison and count-distribution plots after correction.
4. **Standard corrected export**: writes `corrected.h5ad`, `report.md`, `result.json`, and reproducibility artifacts.
5. **Honest fallback behavior**: when SoupX prerequisites are absent, the current wrapper can fall back to the simple method instead of pretending full SoupX execution happened.

## Scope Boundary

Implemented methods in the current wrapper:

1. `simple` - default Python subtraction path
2. `cellbender` - deep generative correction when `--raw-h5` is provided
3. `soupx` - R-backed 10x matrix correction when raw and filtered directories are provided

The wrapper does not currently expose the full upstream CellBender or SoupX parameter surface.

## Input Formats

| Format | Extension / form | Current wrapper support | Notes |
|--------|------------------|-------------------------|-------|
| AnnData | `.h5ad` | yes | used by the `simple` path |
| 10x raw HDF5 | `.h5` | yes | required by `cellbender` |
| 10x raw matrix directory | directory | yes | used with `--raw-matrix-dir` for `soupx` |
| 10x filtered matrix directory | directory | yes | used with `--filtered-matrix-dir` for `soupx` |
| Demo | `--demo` | yes | synthetic / bundled fallback path |

### Input Expectations

- `simple` expects a count-like matrix in `adata.X`.
- `cellbender` must receive a raw 10x `.h5` file from `cellranger count`; processed `.h5ad` is not enough for this path.
- `soupx` needs both `--raw-matrix-dir` and `--filtered-matrix-dir`.
- If the user only has a processed AnnData object, the current wrapper can only guarantee the `simple` path.

## Workflow

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

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | ambient-removal backend | `simple`, `cellbender`, or `soupx` |
| `--contamination` | wrapper-level contamination fraction | used only by `simple` |
| `--raw-h5` | raw 10x HDF5 input | required by `cellbender` |
| `--expected-cells` | CellBender size prior | defaults to observed cell count when omitted |
| `--raw-matrix-dir` | raw 10x matrix directory | used by `soupx` |
| `--filtered-matrix-dir` | filtered 10x matrix directory | used by `soupx` |

## Algorithm / Methodology

### `simple`

Current OmicsClaw `simple` ambient removal:

1. loads a count-like AnnData matrix
2. estimates a global ambient profile
3. subtracts contamination using the wrapper-level `contamination` fraction
4. clips corrected values back into a valid corrected count-like matrix

Important implementation note:

- this is an OmicsClaw fallback path, not an upstream CellBender or SoupX equivalent

### `cellbender`

Current OmicsClaw `cellbender` path:

1. requires a raw 10x `.h5`
2. passes `expected_cells` into the CellBender CLI
3. reimports the corrected matrix into the OmicsClaw output contract

Important implementation note:

- the wrapper exposes only a compact subset of CellBender controls today

### `soupx`

Current OmicsClaw `soupx` path:

1. requires paired raw and filtered 10x matrix directories
2. runs the shared R-backed SoupX bridge
3. writes corrected counts back into the exported AnnData

Important implementation note:

- if the required inputs are missing, the wrapper may fall back instead of silently faking SoupX completion

## Output Contract

Successful runs write:

- `corrected.h5ad`
- `report.md`
- `result.json`
- `figures/counts_comparison.png`
- `figures/count_distribution.png`

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/counts_comparison.png`
- `figures/count_distribution.png`

### What Users Should Inspect First

1. `report.md`
2. `figures/counts_comparison.png`
3. `figures/count_distribution.png`
4. `corrected.h5ad`

## Current Limitations

- The wrapper writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
- `simple` is an OmicsClaw fallback, not an upstream CellBender/SoupX equivalent.
