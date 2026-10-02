---
name: sc-cell-annotation
description: Load when assigning cell-type labels to a clustered scRNA AnnData via marker dictionaries,
  CellTypist, PopV, KNNPredict, SingleR, scmap, SCSA, or a manual cluster-to-label map. Skip when ranking
  marker genes per cluster (use sc-markers); condition-vs-control DE (use sc-de).
tags:
- singlecell
- scrna
- cell-annotation
- celltypist
- popv
- singler
- scmap
- scsa
- knnpredict
- markers
---

# sc-cell-annotation

## When to use

The user has a clustered AnnData (e.g. `obs["leiden"]`) and wants
labelled cell types in `obs["cell_type"]`. Pick a method by
data / reference availability:

- `markers` (default) — built-in or custom marker-gene scoring.
- `manual` — user-supplied cluster-to-label map.
- `celltypist` — pretrained `Immune_All_Low.pkl` style classifier.
- `popv` / `knnpredict` — reference AnnData mapping (PopV consensus or lightweight KNN).
- `singler` / `scmap` — R-backed reference annotation.
- `scsa` — Fisher-test DB scoring (`species`, `tissue`).

This skill labels — for **ranking** the genes that justify a label use
`sc-markers`; for replicate-aware condition DE use `sc-de`.

## Use from a step

```python
annotation = load_skill("sc-cell-annotation")
adata = read_input("results/03_clustering/intermediate/adata_clustered.h5ad")
# celltypist Immune_All_Low: PBMC sample; the model covers circulating immune types.
adata = annotation.annotate(adata, method="celltypist", model="Immune_All_Low")
run = annotation.run_info(adata)
assert run["summary"]["actual_method"] == "celltypist", run["summary"]["fallback_reason"]
write_output(annotation.annotation_table(adata), "tables/cell_type_counts.csv")
write_output(annotation.annotation_figure(adata), "figures/umap_cell_type.png")
write_output(adata, "intermediate/adata_annotated.h5ad")
```

A complete step that runs on demo data: `examples/example_step.py`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `annotate(adata, *, method: str='markers', cluster_key: str | None=None, markers: dict[str, list[str]] | None=None, marker_file: str | None=None, model: str='Immune_All_Low', majority_voting: bool=False, reference: str='HPCA', manual_map: str | None=None, manual_map_file: str | None=None, species: str='Human', tissue: str='All', scsa_foldchange: float=1.5, scsa_pvalue: float=0.05)`

Annotate cell types with the chosen method; the single entry point to the method functions.

:param method: One of ``markers`` (default), ``manual``, ``celltypist``, ``popv``,
    ``knnpredict``, ``singler``, ``scmap``, ``scsa``. See the method functions for
    what each needs.
:param cluster_key: The ``obs`` column with cluster labels. Default ``None``: the
    matrix contract's primary cluster key, else the first of ``leiden``,
    ``louvain``, ``seurat_clusters``, ``cluster``, ``cell_type`` present.
:param markers: ``markers`` only: cell type to marker genes. Default: the built-in human set.
:param marker_file: ``markers`` only: a JSON or CSV marker file, used instead of *markers*.
:param model: ``celltypist`` only. Default ``"Immune_All_Low"``.
:param majority_voting: ``celltypist`` only. Default ``False``.
:param reference: ``popv``, ``knnpredict``: a labelled ``.h5ad`` path; ``singler``,
    ``scmap``: a celldex atlas name. Default ``"HPCA"``.
:param manual_map: ``manual`` only: inline mapping such as ``"0=T cell;1,2=Myeloid"``.
:param manual_map_file: ``manual`` only: a mapping file (json/csv/tsv/txt).
:param species: ``scsa`` only: ``"Human"`` or ``"Mouse"``. Default ``"Human"``.
:param tissue: ``scsa`` only: CellMarker tissue filter. Default ``"All"``.
:param scsa_foldchange: ``scsa`` only. Default 1.5.
:param scsa_pvalue: ``scsa`` only. Default 0.05.
:returns: The same AnnData.
:raises ValueError: an unknown method, or what the chosen method raises.

### `annotate_markers(adata, *, cluster_key: str | None=None, markers: dict[str, list[str]] | None=None, marker_file: str | None=None)`

Label each cluster with the cell type whose marker genes have the highest mean expression in it.

Every cell of a cluster gets the cluster's label; a cluster where no marker
gene is expressed is ``Unknown``. Gene names are matched exactly, or
case-insensitively when nothing matches exactly (human markers on mouse data).

:param cluster_key: As in :func:`annotate`.
:param markers: Cell type to marker genes. Default: the built-in human set
    (PBMC, brain and general stromal types). Give tissue-specific markers for other tissues.
:param marker_file: A JSON (``{"T cell": ["CD3D", ...]}``) or CSV (``T cell,CD3D;CD3E``)
    marker file, used instead of *markers*.
