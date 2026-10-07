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
runtime), and `soupx` (Rscript; needs raw + filtered matrices).
Doublets are a different problem — use `sc-doublet-detection` for
multiplet barcodes.

## Use from a step

```python
ambient = load_skill("sc-ambient-removal")
adata = ambient.remove_ambient(read_input("counts.h5ad"), contamination=0.05)
write_output(ambient.correction_summary(adata), "tables/correction_summary.csv")
write_output(ambient.correction_figure(adata), "figures/counts_comparison.png")
write_output(adata, "intermediate/adata_corrected.h5ad")
```

With raw droplets, use `remove_ambient_soupx(filtered, raw=raw_droplets)`.
CellBender remains CLI-only because it uses an external process and files.
The simple-method example is in `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `remove_ambient(adata, *, contamination: float=0.05)`

Subtract a mean ambient profile from count-like expression in place.

Select layers['counts'], aligned raw or X; retain that matrix in
layers['counts'] and replace X with nonnegative corrected values. The
mean cell profile is only an approximation when empty droplets are absent.

:param adata: AnnData with a count-like expression matrix.
:param contamination: Fraction to subtract before clipping at zero, in [0, 1).
    Default 0.05, matching the CLI.
:returns: The same AnnData; run_info reports the matrix source and reduction.
:raises ValueError: No count-like matrix exists or contamination is invalid.

### `remove_ambient_soupx(adata, *, raw)`

Return SoupX-corrected cells, using raw droplet counts to estimate ambient RNA.

Both objects select counts from layers['counts'], aligned raw or X and
exchange temporary 10x matrices with R. This backend does not expose a
seed through its wrapper; results vary between runs. Errors propagate.

:param adata: AnnData containing the filtered cells.
:param raw: AnnData containing raw droplets, with matching feature names.
:returns: A new AnnData aligned to SoupX's retained cells and genes, with
    original counts in layers['counts'] and corrected X.
:raises RuntimeError: R, Seurat or SoupX is unavailable, or the method fails.
:raises ValueError: Counts are missing or the result cannot be aligned.

### `run_info(adata, *, keep: bool=True) -> dict`

Read JSON correction diagnostics from adata.uns.

:param adata: AnnData returned by a correction function.
:param keep: False removes the diagnostics after reading; default True.
:returns: Matrix source, method and before/after count summaries.

### `correction_summary(adata) -> pd.DataFrame`

Return the recorded count reduction as a one-row table.

:param adata: AnnData returned by a correction function.
:returns: Mean counts, reduction_pct, contamination_estimate and method.

### `counts_comparison_table(adata) -> pd.DataFrame`

Compare per-cell original counts in layers['counts'] with corrected X.

:param adata: AnnData returned by a correction function.
:returns: cell_id, counts_before and counts_after in observation order.

### `ambient_profile_table(adata) -> pd.DataFrame`

Return the mean original-count profile used by simple subtraction.

:param adata: Corrected AnnData with original counts in layers['counts'].
:returns: gene and fraction columns. This is not SoupX's estimated profile.

### `correction_figure(adata)`

Plot original versus corrected counts per cell and return the Figure.

:param adata: AnnData returned by a correction function.
:returns: A matplotlib Figure for write_output.

<!-- api:end -->

## Methods and parameters

`remove_ambient` selects counts from `layers["counts"]`, aligned `raw`, then
`X`, saves them in `layers["counts"]` and replaces `X` in place. The
`contamination=0.05` default retains the CLI's fixed subtraction fraction;
it is not an estimated biological contamination rate. The profile is the
mean across input cells, an approximation when no empty droplets exist.
This path is deterministic and needs no optional backend.

`remove_ambient_soupx` requires R, Seurat and SoupX. It exchanges compressed
10x matrices in a temporary directory and returns a new, aligned AnnData.
Its wrapper exposes no seed, so results may vary. Unlike the compatibility
CLI, the API propagates backend errors; it does not fall back to simple
subtraction. `run_info` records the method, count source and reduction.

## Inputs & Outputs

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: scrna
- File types: `.h5ad`, `.h5`, `.loom`, `.csv`, `.tsv`

**Outputs**

- `figures/barcode_rank.png`
- `figures/count_distribution.png`
- `figures/counts_comparison.png`
- `figure_data/` and its manifest, including correction summary and gene expression
- `figures/r_enhanced/` only for successful `--r-enhanced` renders
- `cellbender_output/` only when CellBender runs; files depend on its backend output
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

- The CLI can fall back to `simple` when a backend or its inputs are missing.
  Check `result.json["summary"]["executed_method"]` and `fallback_reason`.
  The SoupX API instead raises on failure.
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
  --method cellbender --raw-h5 raw_feature_bc_matrix.h5 --expected-cells 8000

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
