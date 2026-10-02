---
name: sc-qc
description: Load when computing per-cell QC metrics (n_genes, total counts, mt%, ribo%) on a single-cell
  AnnData before filtering. Skip when reads are still raw FASTQ (use sc-fastq-qc); you want to filter
  cells now (use sc-filter).
trigger: scRNA QC, single-cell QC, quality control, mitochondrial percentage, ribosomal percentage, QC violin, QC scatter, n genes per cell
tags:
- singlecell
- scrna
- qc
- mitochondrial
- ribosomal
---

# sc-qc

## When to use

The user has a single-cell AnnData (post-counting / post-standardisation)
and wants to *review* cell quality — counts, detected genes, mitochondrial
percentage, ribosomal percentage — before any filtering.  This skill
**reports**, it does not remove cells.  Use `sc-filter` to actually drop
cells based on these metrics.

## Use from a step

```python
qc = load_skill("sc-qc")
adata = qc.calculate_qc(read_input("data/pbmc.h5ad"), species="human")
write_output(qc.qc_summary(adata), "tables/qc_metrics_summary.csv")
write_output(qc.qc_figure(adata), "figures/qc_histograms.png")
write_output(adata, "intermediate/adata_qc.h5ad")
```

A complete step that runs on demo data: `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `calculate_qc(adata, *, species: str='human', calculate_ribo: bool=True)`

Bring the input into the OmicsClaw scRNA contract and add per-cell QC metrics to ``obs``.

The count-like matrix becomes ``X`` and ``layers['counts']``, ``raw`` keeps a
counts snapshot, and gene names are made unique. Then scanpy's
``calculate_qc_metrics`` adds ``n_genes_by_counts``, ``total_counts``,
``pct_counts_mt`` and ``pct_counts_ribo`` (when the gene prefixes match), plus
``log10_total_counts`` and ``log10_n_genes_by_counts``; ``var`` gets ``mt`` and
``ribo`` flags. How the input was read is recorded for :func:`run_info`.

:param species: ``"human"`` (``MT-``, ``RPS``/``RPL`` prefixes) or ``"mouse"``
    (``mt-``, ``Rps``/``Rpl``). Default ``"human"``, the CLI default. Set it to the
    organism of the data: with the wrong one no mitochondrial gene matches and
    ``pct_counts_mt`` is not computed at all.
:param calculate_ribo: Also compute ``pct_counts_ribo``. Default ``True``, as the CLI does.
:returns: A new AnnData (the standardized copy), with the metrics in ``obs``.
:raises ValueError: no count-like matrix can be found in ``X``, ``layers`` or ``raw``.

### `run_info(adata, *, keep: bool=True) -> dict`

What :func:`calculate_qc` recorded about the input it prepared.

Keys: ``species``, ``calculate_ribo``, ``expression_source`` (the matrix used
as counts), ``gene_name_source``, ``warnings``, ``input_contract``,
``matrix_contract`` and ``qc_obs_columns``.

:param keep: Leave the record in ``adata.uns``; ``False`` removes it.
:returns: The record, or an empty dict when ``calculate_qc`` has not run on *adata*.

### `qc_summary(adata) -> pd.DataFrame`

One row per QC metric with ``min``, ``max``, ``mean``, ``median``, ``std``, ``q25`` and ``q75``.

:returns: Columns ``metric``, ``min``, ``max``, ``mean``, ``median``, ``std``, ``q25``,
    ``q75``, for the metrics :func:`calculate_qc` added.

### `qc_metrics_table(adata) -> pd.DataFrame`

The per-cell QC metrics, one row per cell.

:returns: Column ``cell_id`` followed by the QC metrics present in ``obs``.

### `highest_expressed_genes(adata, *, n_top: int=20) -> pd.DataFrame`

The genes with the highest mean expression in ``X``.

A few genes dominating the counts (mitochondrial, ribosomal, MALAT1) point
to stressed cells or ambient RNA.

:param n_top: How many genes to return. Default 20, the CLI's table length.
:returns: Columns ``gene`` and ``mean_expression``, highest first.

### `barcode_rank_table(adata) -> pd.DataFrame`

Library sizes ranked from largest to smallest, for a barcode-rank (knee) plot.

:returns: Columns ``rank``, ``total_counts``, ``log10_rank`` and ``log10_total_counts``.
:raises KeyError: ``total_counts`` is not in ``obs``; run :func:`calculate_qc` first.

### `qc_correlation_table(adata, *, metrics: list[str] | None=None) -> pd.DataFrame`

Pearson correlations between QC metrics across cells.

:param metrics: The ``obs`` columns to correlate. Default: the QC metrics present.
:returns: A square table with a ``metric`` column naming each row.

### `qc_figure(adata, *, metrics: list[str] | None=None)`

Histograms of the QC metrics, one panel per metric, with the median marked.

:param metrics: The ``obs`` columns to plot. Default: the QC metrics present.
:returns: A matplotlib Figure.

<!-- api:end -->

## Methods and parameters

There is one method: scanpy's `calculate_qc_metrics` on the count matrix,
after the input is brought into the OmicsClaw scRNA contract (counts in `X`
and `layers['counts']`, a counts snapshot in `raw`, unique gene names).

| Parameter | Default | Where it comes from | When to change it |
|---|---|---|---|
| `species` | `"human"` | the CLI default | Always set it to the organism of the data. It picks the gene prefixes: `MT-` and `RPS`/`RPL` for human, `mt-` and `Rps`/`Rpl` for mouse. Ask the user when the organism is not in the data description. |
| `calculate_ribo` | `True` | the CLI's fixed behaviour | Leave it on; set `False` only when ribosomal content is irrelevant to the question. |
| `n_top` of `highest_expressed_genes` | 20 | the CLI's table length | Raise it to look for more contaminating genes. |

QC thresholds are not chosen here. Read `qc_summary` and the figure, then
choose thresholds for `sc-filter` or `sc-preprocessing` with the user; the
usual starting points per tissue are in `references/methodology.md`.

## Gotchas

- **No filtering happens here.** `calculate_qc` keeps every cell and gene. Filtering is `sc-filter` (or the thresholds of `sc-preprocessing`).
- **A wrong `species` loses the mitochondrial metric.** With no gene matching the prefix, `pct_counts_mt` is not computed at all, and `qc_summary` has no row for it. Check that the row is there before reporting mitochondrial content.
- **`run_info(adata)["expression_source"]` says which matrix was used as counts**: `layers.counts`, `adata.raw` or `adata.X`. QC fractions only mean something on a count-like source; report it when the input came from outside OmicsClaw.
- **`calculate_qc` returns a new object.** Keep the return value (`adata = qc.calculate_qc(adata)`); the input AnnData is left as it was.
- **Non-count input raises `ValueError`.** A log-normalised `X` with no `counts` layer or count-like `raw` cannot be QC'd; ask for the raw counts.

## Inputs and outputs

- `calculate_qc` reads the count-like matrix from `layers['counts']`, `raw` or `X`, and gene names from `var` (a gene-symbol column when there is one). It writes `obs`: `n_genes_by_counts`, `total_counts`, `pct_counts_mt`, `pct_counts_ribo`, `log10_total_counts`, `log10_n_genes_by_counts`; `var`: `mt`, `ribo`; `layers['counts']`, `raw`, and the contract entries in `uns`.
- The table functions read those `obs` columns and return DataFrames; `qc_figure` returns a matplotlib Figure.

## CLI

`sc_qc.py` runs the same functions outside a project and writes a report,
figures, tables and `processed.h5ad`: `python <skill directory>/sc_qc.py --help`.
`--demo` runs it on PBMC3K.

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — mt/ribo gene-pattern detection, scanpy QC parameters, tissue thresholds
- `references/output_contract.md` — the CLI's table column schemas and figure roles
- Adjacent skills: `sc-standardize-input` (upstream — required if input is external), `sc-filter` (next step — actually removes cells), `sc-doublet-detection` (parallel — finds doublets)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
