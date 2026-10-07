---
name: sc-batch-integration
description: Load when integrating multi-sample scRNA-seq with Harmony, scVI, scANVI, BBKNN, Scanorama,
  SIMBA, or supported R-backed methods to remove batch effects. Skip when the data is one sample (no batch
  effect to integrate); upstream merging only (use sc-multi-count).
trigger: batch integration, batch effect, harmony, scvi, bbknn, merge samples
tags:
- singlecell
- scrna
- batch-integration
- harmony
- scvi
- scanvi
- bbknn
- scanorama
- simba
---

# sc-batch-integration

## When to use

Correct batch effects in merged, normalised scRNA data. The nine methods are
Harmony (default), scVI, scANVI, BBKNN, Scanorama, SIMBA, fastMNN, Seurat CCA
and Seurat RPCA. Check batch/condition confounding before correction: a batch
fully confounded with the biological contrast cannot be separated statistically.

## Steps

Start a notebook step with `python skills/_sdk/notebook/run.py new integration`.
Inside it, use `integration = load_skill("sc-batch-integration")`, then
`adata = integration.integrate(adata, method="harmony", batch_key="batch")`.
This returns the corrected representation; choose neighbours, UMAP and
clustering separately with `sc-clustering`. After BBKNN, call
`load_skill("sc-clustering").cluster(adata, use_existing_graph=True)` to keep
the corrected graph. The default clustering call rebuilds it and loses BBKNN's
batch correction.
The CLI additionally builds neighbours/UMAP and writes the legacy report.
See `examples/example_step.py` for a runnable PBMC example.

## Inputs & Outputs

Input is AnnData with a batch column and normalised `X`. Keep counts in
`layers['counts']` for scVI/scANVI and R integration. Existing PCA is optional.
The API returns AnnData and separate table/Figure helpers; it writes no output
directory. R methods retain the existing H5AD bridge and need zellkonverter.

CLI outputs are `processed.h5ad`, `report.md`, `result.json` and
`reproducibility/{commands.sh,requirements.txt}`. Non-empty tables are written
to `tables/{integration_summary,batch_sizes,cluster_sizes,batch_mixing_matrix,integration_metrics}.csv`.
Label-dependent tables and plots are optional. Plot data, including UMAP
coordinates, live under `figure_data/`, not `tables/umap.csv`.
See `references/output_contract.md` for the conditional inventory.

## Gotchas

- `result.json.data.requested_method`, `executed_method`, `fallback_used` and
  `fallback_reason` record scANVI's fallback to scVI when labels are absent.
  Supply `--labels-key` to choose an existing label column.
- `tables/integration_metrics.csv` omits unavailable LISI/ASW values; this is
  not evidence of good or bad integration. Label-free input has no label ASW.
- `_api.py:303`: `run_info(adata)` contains a small JSON summary. The retained Seurat bridge
  also returns old R UMAP coordinates under the private
  `uns['_omicsclaw_legacy_integration_umap']` key. The CLI moves these to
  `obsm['X_umap']` and removes the private key; the API adds no UMAP to obsm.
- `_api.py:39`: `obsm['X_harmony']` uses existing PCA only when the requested PCA size would
  exceed the data's rank. Normal-sized input still recomputes PCA.
- `_api.py:182`: SIMBA uses a temporary working directory; do not run it concurrently in
  threads. Its returned AnnData can be a cell-subset copy.

## Key CLI

```bash
python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py --demo --output /tmp/sc_integrate_demo
python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py --input merged.h5ad --output results/integration --method harmony --batch-key sample_id --seed 0
python skills/singlecell/scrna/sc-batch-integration/sc_integrate.py --input labelled.h5ad --output results/scanvi --method scanvi --labels-key cell_type --no-gpu --n-epochs 200
```

`--seed` controls Harmony, Scanorama and scVI/scANVI and the Python CLI UMAP.
It does not control SIMBA or the retained R integration bridge.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `integrate(adata, *, method: str='harmony', batch_key: str='batch', harmony_theta: float=2.0, n_pcs: int=50, n_latent: int=30, n_epochs: int | None=None, use_gpu: bool=True, labels_key: str | None=None, bbknn_neighbors_within_batch: int=3, scanorama_knn: int=20, integration_features: int=2000, integration_pcs: int=30, simba_n_top_genes: int=3000, simba_n_components: int=15, simba_k: int=15, simba_num_workers: int=4, random_state: int=0)`

