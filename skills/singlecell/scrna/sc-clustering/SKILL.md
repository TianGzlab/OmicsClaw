---
name: sc-clustering
description: Load when building the neighbour graph, embedding (UMAP/t-SNE/diffmap/PHATE), and clustering
  (Leiden/Louvain) on a normalised single-cell AnnData. Skip when QC/normalisation/HVG/PCA have not run
  yet (use sc-preprocessing); marker ranking after clustering (use sc-markers).
tags:
- singlecell
- scrna
- clustering
- leiden
- louvain
- umap
- tsne
- phate
---

# sc-clustering

## When to use

The user has a normalised AnnData with PCA / integrated embedding
already populated and wants the standard scRNA neighbour-graph →
embedding → cluster workflow.  Combinable in one call: pick an
embedding method (`umap` default, also `tsne` / `diffmap` / `phate`)
and a clustering method (`leiden` default, also `louvain`), with an
explicit resolution or auto-resolution search.  Reads from
`obsm["X_pca"]` / `obsm["X_harmony"]` / etc. via `use_rep`.

## Use from a step

```python
clustering = load_skill("sc-clustering")
adata = read_input("results/02_preprocess/intermediate/adata_preprocessed.h5ad")
# resolution 0.8: the user wants broad cell types; sc-clustering's default is 1.0.
adata = clustering.cluster(adata, resolution=0.8)
write_output(clustering.cluster_summary(adata, key="leiden"), "tables/cluster_summary.csv")
write_output(clustering.embedding_figure(adata, color="leiden"), "figures/umap_leiden.png")
write_output(adata, "intermediate/adata_clustered.h5ad")
```

