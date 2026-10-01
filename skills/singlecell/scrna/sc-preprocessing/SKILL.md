---
name: sc-preprocessing
description: Load when normalising QC'd scRNA into a PCA-ready AnnData via scanpy / Seurat / SCTransform
  / Pearson residuals. Skip when QC thresholds are still undecided (use sc-qc); batch correction across
  samples (use sc-batch-integration).
trigger: single cell preprocess, scRNA preprocessing, normalize hvg pca, base preprocessing, Seurat preprocessing, SCTransform preprocessing
tags:
- singlecell
- scrna
- preprocessing
- normalization
- hvg
- pca
- scanpy
- seurat
- sctransform
- pearson_residuals
---

# sc-preprocessing

## When to use

The user has a QC'd AnnData and wants the standard
"filter → normalise → HVG → PCA" pipeline before clustering or batch
integration. Four interchangeable backends are available: `scanpy`
(default; CP10k log + HVG seurat flavour), `seurat` (R-backed
LogNormalize / CLR / RC), `sctransform` (R-backed regularised NB), and
`pearson_residuals` (raw-count HVG selection plus Pearson residual
transformation). The skill stops at PCA — UMAP / clustering live in
`sc-clustering`, multi-sample correction in `sc-batch-integration`.

## Use from a step

```python
pre = load_skill("sc-preprocessing")
adata = read_input("results/01_qc/intermediate/adata_qc.h5ad")
# max_mt_pct 10: PBMC cells above 10% mitochondrial reads are mostly damaged (agreed with the user).
adata = pre.preprocess(adata, method="scanpy", max_mt_pct=10.0)
write_output(pre.run_info(adata)["filter_summary"], "tables/filter_summary.json")
write_output(pre.pca_variance_table(adata), "tables/pca_variance_ratio.csv")
write_output(adata, "intermediate/adata_preprocessed.h5ad")
```

