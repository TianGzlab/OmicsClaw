---
name: sc-de
description: Load when finding marker genes per cluster or comparing condition expression in single-cell
  RNA-seq. Skip when the data is bulk (use bulkrna-de); spatial (use spatial-de); cluster-only markers
  without conditions (use sc-markers).
trigger: differential expression, marker genes, de analysis, wilcoxon, pseudo-bulk
tags:
- singlecell
- differential-expression
- markers
- wilcoxon
- deseq2
---

# sc-de

## When to use

The user has a preprocessed scRNA-seq AnnData and wants to know either
(a) which genes mark each cluster (Wilcoxon / t-test / logreg ranking) or
(b) which genes change between conditions in a replicate-aware way
(`pseudobulk_de`, DESeq2 in R).  Mixing normalized expression and raw
counts across these paths is the most common silent-wrong-answer failure
mode, so each path reads the matrix it needs.

## Use from a step

```python
de = load_skill("sc-de")
adata = read_input("results/04_annotation/intermediate/adata_annotated.h5ad")
table = de.rank_genes(adata, groupby="cell_type", method="wilcoxon")
write_output(table, "tables/de_full.csv")
write_output(de.top_genes(table, n_top=10), "tables/markers_top.csv")
write_output(de.volcano_figure(table, group="B cell"), "figures/volcano_b_cell.png")
```