A complete step that runs on demo data: `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `cluster(adata, *, use_rep: str | None=None, n_neighbors: int=15, n_pcs: int=50, embedding: str='umap', method: str='leiden', resolution: float=1.0, random_state: int=0, umap_min_dist: float=0.5, umap_spread: float=1.0, tsne_perplexity: float=30.0, tsne_metric: str='euclidean', diffmap_n_comps: int=15, phate_knn: int=15, phate_decay: int=40)`

Build the neighbour graph, cluster the cells and compute a 2-D embedding, in place.

Writes ``obs[method]`` (the cluster labels, a categorical of strings),
``obsm['X_<embedding>']``, the graph in ``obsp`` and ``uns['neighbors']``, and
records the cluster key as the primary one in the matrix contract.

:param use_rep: The ``obsm`` key the graph is built on. Default ``None``: the
    first of ``X_pca``, ``X_harmony``, ``X_scvi``, ``X_scanvi``, ``X_scanorama``
    present. Pass ``X_harmony`` or ``X_scvi`` after batch integration.
:param n_neighbors: Neighbours per cell in the graph. Default 15, scanpy's default.
    Larger values give smoother, coarser structure.
:param n_pcs: Components of ``use_rep`` to use. Default 50; pick it from
    sc-preprocessing's ``pca_variance_table`` (the elbow) when the data are small.
:param embedding: ``"umap"`` (default), ``"tsne"``, ``"diffmap"`` or ``"phate"``.
:param method: ``"leiden"`` (default) or ``"louvain"``; also the ``obs`` column written.
:param resolution: Clustering resolution. Default 1.0, scanpy's default. Lower it
    (0.3 to 0.6) for broad cell types, raise it for finer subtypes; or use
    :func:`auto_resolution`.
:param random_state: Seed for the graph, the clustering and the embedding. Default 0,
    scanpy's default, which makes reruns reproduce the labels.
:param umap_min_dist: UMAP ``min_dist``. Default 0.5, scanpy's default.
:param umap_spread: UMAP ``spread``. Default 1.0, scanpy's default.
:param tsne_perplexity: t-SNE perplexity. Default 30.
:param tsne_metric: t-SNE distance metric. Default ``"euclidean"``.
:param diffmap_n_comps: Diffusion-map components. Default 15.
:param phate_knn: PHATE neighbours. Default 15.
:param phate_decay: PHATE alpha decay. Default 40.
:returns: The same AnnData.
:raises ValueError: no embedding is available, or an unknown method or embedding.

### `auto_resolution(adata, *, use_rep: str | None=None, n_neighbors: int=15, n_pcs: int=50, method: str='leiden', resolutions: list[float] | None=None, n_subsample_reps: int=5, subsample_fraction: float=0.8, random_state: int=1) -> pd.DataFrame`

Choose a clustering resolution by how stably cells co-cluster under subsampling.

Builds the neighbour graph, then for every candidate resolution clusters
``n_subsample_reps`` random subsamples, turns how often two cells share a
cluster into a distance, and scores the full-data clustering with the
silhouette on that distance. The best-scoring clustering is left in
``obs[method]``; pass the selected resolution to :func:`cluster`. The cost
grows with the square of the number of cells.

:param use_rep: As in :func:`cluster`.
:param n_neighbors: As in :func:`cluster`.
:param n_pcs: As in :func:`cluster`.
:param method: ``"leiden"`` (default) or ``"louvain"``.
:param resolutions: Candidates. Default ``[0.4, 0.6, 0.8, 1.0, 1.2, 1.4]``.
:param n_subsample_reps: Subsamples per resolution. Default 5.
:param subsample_fraction: Fraction of cells in each subsample. Default 0.8.
:param random_state: Seed for the subsampling. Default 1, the CLI's value.
:returns: Columns ``resolution``, ``silhouette_score`` and ``selected`` (true on the chosen row).

### `run_info(adata, *, keep: bool=True) -> dict`

What :func:`cluster` recorded: ``use_rep``, ``cluster_key``, ``embedding_key`` and the contracts.

:param keep: Leave the record in ``adata.uns``; ``False`` removes it.
:returns: The record, or an empty dict when ``cluster`` has not run on *adata*.

### `cluster_summary(adata, *, key: str='leiden') -> pd.DataFrame`

Cells per cluster, largest first.

:param key: The ``obs`` column holding the labels. Default ``"leiden"``.
:returns: Columns ``cluster``, ``n_cells`` and ``proportion_pct`` (rounded to 2 decimals).

### `embedding_figure(adata, *, color: str='leiden', basis: str | None=None)`

A scatter plot of the 2-D embedding, coloured by an ``obs`` column.

:param color: The ``obs`` column to colour by. Default ``"leiden"``.
:param basis: The ``obsm`` key to plot. Default: the first of ``X_umap``,
    ``X_tsne``, ``X_diffmap``, ``X_phate`` present.
:returns: A matplotlib Figure.
:raises KeyError: no 2-D embedding is present.

<!-- api:end -->

## Methods and parameters

- **Graph**: scanpy `neighbors` on `use_rep` with `n_neighbors=15` and `n_pcs=50`, scanpy's defaults. Pick `n_pcs` from the elbow of sc-preprocessing's `pca_variance_table` when it is clearly below 50; raise `n_neighbors` (30 to 50) for smoother, coarser structure on large datasets.
- **Clustering**: `leiden` (default; Traag et al. 2019, guarantees connected communities) or `louvain`. `resolution=1.0` is scanpy's default. It is the parameter the user most often has an opinion on: broad cell types usually come out around 0.3 to 0.6, subtypes at 1.0 to 2.0. Ask, or try two values in variant steps (`02a_leiden_r05.py`, `02b_leiden_r10.py`) and compare.
- **`auto_resolution`**: picks the resolution whose clustering is most stable under subsampling (silhouette on a co-clustering distance). It costs time quadratic in the cell count; on more than a few thousand cells subsample first or choose by hand.
- **Embedding**: `umap` (default; `min_dist=0.5`, `spread=1.0`, scanpy's defaults), `tsne` (perplexity 30), `diffmap` (15 components, for trajectories), `phate` (needs the `phate` package).
- **`random_state=0`**: scanpy's default seed for the graph, clustering and UMAP; keep it fixed so reruns and the standalone run of the step give the same labels.

## Gotchas

- **No embedding → `ValueError`.** `cluster` needs `obsm["X_pca"]` or the `use_rep` you name. Run sc-preprocessing (or sc-batch-integration) first.
- **The label column is named after the method.** `cluster(method="leiden")` writes `obs["leiden"]` and overwrites an existing one; copy the old labels to another column first when you need to compare.
- **`cluster` works in place.** It returns the same AnnData; write it out with `write_output` to keep the labels.
- **Use the integrated embedding after batch correction.** With `X_harmony` or `X_scvi` present, pass it as `use_rep`; the default picks `X_pca` first.

## Inputs and outputs

- Reads `obsm[use_rep]` (default `X_pca`) and the matrix contract in `uns`.
- Writes `obs[method]` (labels as strings), `obsm['X_<embedding>']`, `obsp['connectivities']` / `obsp['distances']`, `uns['neighbors']`, and the contract's primary cluster key. `auto_resolution` also leaves its best clustering in `obs[method]`.
- `cluster_summary` and `auto_resolution` return DataFrames; `embedding_figure` returns a matplotlib Figure.

## CLI

`sc_cluster.py` runs the same functions outside a project and writes a
report, figures, tables and `processed.h5ad`:
`python <skill directory>/sc_cluster.py --help`. `--demo` runs it on PBMC3k.

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — embedding choice guide, auto-resolution heuristic
- `references/output_contract.md` — `obs` / `obsm` keys + the CLI's table schemas
- Adjacent skills: `sc-preprocessing` (upstream — normalise/HVG/PCA before this), `sc-batch-integration` (parallel — produces the integrated embedding `use_rep` reads from), `sc-markers` (downstream — rank cluster markers from `obs["leiden"]`)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `louvain`, `matplotlib`, `numpy`, `pandas`, `phate`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`