A complete step that runs on demo data: `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `preprocess(adata, *, method: str='scanpy', min_genes: int=200, min_cells: int=3, max_mt_pct: float=20.0, n_top_hvg: int | None=None, n_pcs: int=50, normalization_target_sum: float=10000.0, scanpy_hvg_flavor: str='seurat', pearson_hvg_flavor: str='seurat_v3', pearson_theta: float=100.0, seurat_normalize_method: str='LogNormalize', seurat_scale_factor: float=10000.0, seurat_hvg_method: str='vst', sctransform_regress_mt: bool=True, remove_doublets: bool=True, doublet_score_threshold: float=0.25, preserve_var_names: bool=False)`

Filter cells and genes, normalise, select highly variable genes and run PCA.

The input is first brought into the OmicsClaw scRNA contract (counts in
``layers['counts']``, a counts snapshot in ``raw``) and QC metrics are added
when missing. Cells and genes are then filtered by the thresholds below,
and doublets are dropped when ``predicted_doublet`` or ``doublet_score``
from sc-doublet-detection are in ``obs``. Finally the chosen method
normalises ``X``, flags ``var['highly_variable']`` and writes
``obsm['X_pca']``. What was filtered is recorded for :func:`run_info`.

:param method: ``"scanpy"`` (normalize_total, log1p, HVG, PCA; the default),
    ``"pearson_residuals"`` (analytic Pearson residuals for HVG and PCA; ``X``
    stays log-normalised), ``"seurat"`` (Seurat LogNormalize in R) or
    ``"sctransform"`` (Seurat SCTransform in R).
:param min_genes: Drop cells with fewer detected genes. Default 200, the
    scanpy and Seurat tutorial value; lower it for low-depth data.
:param min_cells: Drop genes detected in fewer cells. Default 3, the tutorial value.
:param max_mt_pct: Drop cells above this mitochondrial percentage. Default 20.0,
    a permissive threshold; PBMC data usually uses 5 to 10. Agree it with the user.
:param n_top_hvg: Number of highly variable genes. Default ``None``: 3000 for
    ``sctransform``, 2000 for the other methods (their tutorials' values).
:param n_pcs: Principal components to compute. Default 50.
:param normalization_target_sum: Counts per cell after ``normalize_total``
    (``scanpy`` only). Default 10000.
:param scanpy_hvg_flavor: HVG flavor for ``scanpy``: ``"seurat"`` (default),
    ``"cell_ranger"`` or ``"seurat_v3"``.
:param pearson_hvg_flavor: HVG flavor for ``pearson_residuals``. Default ``"seurat_v3"``.
:param pearson_theta: Overdispersion for Pearson residuals. Default 100, scanpy's default.
:param seurat_normalize_method: Seurat ``NormalizeData`` method. Default ``"LogNormalize"``.
:param seurat_scale_factor: Seurat scale factor. Default 10000.
:param seurat_hvg_method: Seurat ``FindVariableFeatures`` method. Default ``"vst"``.
:param sctransform_regress_mt: Regress out mitochondrial percentage in SCTransform. Default ``True``.
:param remove_doublets: Drop cells flagged as doublets when the flags are present. Default ``True``.
:param doublet_score_threshold: Score above which a cell counts as a doublet when only
    ``doublet_score`` is present. Default 0.25.
:param preserve_var_names: Keep the input's gene identifiers instead of the
    symbols chosen during standardisation. Default ``False``.
:returns: A new AnnData: filtered, normalised ``X``, ``layers['counts']``, ``raw``
    counts snapshot, ``var['highly_variable']``, ``obsm['X_pca']``, ``uns['pca']``.
:raises ValueError: an unknown method, or input with no count-like matrix.
:raises RuntimeError: the R methods fail, or their R packages are missing.

### `run_info(adata, *, keep: bool=True) -> dict`

What :func:`preprocess` recorded about its run.

Keys: ``method``; ``filter_summary`` (cells and genes before and after
filtering, cells removed by each threshold under ``filter_stats``, whether QC
metrics were reused, and ``input_preparation``: the matrix used as counts,
gene-name source, warnings and inferred species); ``input_contract``;
``matrix_contract``.

:param keep: Leave the record in ``adata.uns``; ``False`` removes it.
:returns: The record, or an empty dict when ``preprocess`` has not run on *adata*.

### `hvg_table(adata, *, n_top: int=50) -> pd.DataFrame`

The most variable genes with their mean and dispersion statistics.

:param n_top: How many genes to return, most variable first. Default 50.
:returns: Column ``gene`` plus whichever of ``means``, ``variances``,
    ``variances_norm``, ``dispersions``, ``dispersions_norm`` the method wrote.

### `pca_variance_table(adata) -> pd.DataFrame`

Variance explained by each principal component, to choose how many to keep downstream.

:returns: Columns ``pc``, ``variance_ratio`` and ``cumulative_variance_ratio``.

### `pca_embedding_table(adata, *, n_components: int=5) -> pd.DataFrame`

The first principal-component coordinates of every cell.

:param n_components: How many components to include. Default 5.
:returns: Column ``cell_id`` followed by ``PC1``, ``PC2``, ...

### `qc_metrics_table(adata) -> pd.DataFrame`

The QC metrics of the cells that passed filtering.

:returns: Column ``cell_id`` followed by whichever of ``n_genes_by_counts``,
    ``total_counts`` and ``pct_counts_mt`` are in ``obs``.

### `pca_variance_figure(adata, *, n_pcs: int=50)`

An elbow plot of the variance ratio per principal component.

:param n_pcs: How many components to show. Default 50.
:returns: A matplotlib Figure.
:raises KeyError: ``uns['pca']`` is missing; run :func:`preprocess` first.

<!-- api:end -->

## Methods and parameters

| Method | Use when | Notes |
|---|---|---|
| `scanpy` (default) | most 10x data | `normalize_total` to 10,000, `log1p`, HVG (`seurat` flavor), PCA with `arpack` |
| `pearson_residuals` | very sparse or heterogeneous data | HVG and PCA on analytic Pearson residuals (Lause et al. 2021); `X` stays log-normalised for plotting and DE |
| `seurat` | the user wants Seurat's LogNormalize numbers | runs `Rscript`; needs Seurat, SingleCellExperiment, zellkonverter, rhdf5 |
| `sctransform` | the user wants SCTransform | runs `Rscript`; also needs sctransform; 3,000 HVGs by default |

Defaults and where they come from:

- `min_genes=200`, `min_cells=3`: the scanpy and Seurat PBMC tutorials. Lower `min_genes` for low-depth or nuclei data.
- `max_mt_pct=20.0`: a permissive ceiling, not a recommendation. Read sc-qc's `pct_counts_mt` distribution and agree the value with the user; PBMC usually uses 5 to 10, tissues with high metabolic activity more.
- `n_top_hvg`: 2,000 (3,000 for `sctransform`), the tutorials' values. Raise it for very heterogeneous data.
- `n_pcs=50`: scanpy's default upper bound; later steps choose how many to use from `pca_variance_table`.
- `remove_doublets=True`, `doublet_score_threshold=0.25`: only act when sc-doublet-detection columns are in `obs`.

Every threshold you change goes into the step with its reason.

## Gotchas

- **`preprocess` returns a new, filtered object.** Keep the return value; cells and genes below the thresholds are gone from it, and `run_info(adata)["filter_summary"]` says how many each threshold removed.
- **Fewer PCs than requested.** Small matrices cap `obsm["X_pca"]` below `n_pcs`; use `adata.obsm["X_pca"].shape[1]` when you pass `n_pcs` to sc-clustering.
- **R methods need a working `Rscript` stack.** `preprocess(method="seurat")` raises `RuntimeError` when the R packages are missing or when the R round-trip returns no overlapping cells or genes. Check `Rscript` before choosing them.
- **Doublets are dropped whenever sc-doublet-detection ran.** Pass `remove_doublets=False` to keep the called doublets.
- **`X` is normalised, not counts.** Raw counts stay in `layers["counts"]` and `raw`; methods that need counts (pseudobulk DE) read them from there.

## Inputs and outputs

- Reads the count matrix from `layers['counts']`, `raw` or `X` (as sc-qc does) and the QC columns of `obs` when present.
- Writes a new AnnData: normalised `X`; `layers['counts']`; `raw` (counts snapshot); `obs` QC columns; `var['highly_variable']` and the HVG statistics; `obsm['X_pca']`; `uns['pca']`; `layers['pearson_residuals']` for that method; contract entries in `uns`.
- The table functions return DataFrames; `pca_variance_figure` returns a matplotlib Figure.

## CLI

`sc_preprocess.py` runs the same functions outside a project and writes a
report, figures, tables and `processed.h5ad`:
`python <skill directory>/sc_preprocess.py --help`. `--demo` runs it on PBMC3k.

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — when each backend wins; canonicalisation contract
- `references/output_contract.md` — `obs` / `obsm` / `layers` / `uns` schema + the CLI's table layouts
- Adjacent skills: `sc-qc` / `sc-filter` (upstream — produce the input), `sc-batch-integration` (parallel — multi-sample alternative path; consumes `obsm["X_pca"]`), `sc-clustering` (downstream — consumes `obsm["X_pca"]` for neighbour-graph + UMAP + Leiden)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `phate`, `scanpy`, `scipy`, `seaborn`
