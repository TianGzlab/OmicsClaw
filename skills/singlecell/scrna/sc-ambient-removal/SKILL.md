---
name: sc-ambient-removal
description: Load when removing ambient RNA contamination from droplet-based scRNA-seq using a simple
  subtraction path, CellBender, or SoupX. Skip when the contamination is multiplet barcodes (use sc-doublet-detection);
  before counts exist (use sc-count).
trigger: ambient RNA, ambient removal, cellbender, contamination, background RNA
tags:
- singlecell
- scrna
- ambient
- cellbender
- soupx
- contamination
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

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: scrna
- File types: `.h5ad`, `.h5`, `.loom`, `.csv`, `.tsv`

**Outputs**

- `tables/cell_metadata.csv`
- `tables/cellbender_output_cell_barcodes.csv`
- `tables/cellbender_output_metrics.csv`
- `tables/cells.csv`
- `tables/corrected_counts.csv`
- `tables/correction_summary.csv`
- `tables/gene_expression.csv`
- `tables/genes.csv`
- `figures/barcode_rank.png`
- `figures/count_distribution.png`
- `figures/counts_comparison.png`
- `figures/r_ambient_violin.png`
- `README.md`
- `analysis_summary.txt`
- `cellbender_output_report.html`
- `contamination.json`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `layers`: `counts`; `uns`: `ambient_correction`, `soupx`, `cellbender`

## Flow

1. Load filtered AnnData; optionally load raw matrix (SoupX requires both).
2. Validate `--contamination` is in `[0, 1)` and `--expected-cells` is positive when set.
3. Run the chosen `--method` against `METHOD_REGISTRY`.
4. If the requested backend is unavailable, fall back deterministically to `simple`.
5. Stash the pre-correction matrix in `layers["counts"]` and overwrite `adata.X` with the corrected counts; record the run params in `uns["ambient_correction"|"soupx"|"cellbender"]`.
6. Render diagnostic figures + emit `report.md` + `result.json`.

## Gotchas

- **Unavailable backend silently falls back to `simple`.** `sc_ambient.py` logs `"Requested method '%s' is unavailable (...). Falling back to simple subtraction."` when CellBender is not installed or SoupX cannot reach R/rpy2.  After every non-`simple` run, confirm `result.json["summary"]["method_used"]` matches what you passed via `--method` — the flag is a request, not a guarantee.
- **`--contamination` is bounded to `[0, 1)` (left-inclusive).** `sc_ambient.py` checks `0 <= float(args.contamination) < 1` and raises `ValueError("--contamination must be between 0 and 1 (for example 0.05).")` otherwise.  `0` is allowed (degenerate no-op); `1` and `5.0` (the common typo for `0.05`) both fail loudly.
- **`--expected-cells` must be a positive integer.** `sc_ambient.py` raises `ValueError`.  Zero or negative values fail loudly here rather than producing a degenerate run.
- **SoupX without both `--raw-matrix-dir` and `--filtered-matrix-dir` silently falls back to `simple`.** `sc_ambient.py` logs `"SoupX requires --raw-matrix-dir and --filtered-matrix-dir. Falling back to simple subtraction."` and continues with the simple path.  `result.json` records the fallback in `summary["fallback_reason"]`; CellBender uses just the filtered matrix and the simple path uses neither.

## Key CLI

```bash
# Demo (simple subtraction)
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py --demo --output /tmp/sc_ambient_demo

# CellBender on a 10X-filtered AnnData
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
  --input filtered.h5ad --output results/ \
  --method cellbender --expected-cells 8000 --contamination 0.05

# SoupX with explicit raw + filtered matrices
python skills/singlecell/scrna/sc-ambient-removal/sc_ambient.py \
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

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cellbender`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `torch`
