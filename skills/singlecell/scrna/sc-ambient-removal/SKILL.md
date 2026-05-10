---
name: sc-ambient-removal
description: Load when removing ambient RNA contamination from droplet-based scRNA-seq using a simple subtraction path, CellBender, or SoupX. Skip when the contamination is multiplet barcodes (use sc-doublet-detection) or before counts exist (use sc-count).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- ambient
- cellbender
- soupx
- contamination
requires:
- anndata
- numpy
- scipy
---

# sc-ambient-removal

## When to use

The user has filtered (or raw + filtered) droplet-based scRNA-seq counts
and suspects ambient RNA from cell-free droplets is inflating per-cell
expression — typical for 10X data with high droplet density.  Three
backends share the CLI: `simple` (a deterministic ambient-profile
subtraction, default), `cellbender` (Python, requires GPU for sensible
runtime), and `soupx` (R via rpy2; needs raw + filtered matrices).
Doublets are a different problem — use `sc-doublet-detection` for
multiplet barcodes.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Filtered single-cell AnnData | `.h5ad` | yes (unless `--demo`) |
| Raw matrix (SoupX) | 10X mtx dir via `--raw-matrix-dir` | only for `--method soupx` |

| Output | Path | Notes |
|---|---|---|
| Cleaned AnnData | `processed.h5ad` | `adata.X` overwritten with corrected counts; `layers["counts"]` preserves the pre-correction matrix; `uns["ambient_correction"]` (simple) / `uns["soupx"]` / `uns["cellbender"]` carries diagnostics |
| Diagnostic figures | `figures/counts_comparison.png`, `figures/count_distribution.png`, `figures/barcode_rank.png` | always rendered |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Load filtered AnnData; optionally load raw matrix (SoupX requires both).
2. Validate `--contamination` is in `[0, 1)` and `--expected-cells` is positive when set.
3. Run the chosen `--method` against `METHOD_REGISTRY`.
4. If the requested backend is unavailable, fall back deterministically to `simple`.
5. Stash the pre-correction matrix in `layers["counts"]` and overwrite `adata.X` with the corrected counts; record the run params in `uns["ambient_correction"|"soupx"|"cellbender"]`.
6. Render diagnostic figures + emit `report.md` + `result.json`.

## Gotchas

- **Unavailable backend silently falls back to `simple`.** `sc_ambient.py:207-208` logs `"Requested method '%s' is unavailable (...). Falling back to simple subtraction."` when CellBender is not installed or SoupX cannot reach R/rpy2.  After every non-`simple` run, confirm `result.json["summary"]["method_used"]` matches what you passed via `--method` — the flag is a request, not a guarantee.
- **`--contamination` is bounded to `[0, 1)` (left-inclusive).** `sc_ambient.py:133-134` checks `0 <= float(args.contamination) < 1` and raises `ValueError("--contamination must be between 0 and 1 (for example 0.05).")` otherwise.  `0` is allowed (degenerate no-op); `1` and `5.0` (the common typo for `0.05`) both fail loudly.
- **`--expected-cells` must be a positive integer.** `sc_ambient.py:136` raises `ValueError`.  Zero or negative values fail loudly here rather than producing a degenerate run.
- **SoupX without both `--raw-matrix-dir` and `--filtered-matrix-dir` silently falls back to `simple`.** `sc_ambient.py:851-857` logs `"SoupX requires --raw-matrix-dir and --filtered-matrix-dir. Falling back to simple subtraction."` and continues with the simple path.  `result.json` records the fallback in `summary["fallback_reason"]`; CellBender uses just the filtered matrix and the simple path uses neither.

## Key CLI

```bash
# Demo (simple subtraction)
python omicsclaw.py run sc-ambient-removal --demo --output /tmp/sc_ambient_demo

# CellBender on a 10X-filtered AnnData
python omicsclaw.py run sc-ambient-removal \
  --input filtered.h5ad --output results/ \
  --method cellbender --expected-cells 8000 --contamination 0.05

# SoupX with explicit raw + filtered matrices
python omicsclaw.py run sc-ambient-removal \
  --input filtered.h5ad --output results/ \
  --method soupx \
  --raw-matrix-dir cellranger_out/raw_feature_bc_matrix \
  --filtered-matrix-dir cellranger_out/filtered_feature_bc_matrix
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — when each backend wins, ambient profile derivation, R/Python tradeoffs
- `references/output_contract.md` — `layers["counts"]` (pre-correction) and `.X` (corrected) semantics, per-method `uns` diagnostics
- Adjacent skills: `sc-doublet-detection` (parallel — multiplet barcodes, complementary contamination class), `sc-filter` (upstream — cell QC), `sc-preprocessing` (downstream — normalise/HVG/PCA on the cleaned counts)
