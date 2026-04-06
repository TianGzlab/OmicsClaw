---
name: sc-ambient-removal
description: >-
  Remove ambient RNA contamination from droplet-based single-cell RNA-seq using
  a simple subtraction path, CellBender, or SoupX. The wrapper exposes only the
  parameters that are actually wired into the current implementation.
version: 0.6.0
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
        requires: ["count_like_expression_in_layers_counts_or_raw_or_X", "scanpy"]
        tips:
          - "--method simple: Python fallback that subtracts a global ambient profile from the best available raw-count-like matrix."
          - "--contamination: Wrapper-level contamination fraction used directly in the subtraction formula after scaling by each barcode's library size."
      cellbender:
        priority: "raw_h5 -> expected_cells"
        params: ["raw_h5", "expected_cells"]
        defaults: {expected_cells: "input_n_obs_or_required_without_input"}
        requires: ["cellbender", "10x_raw_h5"]
        tips:
          - "--raw-h5: Required for the CellBender path."
          - "--expected-cells: Main CellBender size prior; strongly recommended and required when no separate --input is provided."
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
3. **Method-aware diagnostics**: shared-barcode comparison, count-distribution, and CellBender barcode-rank diagnostics when applicable.
4. **Dual output contract for CellBender**: preserves native CellBender matrix/log artifacts and also writes `corrected.h5ad` for downstream OmicsClaw skills.
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
| AnnData | `.h5ad` | yes | preferred input for `simple`; also usable as filtered reference for other paths |
| 10x raw HDF5 | `.h5` | yes | required by `cellbender`; can also be loaded directly when `--input` is omitted |
| 10x raw matrix directory | directory | yes | used with `--raw-matrix-dir` for `soupx` |
| 10x filtered matrix directory | directory | yes | used with `--filtered-matrix-dir` for `soupx`; can seed output AnnData when `--input` is omitted |
| Loom | `.loom` | yes | loaded through OmicsClaw single-cell smart loader |
| Delimited count matrix | `.csv`, `.tsv` | yes | loaded through OmicsClaw single-cell smart loader |
| Demo | `--demo` | yes | synthetic / bundled fallback path |

### Input Expectations

- `simple` accepts whichever raw-count-like source OmicsClaw can recover first from `adata.layers['counts']`, aligned `adata.raw`, or count-like `adata.X`.
- `cellbender` must receive a raw 10x `.h5` file from `cellranger count`; processed `.h5ad` is not enough for this path.
- `soupx` needs both `--raw-matrix-dir` and `--filtered-matrix-dir`.
- If `--input` is omitted, the wrapper can bootstrap from method-specific assets such as `--raw-h5` or `--filtered-matrix-dir`.
- If the user only has a processed AnnData object, the current wrapper can only guarantee the `simple` path.
- If the user drops in an arbitrary single-cell file and the matrix provenance is unclear, OmicsClaw will still try to load it, but may recommend `sc-standardize-input` first for more stable downstream behavior.

## Workflow

1. Load AnnData or demo data.
2. Validate the selected correction path.
3. Run the requested method or fall back when required inputs are absent.
4. Generate method-aware diagnostics, using shared barcodes for direct before/after comparison when needed.
5. Write `corrected.h5ad`, figures, `report.md`, `result.json`, and preserved method-specific artifacts.

## CLI Reference

```bash
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --input <data.h5ad> --output <dir>

python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --method cellbender --raw-h5 <raw_feature_bc_matrix.h5> \
  --expected-cells 10000 --output <dir>

python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --method soupx \
  --raw-matrix-dir raw_feature_bc_matrix/ \
  --filtered-matrix-dir filtered_feature_bc_matrix/ \
  --output <dir>

python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --input <unknown_singlecell_input> --method simple \
  --output <dir>
```

## Public Parameters

| Parameter | Role | Notes |
|-----------|------|-------|
| `--method` | ambient-removal backend | `simple`, `cellbender`, or `soupx` |
| `--contamination` | wrapper-level contamination fraction | used only by `simple` |
| `--raw-h5` | raw 10x HDF5 input | required by `cellbender` |
| `--expected-cells` | CellBender size prior | defaults to observed cell count when an input reference is available; require it explicitly when only `--raw-h5` is provided |
| `--raw-matrix-dir` | raw 10x matrix directory | used by `soupx` |
| `--filtered-matrix-dir` | filtered 10x matrix directory | used by `soupx` |

## Algorithm / Methodology

### `simple`

Current OmicsClaw `simple` ambient removal:

1. loads a count-like AnnData matrix
2. estimates a global ambient profile
3. subtracts contamination using the wrapper-level `contamination` fraction scaled by each barcode's library size
4. clips corrected values back into a valid corrected count-like matrix

Important implementation note:

- this is an OmicsClaw fallback path, not an upstream CellBender or SoupX equivalent

### `cellbender`

Current OmicsClaw `cellbender` path:

1. requires a raw 10x `.h5`
2. passes `expected_cells` into the CellBender CLI
3. preserves native CellBender matrix/log outputs under `cellbender_output/`
4. reimports the corrected filtered matrix into the OmicsClaw output contract as `corrected.h5ad`

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
- `figures/count_distribution.png`
- `figures/counts_comparison.png` when before/after barcodes can be aligned directly

Additional CellBender runs preserve upstream-style artifacts under `cellbender_output/`, such as:

- `cellbender_output/cellbender_output.h5`
- `cellbender_output/cellbender_output_filtered.h5`
- `cellbender_output/cellbender_output_posterior.h5` when produced
- `cellbender_output/cellbender_output_metrics.csv` when produced
- `cellbender_output/cellbender_output_cell_barcodes.csv` when produced
- `cellbender_output/cellbender_output.log` when produced

### Visualization Contract

The current wrapper writes direct figure outputs rather than a recipe-driven gallery:

- `figures/count_distribution.png`
- `figures/counts_comparison.png` for aligned shared barcodes
- `figures/barcode_rank.png` for CellBender runs

### What Users Should Inspect First

1. `report.md`
2. `cellbender_output/` native outputs when the method is `cellbender`
3. `figures/barcode_rank.png` or `figures/count_distribution.png`
4. `corrected.h5ad`

## Current Limitations

- The wrapper writes `README.md` and notebook-style reproducibility artifacts when notebook export dependencies are available.
- `simple` is an OmicsClaw fallback, not an upstream CellBender/SoupX equivalent.
- `corrected.h5ad` is a downstream convenience export, not CellBender's native primary file format.
- The wrapper will try to load many common single-cell formats through OmicsClaw's smart loader, but sophisticated methods still require their true raw 10x side inputs.

## Safety And Guardrails

- Explain both the requested method and the actually executed method when `soupx` falls back to `simple`.
- Do not present `simple` as scientifically equivalent to CellBender or SoupX.
- Enforce the real input contract: `cellbender` needs `--raw-h5`, and `soupx` needs both raw and filtered matrix directories.
- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-ambient-removal-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-ambient-removal.md`.
