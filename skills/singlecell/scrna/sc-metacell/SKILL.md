---
name: sc-metacell
description: Load when aggregating single cells into metacells (sample-aware coarse-grained pseudo-cells)
  on a normalised scRNA AnnData via SEACells or KMeans on a low-D embedding. Skip when ranking marker
  genes per cluster (use sc-markers); trajectory pseudotime ordering (use sc-pseudotime).
tags:
- singlecell
- scrna
- metacell
- seacells
- aggregation
- pseudo-cells
---

# sc-metacell

## Use from a step

```python
aggregation = load_skill("sc-metacell")
cells = read_input("clustered.h5ad")
metacells = aggregation.metacells(cells, method="kmeans", n_metacells=30)
write_output(aggregation.cell_to_metacell(cells), "tables/cell_to_metacell.csv")
write_output(aggregation.metacell_summary(metacells), "tables/metacell_summary.csv")
write_output(metacells, "intermediate/metacells.h5ad")
```

The input receives obs['metacell']; the returned AnnData contains the
aggregates. See `examples/example_step.py` for a PBMC example.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `metacells(adata, *, method: str='seacells', use_rep: str='X_pca', n_metacells: int=30, min_iter: int=10, max_iter: int=30, n_neighbors: int=15, n_pcs: int=20, random_state: int=0, celltype_key: str='leiden')`

Annotate input cells and return a new mean-expression metacell AnnData.

KMeans uses the selected embedding. SEACells falls back to KMeans only
when its package cannot be imported; a warning and run_info identify the
fallback. Runtime errors propagate. Counts
are averaged, not summed, using layers['counts'] when present, else X.
Input X is preserved; obs['metacell'] receives the assignments.

:param method: seacells (default) or kmeans.
:param use_rep: Existing embedding, default X_pca.
:param n_metacells: Requested aggregates, default 30; at least 2 and fewer than cells.
:param min_iter: SEACells minimum fitting iterations, default 10.
:param max_iter: SEACells maximum fitting iterations, default 30.
:param n_neighbors: Neighbor count for SEACells when its graph is absent, default 15.
:param n_pcs: PCs for that graph, default 20.
:param random_state: Seed for KMeans and SEACells initialization, default 0.
:param celltype_key: SEACells dominant-celltype annotation, default leiden.
    KMeans retains the legacy dominant_label from the first obs column.
:returns: A new AnnData with mean_expression layer, n_cells and dominant_label.
:raises ValueError: The method, embedding or numerical parameters are invalid.

### `aggregate_metacells(adata, labels: pd.Series | None=None)`

Return mean-expression aggregates for labels, or the input obs['metacell'].

Labels must cover every cell. Prefer layers['counts'] over X. This is
not a summed pseudobulk matrix and does not infer biological replicates.

### `run_info(madata, *, keep: bool=True) -> dict`

Read requested/executed method and aggregation diagnostics from the result.

### `metacell_summary(madata) -> pd.DataFrame`

Return a copy of the aggregate's size and dominant-label metadata.

### `cell_to_metacell(adata) -> pd.DataFrame`

Return cell and metacell columns from the annotated input AnnData.

### `size_distribution_figure(madata)`

Return a matplotlib Figure of cells per metacell.

<!-- api:end -->

## Methods and parameters

`method="seacells"` retains the CLI default. If SEACells is unavailable,
the API warns, uses KMeans and records both methods in `run_info`. Other backend
errors propagate. `method="kmeans"` avoids that optional dependency.

Defaults remain `use_rep="X_pca"`, `n_metacells=30`, `min_iter=10`,
`max_iter=30`, `n_neighbors=15` and `n_pcs=20`. KMeans uses the selected
embedding, not a newly constructed neighbor graph. `random_state=0` seeds
KMeans and now also SEACells initialization; the wrapper previously ignored
the seed for SEACells.

## Gotchas

- Aggregation takes the **mean**, not sum, of counts-layer values or X.
  This is not sample-level pseudobulk, and grouping is not sample-aware (`_api.py:82`).
- The legacy KMeans `dominant_label` uses the first obs column, not
  `celltype_key`; that option controls SEACells' extra dominant-celltype column (`_api.py:15`).
- `run_info(metacells)` reports fallback and expression source. Inspect
  `aggregation="mean"` before feeding an aggregate into a count-based model (`_api.py:94`).
- CLI `processed.h5ad` contains original cells plus labels.
  `tables/metacells.h5ad` is the aggregate; use it explicitly when needed.

## Inputs & Outputs

Input needs the selected embedding and more cells than requested aggregates.
The API returns a new metacell AnnData and table/Figure helpers.

CLI files: `processed.h5ad`, its `metacells_annotated.h5ad` alias,
`tables/metacells.h5ad`, `tables/metacell_summary.csv`,
`tables/cell_to_metacell.csv`, `report.md`, `result.json`,
`figures/metacell_centroids.png` and `figures/metacell_size_distribution.png`.
Plot data/manifests and optional R-enhanced figures are also exported.

## Key CLI

```bash
python skills/singlecell/scrna/sc-metacell/sc_metacell.py --demo --method kmeans --output /tmp/sc_metacell_demo
python skills/singlecell/scrna/sc-metacell/sc_metacell.py --input clustered.h5ad --method kmeans --n-metacells 30 --output results/
```

## Dependencies

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scikit-learn`, `scipy`, `SEACells`
