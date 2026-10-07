---
name: sc-filter
description: Load when removing low-quality cells and lowly-detected genes from a single-cell AnnData
  using QC-derived thresholds or tissue presets. Skip when the full normalize→HVG→PCA→cluster pipeline
  (use sc-preprocessing); reads are still raw FASTQ (use sc-fastq-qc).
trigger: filter cells, cell filtering, gene filtering, remove low quality, qc filtering, tissue-specific thresholds
tags:
- singlecell
- scrna
- filter
- qc
- mitochondrial
---

# sc-filter

## When to use

The user has reviewed `sc-qc` output and now wants to actually drop
low-quality cells and lowly-detected genes — by per-cell thresholds
(`--min-genes`, `--max-genes`, `--max-mt-percent`, `--min-counts`,
`--max-counts`, `--min-cells`) or tissue-specific presets (`--tissue
brain` / `pbmc` / etc.).  This skill removes cells; it does not
normalise, cluster, or annotate.

## Use from a step

```python
filtering = load_skill("sc-filter")
before = read_input("results/01_qc/intermediate/adata_qc.h5ad")
after = filtering.filter_cells(before, tissue="pbmc")
write_output(filtering.filter_summary(after), "tables/filter_summary.csv")
write_output(filtering.filter_stats_table(after), "tables/filter_stats.csv")
write_output(after, "intermediate/adata_filtered.h5ad")
```

