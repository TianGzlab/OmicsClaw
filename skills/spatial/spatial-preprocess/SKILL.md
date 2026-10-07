---
name: spatial-preprocess
description: Load when running the foundational spatial transcriptomics QC + filtering + normalisation
  + HVG + PCA + neighbour-graph + Leiden pipeline on a Visium / Xenium / generic spatial AnnData. Skip
  when raw FASTQs need converting first (use spatial-raw-processing); tissue-domain detection on already-preprocessed
  data (use spatial-domains).
trigger: preprocess, spatial preprocessing, spatial QC, normalize, visium, xenium, merfish, slide-seq, load spatial data, leiden, umap
tags:
- spatial
- visium
- xenium
- preprocessing
- qc
- normalization
- hvg
- pca
- leiden
---

# spatial-preprocess

## When to use

Use on raw-count spatial AnnData for QC, filtering, normalization, HVGs,
PCA, neighbors, UMAP and Leiden. The expression graph does not use spatial
coordinates. Use `spatial-raw-processing` for FASTQs and `spatial-domains`
for spatially informed domain detection on preprocessed data.

## Use from a step

```python
from skills._sdk.notebook import load_demo, load_skill, write_output

library = load_skill("spatial-preprocess")
adata = library.preprocess(load_demo("spatial_synthetic"), n_top_hvg=150, n_pcs=15)
write_output(adata, "intermediate/processed.h5ad")
write_output(library.cluster_summary(adata), "tables/clusters.csv")
```

The demo is synthetic, with three known spatial stripes. See
`examples/example_step.py` for count-preservation and domain-recovery checks.
For real H5AD input use `read_input("data/slide.h5ad")` instead of `load_demo`.

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `preprocess(adata, *, min_genes: int=0, min_cells: int=0, max_mt_pct: float=20.0, max_genes: int=0, n_top_hvg: int=2000, n_pcs: int=30, n_neighbors: int=15, leiden_resolution: float=0.5, resolutions: list[float] | None=None, tissue: str | None=None, species: str='human', random_state: int=0)`

Filter raw spatial counts and return a processed copy without changing the input.

Reads raw counts from ``X``. The returned ``X`` is total-normalized to
10,000 and log1p-transformed; ``layers['counts']`` and ``raw`` retain the
filtered counts. Adds QC metrics, HVGs, PCA, neighbors, UMAP and Leiden.
Coordinates are preserved but do not enter the expression neighbor graph.

:param adata: AnnData with raw counts in ``X`` and optional spatial coordinates.
:param min_genes: Minimum detected genes per spot; 0 disables this filter.
:param min_cells: Minimum spots per gene; 0 disables this filter.
:param max_mt_pct: Keep spots strictly below this percentage; 20 by default,
    100 disables the filter. Adjust for tissue and assay quality.
:param max_genes: Keep spots strictly below this detected-gene count;
    0 disables the upper bound.
:param n_top_hvg: Select up to 2000 HVGs from counts with Seurat v3 by default.
:param n_pcs: Request 30 PCs by default; clipped below both dimensions.
    Neighbors use at most 30 of the computed PCs.
:param n_neighbors: Graph neighborhood size, 15 by default.
:param leiden_resolution: Primary Leiden resolution, 0.5 by default.
:param resolutions: Optional positive resolutions for extra
    ``obs['leiden_res_<value>']`` columns; None skips the sweep.
:param tissue: Optional QC preset such as brain or pbmc. Values equal to
    the defaults (0, 20, 0) for min_genes, max_mt_pct and max_genes are
    replaced by the preset, even when passed explicitly. None uses no preset.
:param species: Human (default, ``MT-``) or mouse (``mt-``) mitochondrial prefix.
:param random_state: Seed for PCA, neighbors, UMAP and Leiden; default 0
    matches the original CLI. Change it to assess seed sensitivity.
:returns: A new AnnData with counts, embeddings, labels and JSON diagnostics.
:raises ValueError: Invalid thresholds or too few spots, genes or HVGs remain.
:raises ImportError: A backend is missing; use install_skill_deps for
    scikit-misc (HVGs), igraph (Leiden) or umap-learn (embedding).

### `run_info(adata, *, keep: bool=True) -> dict`

Read the QC counts, cluster sizes and effective parameters of the last run.

:param adata: AnnData returned by preprocess.
:param keep: True retains diagnostics; False removes them before CLI serialization.
:returns: A dict including random_state, effective_params and optional
    multi_resolution, or an empty dict if no record remains.

### `cluster_summary(adata) -> pd.DataFrame`