:returns: The same AnnData with ``obs['cell_type']`` and ``obs['annotation_score']``
    (the winning mean expression).
:raises ValueError: the cluster column is missing.

### `annotate_manual(adata, *, cluster_key: str | None=None, manual_map: str | None=None, manual_map_file: str | None=None)`

Relabel clusters from a mapping the user gives.

:param cluster_key: As in :func:`annotate`.
:param manual_map: Inline mapping such as ``"0=T cell;1,2=Myeloid"``.
:param manual_map_file: A mapping file (json, csv, tsv or txt), used instead of *manual_map*.
:returns: The same AnnData with ``obs['cell_type']``.
:raises ValueError: neither mapping is given.

### `annotate_celltypist(adata, *, model: str='Immune_All_Low', majority_voting: bool=False, cluster_key: str | None=None)`

Per-cell labels from a pretrained CellTypist model.

CellTypist needs log1p-normalised expression to 10,000 counts; when the input
fails that check, or the model cannot be loaded, the function falls back to
:func:`annotate_markers` and records the reason (``run_info(adata)["summary"]["fallback_reason"]``).

:param model: A CellTypist model name or ``.pkl``. Default ``"Immune_All_Low"`` (immune
    cells, fine labels); choose a tissue model for other data. Models download on first use.
:param majority_voting: Smooth labels over over-clustered communities. Default ``False``.
:param cluster_key: Recorded for later steps; CellTypist labels cells individually.
:returns: The same AnnData with ``obs['cell_type']``, ``obs['annotation_score']`` and
    ``obsm['cell_type_prob']``.

### `annotate_popv(adata, *, reference: str='HPCA', cluster_key: str | None=None)`

Labels transferred from a labelled reference AnnData by PopV-style consensus.

:param reference: Path to a labelled ``.h5ad`` (a ``cell_type`` column in ``obs``).
:param cluster_key: As in :func:`annotate`; used for the cluster consensus.
:returns: The same AnnData with ``obs['cell_type']``.

### `annotate_knnpredict(adata, *, reference: str='HPCA', cluster_key: str | None=None)`

Labels transferred from a labelled reference AnnData by nearest neighbours (SCOP KNNPredict style).

:param reference: Path to a labelled ``.h5ad`` (a ``cell_type`` column in ``obs``).
:param cluster_key: As in :func:`annotate`.
:returns: The same AnnData with ``obs['cell_type']`` and ``obs['annotation_score']``.

### `annotate_singler(adata, *, reference: str='HPCA', cluster_key: str | None=None)`

Per-cell labels from SingleR against a celldex atlas, run in R.

:param reference: A celldex atlas: ``HPCA`` (default), ``BlueprintEncode``, ``Monaco``, ...
:param cluster_key: Recorded for later steps; SingleR labels cells individually.
:returns: The same AnnData with ``obs['cell_type']`` and ``obs['annotation_score']``.
:raises RuntimeError: R, SingleR or celldex is missing, or SingleR returns nothing.

### `annotate_scmap(adata, *, reference: str='HPCA', cluster_key: str | None=None)`

Per-cell labels projected with scmap onto a celldex atlas, run in R.

:param reference: A celldex atlas. Default ``HPCA``.
:param cluster_key: Recorded for later steps.
:returns: The same AnnData with ``obs['cell_type']``.
:raises RuntimeError: R, scmap or celldex is missing, or scmap returns nothing.

### `annotate_scsa(adata, *, cluster_key: str | None=None, species: str='Human', tissue: str='All', foldchange: float=1.5, pvalue: float=0.05)`

Cluster labels from CellMarker 2.0 genes scored against each cluster's markers (SCSA).

Runs a Wilcoxon test per cluster and scores each cell type's markers with a
Fisher exact test. The CellMarker table downloads once to
``~/.cache/omicsclaw/scsa``; without network a small built-in set is used.

:param cluster_key: As in :func:`annotate`.
:param species: ``"Human"`` (default) or ``"Mouse"``.
:param tissue: CellMarker tissue filter such as ``"Blood"``. Default ``"All"``.
:param foldchange: Minimum fold change of a cluster marker. Default 1.5.
:param pvalue: Maximum adjusted p-value of a cluster marker. Default 0.05.
:returns: The same AnnData with ``obs['cell_type']``.

### `run_info(adata, *, keep: bool=True) -> dict`

What the last annotate function recorded: ``cluster_key`` and ``summary``.

``summary`` has ``requested_method``, ``actual_method``, ``used_fallback``,
``fallback_reason``, ``n_cell_types``, ``cell_type_counts`` and the method's
own details (reference, marker source, ...).

:param keep: Leave the record in ``adata.uns``; ``False`` removes it.
:returns: The record, or an empty dict when no annotate function has run on *adata*.