Run doublet detection before filtering when doublets should be removed.
In the next preprocessing step, call
`preprocess(after, apply_filters=False)` to keep these cells and genes.
A complete demo step is in `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `filter_cells(adata, *, min_genes: int=200, max_genes: int | None=None, min_counts: int | None=None, max_counts: int | None=None, max_mt_percent: float | None=20.0, min_cells: int=3, tissue: str | None=None, remove_doublets: bool=True, doublet_score_threshold: float=0.25)`

Return a filtered copy of an AnnData, with counts and matrix contracts.

Existing QC columns are reused. Otherwise counts are selected from the
input's counts layer, raw snapshot or X and missing QC metrics are computed.
A normalized X with existing QC metrics is preserved. Doublet removal reads
existing obs columns; it does not run doublet detection.

:param min_genes: Minimum detected genes per cell. Default 200.
:param max_genes: Maximum detected genes per cell; None leaves it uncapped.
:param min_counts: Minimum counts per cell; None disables this threshold.
:param max_counts: Maximum counts per cell; None disables this threshold.
:param max_mt_percent: Maximum mitochondrial percentage. Default 20.0;
    None disables the threshold.
:param min_cells: Minimum retained cells expressing a gene. Default 3.
:param tissue: Preset from tissue_presets(); overrides min_genes, max_genes
    and max_mt_percent. None uses the supplied thresholds.
:param remove_doublets: Drop cells marked by predicted_doublet, or by
    doublet_score when the boolean column is absent. Default True.
:param doublet_score_threshold: Score cutoff for the score-only case. Default 0.25.
:returns: A new AnnData with retained cells and genes; run_info records
    effective thresholds, the count source and the filtering summary.
:raises ValueError: Input requiring QC metrics has no count-like matrix.

### `run_info(adata, *, keep: bool=True) -> dict`

Read the filtering record from the returned AnnData.

:param keep: False removes the record from uns; default True keeps it.
:returns: summary, effective_params, input_contract and matrix_contract;
    an empty dict when filter_cells has not run. outliers_flagged counts
    existing outlier flags, which do not themselves remove cells.

### `filter_summary(adata) -> pd.DataFrame`

Return retention counts and effective thresholds as metric/value rows.

:param adata: The result of filter_cells.
:returns: A DataFrame matching the CLI's tables/filter_summary.csv.

### `filter_stats_table(adata) -> pd.DataFrame`

Return metric/value rows for threshold removals and existing outlier flags.

Threshold counts can overlap. outliers_flagged is a count of flags, not
removals. doublets_removed counts doublets remaining after QC thresholds.

### `retention_table(adata) -> pd.DataFrame`

Return Cells and Genes rows with before/after counts from filter_cells.

### `filter_state_table(before, after) -> pd.DataFrame`

Return QC metrics and Retained/Removed labels for every input cell.

Missing QC columns are calculated on a copy using filter_cells' input
preparation. The index contains the original cell names.

### `tissue_presets() -> dict`

Return copies of the shared QC presets, including their descriptions.

Each preset has min_genes, max_genes and max_mt (a percentage). These
replace the corresponding filter_cells thresholds when tissue is set.

### `filter_figure(before, after)`

Return a matplotlib Figure comparing cell and gene counts before and after filtering.

<!-- api:end -->

## Methods and parameters

`filter_cells` applies thresholds to cells, removes existing doublet calls,
then drops genes expressed in too few retained cells.

- `min_genes=200` and `min_cells=3` follow the existing OmicsClaw CLI defaults.
- `max_mt_percent=20.0` is the existing permissive ceiling. Choose the threshold
  from the QC distribution and record the reason in the step.
- `max_genes`, `min_counts` and `max_counts` default to `None`, disabling those limits.
- `tissue=None` uses the supplied thresholds. `tissue_presets()` returns the
  OmicsClaw heuristics: PBMC uses 200 to 2,500 genes and at most 5% MT counts.
- `remove_doublets=True` uses `predicted_doublet` first; if only `doublet_score`
  exists, the existing default cutoff is 0.25. Without either column it does
  no doublet filtering.

## Gotchas

- `run_info(after)["effective_params"]` records the thresholds after a tissue
  preset overrides `min_genes`, `max_genes` and `max_mt_percent`. To set these
  independently, leave `tissue=None`; editing documentation does not change a preset.
- `run_info(after)["summary"]["input_preparation"]` identifies the count source.
  QC columns already in `obs` are reused, including on normalized inputs; check
  how they were computed before applying count and MT thresholds.
- `filter_stats_table(after)` counts overlapping threshold failures. Its rows
  need not sum to the number removed. `outliers_flagged` counts pre-existing
  outlier flags; flags alone do not remove cells.
- `_api.py:53` (`filter_cells`) needs `pct_counts_mt` when MT filtering is enabled.
  If no mitochondrial features matched and this column is absent, inspect the
  gene names or explicitly disable that threshold with `max_mt_percent=None`.
- `tissue_presets()` has no lung preset. The legacy CLI accepts `--tissue lung`
  but the shared helper uses the `default` preset and logs a warning.

## Inputs and outputs

The functions accept AnnData. `filter_cells` reads counts and QC columns,
returns a new object with retained cells and genes, preserves a normalized X
when existing QC metrics permit it, and stores the run record in `uns`.
The summary functions return DataFrames; `filter_figure` returns a matplotlib
Figure. Use `write_output` for files.

The CLI writes `processed.h5ad`, `report.md`, `result.json`, three tables
(`filter_stats.csv`, `filter_summary.csv`, `retention_summary.csv`), and its
plot data under `figure_data/`. The figure and optional R-output inventory is
in `references/output_contract.md`.

## Key CLI

```bash
# Demo
python skills/singlecell/scrna/sc-filter/sc_filter.py --demo --output /tmp/sc_filter_demo

# Threshold-based (typical PBMC defaults)
python skills/singlecell/scrna/sc-filter/sc_filter.py \
  --input qc_output.h5ad --output results/ \
  --min-genes 200 --max-mt-percent 20 --min-cells 3

# Tissue preset (overrides matching CLI flags)
python skills/singlecell/scrna/sc-filter/sc_filter.py \
  --input qc_output.h5ad --output results/ --tissue pbmc
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — tissue preset definitions, threshold semantics
- `references/output_contract.md` — `processed.h5ad` + table schemas
- Adjacent skills: `sc-qc` supplies metrics; `sc-doublet-detection` supplies
  doublet calls; `sc-preprocessing` normalises the filtered AnnData with
  `apply_filters=False`.

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