Integrate batches and return AnnData with a corrected representation.

``harmony`` reads log-normalised expression and batch labels, writes
``obsm['X_harmony']`` and preserves cells and genes. It recomputes PCA on
ordinary inputs; when ``n_pcs`` exceeds the small input's rank, it reuses
an existing PCA or computes the largest valid PCA. No neighbours or UMAP
are computed. Diagnostics are available through :func:`run_info`.

:param method: ``harmony`` (default), ``scvi``, ``scanvi``, ``bbknn``,
    ``scanorama``, ``simba``, ``fastmnn``, ``seurat_cca`` or ``seurat_rpca``.
    BBKNN writes its batch-balanced neighbour graph, not a new embedding.
:param batch_key: Batch column in ``obs``; default ``batch``.
:param harmony_theta: Harmony diversity penalty; default 2.0.
:param n_pcs: Requested Harmony components; default 50.
:param n_latent: scVI/scANVI latent dimensions; default 30.
:param n_epochs: Training epochs; None uses 400 for scVI, 200 for scANVI.
:param use_gpu: Request a GPU for scVI/scANVI; default True, CPU if unavailable.
:param labels_key: scANVI labels; None searches cell_type/leiden/louvain/
    seurat_clusters. With no labels it falls back to scVI and records why.
:param bbknn_neighbors_within_batch: BBKNN neighbours per batch; default 3.
:param scanorama_knn: Scanorama matching neighbours; default 20.
:param integration_features: R integration variable genes; default 2000.
:param integration_pcs: R integration components; default 30.
:param simba_n_top_genes: SIMBA variable genes; default 3000.
:param simba_n_components: SIMBA inter-batch components; default 15.
:param simba_k: SIMBA inter-batch neighbours; default 15.
:param simba_num_workers: SIMBA training workers; default 4.
:param random_state: Backend seed; default 0.
    Passed to Harmony, Scanorama and scVI/scANVI. SIMBA and the retained
    R bridge do not expose this seed. SIMBA runs in a temporary working
    directory; do not call it concurrently from multiple threads.
:returns: AnnData, modified in place for Python methods except SIMBA.
    SIMBA and R methods can return a cell-subset copy. scVI/scANVI require
    raw counts in ``layers['counts']``; other Python methods use ``X``.
:raises ValueError: The method, batch column or PCA dimensions are invalid.
:raises ImportError: The chosen optional backend is unavailable.

### `run_info(adata, *, keep: bool=True) -> dict`

Return integration diagnostics; set ``keep=False`` to remove them from ``uns``.

### `integration_metrics(adata, *, batch_key: str='batch', label_key: str | None=None, embedding_key: str='X_harmony') -> pd.DataFrame`

Return LISI and ASW diagnostics; unavailable metrics are logged and omitted.

LISI values are also attached to ``obs["ilisi"]`` and, with labels,
``obs["clisi"]``. The corrected embedding and batch column must exist.

### `batch_mixing_table(adata, *, batch_key: str='batch', label_key: str | None=None) -> pd.DataFrame`

Return each label's fraction of cells from each batch; empty without labels.

### `batch_sizes_table(adata, *, batch_key: str='batch') -> pd.DataFrame`

Return batch labels and cell counts, largest first.

### `batch_sizes_figure(adata, *, batch_key: str='batch')`

Return a Figure of cell counts per batch; the caller owns saving and closing it.

<!-- api:end -->

## See also

`sc-multi-count` merges samples; `sc-clustering` clusters the returned
representation; `sc-cell-annotation` supplies labels. CLI tuning details are
in `references/parameters.md`.

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `bbknn`, `harmonypy`, `matplotlib`, `numpy`, `pandas`, `phate`, `scanorama`, `scanpy`, `scikit-learn`, `scipy`, `scvi-tools`, `seaborn`, `simba-bio`, `torch`