### `annotation_table(adata, *, key: str='cell_type') -> pd.DataFrame`

Cells per cell type, largest first.

:param key: The ``obs`` column with the labels. Default ``"cell_type"``.
:returns: Columns ``cell_type``, ``n_cells`` and ``proportion_pct``.

### `cluster_annotation_matrix(adata, *, cluster_key: str, key: str='cell_type') -> pd.DataFrame`

For each cluster, the fraction of its cells given each label.

:param cluster_key: The ``obs`` column with cluster labels.
:param key: The ``obs`` column with cell-type labels. Default ``"cell_type"``.
:returns: One row per cluster (first column named after *cluster_key*), one column per label;
    empty when either column is missing.

### `annotation_figure(adata, *, key: str='cell_type', basis: str | None=None)`

A scatter plot of the 2-D embedding coloured by cell type.

:param key: The ``obs`` column to colour by. Default ``"cell_type"``.
:param basis: The ``obsm`` key to plot. Default: the first of ``X_umap``, ``X_tsne``, ``X_pca``.
:returns: A matplotlib Figure.
:raises KeyError: no embedding is present.

<!-- api:end -->

## Methods and parameters

| Method | Needs | Labels | Defaults and their source |
|---|---|---|---|
| `markers` | a cluster column | one per cluster | built-in human marker set (PBMC, brain, stroma); give `markers` or `marker_file` for other tissues |
| `manual` | a cluster column and a mapping from the user | one per cluster | none |
| `celltypist` | log1p-normalised `X` (target sum 10,000) | per cell | `model="Immune_All_Low"` (CellTypist's general immune model), `majority_voting=False` |
| `popv`, `knnpredict` | a labelled reference `.h5ad` with `obs["cell_type"]` | per cell | `reference` must be a path for these two |
| `singler`, `scmap` | R with SingleR or scmap, celldex, zellkonverter | per cell | `reference="HPCA"` (celldex's Human Primary Cell Atlas) |
| `scsa` | a cluster column; network for the CellMarker 2.0 table on first use | one per cluster | `species="Human"`, `tissue="All"`, `foldchange=1.5`, `pvalue=0.05` (pySCSA's defaults) |

Choosing: with a matching reference, prefer `knnpredict` or `popv`; for blood or
immune tissue without one, `celltypist`; when the user knows the markers,
`markers` with their list or `manual`. Labels are hypotheses: report the
method, the reference or model, and the markers that support each label.

## Gotchas

- **`celltypist` falls back to `markers` silently.** On a non-normalised `X`, missing model or any CellTypist error it runs marker scoring instead. Check `run_info(adata)["summary"]["actual_method"]`; `fallback_reason` says why.
- **`popv`'s backend is chosen at run time** (scvi, scanvi or a classical one, by what is installed); `summary["backend"]` records it.
- **R methods fail hard when R returns nothing** (`RuntimeError`). Check `Rscript` and the packages before choosing them.
- **`manual` needs `manual_map` or `manual_map_file`** (`ValueError` otherwise). Inline form: `"0=T cell;1,2=Myeloid"`.
- **A marker file that cannot be read** raises `FileNotFoundError`, an empty one `ValueError`.
- **`Unknown` everywhere means the markers do not fit the data.** All clusters `Unknown` with `markers` usually means the wrong tissue or organism; switch method or ask the user for markers rather than reporting it.

## Inputs and outputs

- Reads the cluster column (`cluster_key`, default from the matrix contract or `leiden` / `louvain`), normalised `X`, and for `celltypist` / R methods the counts it rebuilds from `layers['counts']` or `raw`.
- Writes `obs['cell_type']`, `obs['annotation_score']` (when the method scores), `obs['annotation_requested_method']`, `obs['annotation_actual_method']`, `obs['annotation_method']`, `uns['annotation_runtime']`; `celltypist` also `obsm['cell_type_prob']`.
- `annotation_table` and `cluster_annotation_matrix` return DataFrames; `annotation_figure` returns a matplotlib Figure.

## CLI

`sc_annotate.py` runs the same functions outside a project and writes a
report, figures, tables and `processed.h5ad`:
`python <skill directory>/sc_annotate.py --help`. `--demo` runs it on PBMC3k.

## See also

- `references/parameters.md` — every CLI flag, per-method parameter hints
- `references/methodology.md` — when each backend wins; reference / model notes
- `references/output_contract.md` — `obs["cell_type"]` / `obsm["cell_type_prob"]` / `result.json` keys
- Adjacent skills: `sc-clustering` (upstream — produces the cluster column), `sc-markers` (parallel — ranks the marker genes that *justify* a label; can be run before or after), `sc-de` (downstream — replicate-aware condition DE between labelled groups)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `celltypist`, `matplotlib`, `numpy`, `pandas`, `popv`, `scanpy`, `scipy`, `seaborn`
