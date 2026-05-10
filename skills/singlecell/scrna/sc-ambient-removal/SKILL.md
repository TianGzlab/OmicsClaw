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
| Cleaned AnnData | `processed.h5ad` | adds `obs["ambient_corrected"]`, `layers["ambient_subtracted"]` |
| Diagnostic figures | `figures/counts_comparison.png`, `figures/count_distribution.png`, `figures/barcode_rank.png` | always rendered |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Load filtered AnnData; optionally load raw matrix (SoupX requires both).
2. Validate `--contamination` is in (0, 1) and `--expected-cells` is positive when set.
3. Run the chosen `--method` against `METHOD_REGISTRY`.
4. If the requested backend is unavailable, fall back deterministically to `simple`.
5. Write the cleaned matrix into `layers["ambient_subtracted"]`; update `adata.X` to the corrected counts.
6. Render diagnostic figures + emit `report.md` + `result.json`.

## Gotchas

- **Unavailable backend silently falls back to `simple`.** `sc_ambient.py:207-208` logs `"Requested method '%s' is unavailable (...). Falling back to simple subtraction."` when CellBender is not installed or SoupX cannot reach R/rpy2.  After every non-`simple` run, confirm `result.json["summary"]["method_used"]` matches what you passed via `--method` — the flag is a request, not a guarantee.
- **`--contamination` is bounded to (0, 1).** `sc_ambient.py:134` raises `ValueError("--contamination must be between 0 and 1 (for example 0.05).")` outside that range.  Common typo: passing `5` instead of `0.05` produces a hard fail rather than a silent reinterpretation.
- **`--expected-cells` must be a positive integer.** `sc_ambient.py:136` raises `ValueError`.  Zero or negative values fail loudly here rather than producing a degenerate run.
- **SoupX requires both raw and filtered matrices.** `sc_ambient.py:125` raises `ValueError` when `--method soupx` runs without `--raw-matrix-dir` (or when the directory is missing).  CellBender uses just the filtered matrix; `simple` uses neither.

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
- `references/output_contract.md` — `obs` keys, `layers["ambient_subtracted"]` semantics
- Adjacent skills: `sc-doublet-detection` (parallel — multiplet barcodes, complementary contamination class), `sc-filter` (upstream — cell QC), `sc-preprocessing` (downstream — normalise/HVG/PCA on the cleaned counts)