A complete step that runs on demo data: `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `rank_genes(adata, *, groupby: str='leiden', method: str='wilcoxon', group1: str | None=None, group2: str | None=None, logreg_solver: str='lbfgs') -> pd.DataFrame`

Rank genes per group of cells: every group against the rest, or ``group1`` against ``group2``.

``wilcoxon``, ``t-test`` and ``logreg`` run scanpy's ``rank_genes_groups`` on
``X`` (``use_raw=False``, with the fraction of expressing cells) and also leave
its result in ``uns['rank_genes_groups']``; ``mast`` runs the MAST hurdle model
in R. Cells are the units here, so p-values overstate the evidence for a
difference between conditions; use :func:`pseudobulk_de` for that.

:param groupby: The ``obs`` column defining the groups. Default ``"leiden"``; when it
    is missing and ``louvain`` exists, ``louvain`` is used and recorded.
:param method: ``"wilcoxon"`` (default; scanpy's recommended test), ``"t-test"``,
    ``"logreg"`` or ``"mast"``.
:param group1: Compare only this group ...
:param group2: ... against this one. Default: each group against the rest.
:param logreg_solver: The scikit-learn solver for ``logreg``. Default ``"lbfgs"``.
:returns: One row per gene and group. scanpy methods: ``names``, ``scores``,
    ``logfoldchanges``, ``pvals``, ``pvals_adj``, ``pct_nz_group``,
    ``pct_nz_reference``, ``group``; ``mast``: ``gene``, ``group``, ``pvalue``,
    ``padj`` and effect columns.
:raises ValueError: an unknown method, or the group column is missing.
:raises RuntimeError: ``mast`` and R or MAST is missing.

### `pseudobulk_de(adata, *, condition_key: str, group1: str, group2: str, sample_key: str='sample_id', celltype_key: str='cell_type', min_cells: int=10, min_counts: int=1000) -> pd.DataFrame`

DESeq2 on pseudobulk counts: one test of ``group1`` against ``group2`` per cell type, run in R.

Counts are summed per sample and cell type from ``layers['counts']``, ``raw``
or a count-like ``X``; bins below the thresholds are dropped. Samples, not
cells, are the units, so this is the test for condition effects.

:param condition_key: The ``obs`` column holding the condition.
:param group1: The condition of interest (numerator of the fold change).
:param group2: The reference condition.
:param sample_key: The ``obs`` column naming biological replicates. Default ``"sample_id"``.
:param celltype_key: The ``obs`` column with cell types. Default ``"cell_type"``.
:param min_cells: Minimum cells per sample and cell type bin. Default 10.
:param min_counts: Minimum total counts per bin. Default 1000.
:returns: Columns ``gene``, ``log2FoldChange``, ``pvalue``, ``padj`` (and DESeq2's
    others) plus ``cell_type``.
:raises ValueError: a missing column, missing groups, or no count-like matrix.
:raises RuntimeError: R or DESeq2 is missing, or no bin passes the thresholds.

### `run_info(adata, *, keep: bool=True) -> dict`

What the last :func:`rank_genes` or :func:`pseudobulk_de` call recorded under ``summary``.

``summary`` has ``method``, ``groupby`` (the column actually used), ``n_groups``,
``n_genes_tested`` and ``expression_source``.

:param keep: Leave the record in ``adata.uns``; ``False`` removes it.
:returns: The record, or an empty dict when neither has run on *adata*.

### `top_genes(table: pd.DataFrame, *, n_top: int=10) -> pd.DataFrame`

The first *n_top* genes of each group.

A scanpy table is already ranked within each group. A table with ``padj``
(MAST) is sorted by ``padj`` then ``pvalue`` first.

:param table: What :func:`rank_genes` returned.
:param n_top: Genes per group. Default 10, the CLI's default.
:returns: The selected rows, in the table's columns.

### `volcano_figure(table: pd.DataFrame, *, padj_threshold: float=0.05, log2fc_threshold: float=1.0, group: str | None=None)`

A volcano plot of a DE table, significant genes coloured.

:param table: What :func:`rank_genes` or :func:`pseudobulk_de` returned.
:param padj_threshold: Adjusted p-value cut. Default 0.05.
:param log2fc_threshold: Absolute log2 fold-change cut. Default 1.0.
:param group: Plot only this group (or cell type). Default: all rows.
:returns: A matplotlib Figure.

<!-- api:end -->

## Methods and parameters

| Question | Function | Units | Needs |
|---|---|---|---|
| Which genes mark each cluster or cell type | `rank_genes(method="wilcoxon")` (default) | cells | normalised `X` |
| Same, other tests | `rank_genes(method="t-test" / "logreg")` | cells | normalised `X` |
| Same, hurdle model | `rank_genes(method="mast")` | cells | log-normalised `X`; R with MAST |
| Which genes change between conditions | `pseudobulk_de(...)` | samples | raw counts; a replicate column; R with DESeq2 |

Defaults and their sources: `method="wilcoxon"` is scanpy's recommended
marker test; `n_top=10` and the volcano cuts (`padj_threshold=0.05`,
`log2fc_threshold=1.0`) are the CLI's defaults; `min_cells=10` and
`min_counts=1000` per pseudobulk bin are the CLI's defaults, a common
choice for 10x data. A comparison between conditions with biological
replicates is a pseudobulk question; ask the user for the replicate column
when it is not obvious.

## Gotchas

- **Cell-level tests are not replicate-aware.** Wilcoxon, t-test, logreg and MAST treat each cell as independent, which inflates false positives for treated-versus-control comparisons. Use `pseudobulk_de` whenever there are biological replicates and the question is about the condition.
- **`pseudobulk_de` needs raw counts.** It takes `layers["counts"]`, then `raw`, then `X`, each only if it looks count-like; check `run_info(adata)["summary"]["expression_source"]` after the run: `layers.counts` or `adata.raw`, not `adata.X`.
- **`pseudobulk_de` needs `group1` and `group2`.** The cell-level tests compare each group with the rest when they are absent.
- **Small bins drop whole cell types.** Sample-by-cell-type bins under `min_cells` cells are skipped without a note; check the per-sample cell counts before reading "no DEGs" as a biological null.
- **`sample_key` is the statistical design.** It must name biological replicates with at least two per condition; a non-replicate column gives nonsense and is not caught.
- **`groupby="leiden"` falls back to `louvain`** when only `louvain` exists; `run_info(adata)["summary"]["groupby"]` says which column was used.

## Inputs and outputs

- `rank_genes` reads `X` and `obs[groupby]`, writes `uns['rank_genes_groups']` (scanpy methods) and returns the full table. `pseudobulk_de` reads the count matrix and `obs[condition_key]`, `obs[sample_key]`, `obs[celltype_key]`, and returns one table for all cell types.
- `top_genes` returns a DataFrame; `volcano_figure` returns a matplotlib Figure.

## CLI

`sc_de.py` runs the same functions outside a project and writes a report,
figures, tables and `processed.h5ad`: `python <skill directory>/sc_de.py --help`.
`--demo` ranks PBMC3k's louvain clusters.

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — the DE paths, scope boundary, input expectations, workflow
- `references/output_contract.md` — the CLI's output directory layout + visualization contract
- `references/r_visualization.md` — five R-enhanced renderers
- Adjacent skills: `sc-clustering` (upstream cluster discovery), `sc-cell-annotation` (upstream cell type labels for `celltype_key`), `sc-markers` (lighter cluster-marker-only path), `sc-enrichment` (downstream pathway enrichment of DEG lists), `bulkrna-de` / `spatial-de` (sibling DE skills for the other two data modalities)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`adjustText`, `anndata`, `matplotlib`, `numpy`, `pandas`, `pydeseq2`, `scanpy`, `scipy`, `seaborn`