Count spots in each Leiden cluster, sorted by size then label.

:param adata: Processed AnnData with ``obs['leiden']``.
:returns: Columns cluster (string) and n_cells (spot count).
:raises KeyError: Leiden clustering has not been run.

### `qc_metrics_table(adata) -> pd.DataFrame`

Return available spot QC metrics and Leiden labels in observation order.

:param adata: AnnData after preprocessing or QC metric calculation.
:returns: observation followed by available n_genes_by_counts, total_counts,
    pct_counts_mt and leiden columns, matching the CLI's QC distribution table.

### `pca_variance_table(adata) -> pd.DataFrame`

Return explained and cumulative variance for each computed PC.

:param adata: Processed AnnData with PCA information in ``uns['pca']``.
:returns: Columns pc, variance_ratio, cumulative_variance_ratio and variance;
    an empty table before PCA, with NaN variance if only ratios are available.

### `spatial_figure(adata, *, color: str='leiden')`

Plot spot coordinates colored by an observation annotation, without saving.

:param adata: AnnData with ``obsm['spatial']`` or ``obsm['X_spatial']``.
:param color: Observation column; default leiden shows the expression clusters.
    A numeric column such as total_counts shows a continuous color scale.
:returns: A matplotlib Figure; the caller saves and closes it.
:raises ValueError: No spatial coordinates are available.
:raises KeyError: The color column is absent from obs.

<!-- api:end -->

## Methods and parameters

The single method is `scanpy_standard`. It normalizes each spot to 10,000
counts, applies log1p and selects Seurat v3 HVGs from preserved counts.
`preprocess` returns a copy. QC thresholds, HVG budget, PC count,
neighborhood size and Leiden resolution have the original CLI defaults.
The API accepts `random_state`; the CLI retains its fixed seed 0.

## Inputs & Outputs

The API takes AnnData with raw counts in `X`. Coordinates in `obsm['spatial']`
or `obsm['X_spatial']` are optional for computation and required for spatial plots.
The CLI reads spatial files or platform directories through `load_spatial_data`.

The returned object contains log-normalized `X`, filtered counts in `raw`
and `layers['counts']`, `obs['leiden']`, HVGs, PCA, neighbors and UMAP.
API calls write no analysis files; `write_output` records files from a step.

The CLI writes `processed.h5ad`, `report.md`, `result.json`, and
`tables/{cluster_summary,qc_summary,pca_variance_ratio}.csv`. A resolution
sweep also writes `tables/multi_resolution_summary.csv`.
`figure_data/` holds plot-ready QC, PCA, cluster and run-summary tables plus
UMAP points; spatial points and sweep tables depend on their inputs.
`figures/manifest.json` records the gallery status; spatial plots require
coordinates and the resolution-sweep plot requires a sweep.
`reproducibility/` holds `commands.sh`, `environment.txt` and `r_visualization.sh`.

## Gotchas

- `preprocess` expects counts in `X`; it does not infer another matrix or undo log normalization.
- `TISSUE_PRESETS` replaces default-valued `min_genes`, `max_mt_pct` and
  `max_genes`, even when explicitly supplied. It does not alter `min_cells`.
  `run_info(adata)['effective_params']` records the applied thresholds.
- `run_info(adata)['n_pcs_used']` can be below the requested PC count;
  use the recorded value for downstream analysis.
- Seurat v3 HVGs need `scikit-misc`; UMAP and Leiden need `umap-learn` and
  `igraph`. `preprocess` does not substitute another method when a backend is absent.
- The CLI's `_validate_args` uses exit code 2 for invalid non-demo arguments;
  the API raises `ValueError`. Computation failures still propagate.
- `run_info(adata, keep=False)` removes the JSON diagnostic record. The CLI
  does this before saving `processed.h5ad`; notebook outputs may retain it.

## CLI

```bash
python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/spatial_pp_demo

python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input visium.h5ad --output results/

python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input visium.h5ad --output results/ \
  --data-type visium --tissue brain --leiden-resolution 1.2

python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input visium.h5ad --output results/ \
  --resolutions 0.4,0.6,0.8,1.0,1.4
```

## See also

- `references/parameters.md` lists CLI defaults and tuning priorities.
- `references/methodology.md` discusses QC and resolution choices.
- `references/output_contract.md` lists CLI output paths and conditions.
- Use `spatial-integrate` for batch correction and `spatial-de` for cluster comparisons.

## Dependencies

Check these packages before starting a run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`, `scikit-misc`, `igraph`, `umap-learn`
