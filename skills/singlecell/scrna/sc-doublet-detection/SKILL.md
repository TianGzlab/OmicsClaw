---
name: sc-doublet-detection
description: Load when annotating putative doublets in single-cell RNA-seq using Scrublet, DoubletDetection,
  DoubletFinder, scDblFinder, or scds. Skip when ambient RNA is the contamination problem (use sc-ambient-removal);
  before counts exist (use sc-fastq-qc).
tags:
- singlecell
- scrna
- doublet
- scrublet
- doubletfinder
- scdblfinder
---

# sc-doublet-detection

## When to use

The user has filtered (or at least QC'd) single-cell counts and wants
to flag putative doublet barcodes before clustering / annotation.
Five backends share one CLI: `scrublet` (default, Python), `doubletdetection`
(Python), `doubletfinder` (R), `scdblfinder` (R), `scds` (R).  Per-cell
scores + binary calls land in `obs`; this skill annotates, it does not
remove cells (filter downstream with `obs["predicted_doublet"]`).

## Use from a step

```python
doublets = load_skill("sc-doublet-detection")
adata = doublets.detect_doublets(read_input("filtered.h5ad"), random_state=0)
write_output(doublets.doublet_calls_table(adata), "tables/doublet_calls.csv")
write_output(doublets.doublet_score_figure(adata), "figures/doublet_scores.png")
write_output(adata, "intermediate/adata_doublets.h5ad")
```

Detection annotates the input in place; it never removes cells. To remove
the calls, pass the result to `sc-filter`. See `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `detect_doublets(adata, *, method: str='scrublet', expected_doublet_rate: float=0.06, threshold: float | None=None, batch_key: str | None=None, n_iters: int=10, standard_scaling: bool=False, scds_mode: str='cxds', random_state: int=0)`

Annotate doublets in place using counts from layers['counts'], raw or X.

No observations or features are removed. Pass the result to sc-filter
when doublets should be removed. A DoubletFinder failure may fall back to
scDblFinder; a failed scds mode may fall back to cxds. run_info records both.

:param adata: AnnData containing a count-like matrix.
:param method: scrublet, doubletdetection, doubletfinder, scdblfinder or scds.
:param expected_doublet_rate: Expected doublet fraction; default 0.06.
:param threshold: Scrublet score cutoff; None keeps its automatic calls.
:param batch_key: Scrublet batches in obs; None analyzes all cells together.
:param n_iters: DoubletDetection iterations; default 10.
:param standard_scaling: DoubletDetection standard scaling; default False.
:param scds_mode: cxds, bcds or hybrid; default cxds.
:param random_state: Seed passed to the selected backend; default 0.
:returns: The same AnnData with doublet_score, predicted_doublet and
    doublet_classification in obs, plus JSON diagnostics in uns.
:raises ValueError: A method, rate, threshold or batch column is invalid.
:raises ImportError: A Python backend is missing; use install_skill_deps.
:raises RuntimeError: An R method and any documented fallback fail.

### `run_info(adata, *, keep: bool=True) -> dict`

Read doublet method diagnostics from adata.uns.

:param adata: AnnData annotated by detect_doublets.
:param keep: False removes the JSON diagnostics after reading; default True.
:returns: Method, counts, matrix source and any fallback details.

### `doublet_calls_table(adata, *, groupby: str | None=None) -> pd.DataFrame`

Return per-cell scores and calls in observation order.

:param adata: AnnData annotated by detect_doublets.
:param groupby: Optional obs column to include in the table.
:returns: A DataFrame with cell_id, scores, calls and classification.

### `doublet_summary(adata) -> pd.DataFrame`

Return singlet and doublet counts and percentages from obs calls.

:param adata: AnnData with predicted_doublet in obs.
:returns: A DataFrame with one row per classification.

### `group_summary_table(adata, *, groupby: str) -> pd.DataFrame`

Summarize doublet counts and scores for an obs grouping column.

:param adata: AnnData annotated by detect_doublets.
:param groupby: Existing obs column defining the groups.
:returns: A DataFrame with counts, median and mean scores, and rates.
:raises ValueError: The grouping column is missing.

### `doublet_score_figure(adata)`

Plot the doublet score distribution and return the Figure.

:param adata: AnnData with doublet_score in obs.
:returns: A matplotlib Figure; the caller saves it with write_output.

<!-- api:end -->

## Methods and parameters

- `method="scrublet"` and `expected_doublet_rate=0.06` retain the CLI defaults.
  Set the rate from loading density and the experimental design.
- `threshold=None` retains Scrublet's automatic calls; a numeric threshold
  applies only to Scrublet. `batch_key` runs Scrublet by that `obs` column;
  it does not make the other backends batch-aware.
- DoubletDetection retains `n_iters=10` and `standard_scaling=False`.
- R backends use `Rscript` and temporary gene-by-cell MTX plus CSV metadata;
  they do not need a Python environment inside R. DoubletFinder requires
  Seurat, DoubletFinder and Matrix; scDblFinder/scds require their matching
  package, SingleCellExperiment and Matrix.
- `random_state=0` now reaches every backend, including Scrublet and R.
  Previously the CLI ignored this parameter for Scrublet; scDblFinder used
  a fixed R seed of 42. Missing Python packages raise an import error.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`

**Outputs**

- `tables/doublet_calls.csv`
- `tables/summary.csv`
- `tables/group_summary.csv` when a comparison group is available
- `figures/doublet_score_distribution.png`; embedding plots when an embedding is available
- `figure_data/` and its manifest, for the generated plots
- `figures/r_enhanced/` only for successful `--r-enhanced` renders
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `doublet_score`, `predicted_doublet`, `doublet_classification`

## Flow

1. Load AnnData; resolve `--method` against the `METHOD_REGISTRY`.
2. Run the chosen backend on the selected count-like matrix.
3. DoubletFinder may fall back to scDblFinder; a failed scds mode may fall back to cxds. Other failures propagate.
4. Apply the chosen `--threshold` (or method default) to score → call.
5. Write `obs["predicted_doublet"]` + `obs["doublet_score"]`; emit tables and the score-distribution figure.
6. Save `processed.h5ad` + `report.md` + `result.json`.

## Gotchas

- Check `run_info(adata)["executed_method"]`, `fallback_reason` and, for scds,
  `executed_scds_mode`. The CLI mirrors these diagnostics in `result.json["summary"]`.
- **No cells are removed.** This skill annotates barcodes; downstream filtering on `obs["predicted_doublet"]` is the user's responsibility.  If `sc-filter` was already run, doublets re-introduce themselves to the cluster graph if not filtered after this step.
- `tables/group_summary.csv` requires a comparison column: `--batch-key`
  takes precedence over an available annotation or cluster column.
- **Embedding pre-flight is non-fatal.** `sc_doublet.py` logs `"Preview embedding computation failed"` and continues; the score-distribution figure still renders without the embedding overlay.  When the figure looks sparse vs documented examples, check the warning log before assuming a bug.
- **Unsupported method → hard fail.** `sc_doublet.py` raises `ValueError("Unsupported method: ...")` for typos like `--method scrubblet`.

## Key CLI

```bash
# Demo (Scrublet)
python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py --demo --output /tmp/sc_doublet_demo

# Default Scrublet, with batch-aware grouping
python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py \
  --input filtered.h5ad --output results/ --batch-key sample_id

# scDblFinder with a custom expected rate
python skills/singlecell/scrna/sc-doublet-detection/sc_doublet.py \
  --input filtered.h5ad --output results/ \
  --method scdblfinder --expected-doublet-rate 0.1 --random-state 0
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — when each backend wins, R vs Python tradeoffs
- `references/output_contract.md` — `obs` keys added + table schemas
- Adjacent skills: `sc-ambient-removal` (parallel — fixes ambient RNA, complementary to doublet removal), `sc-filter` (upstream — typically run before this), `sc-clustering` (downstream — filter doublets out before clustering)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `doubletdetection`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `scrublet`, `seaborn`
