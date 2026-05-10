---
name: sc-clustering
description: Load when building the neighbour graph, embedding (UMAP/t-SNE/diffmap/PHATE), and clustering (Leiden/Louvain) on a normalised single-cell AnnData. Skip when QC/normalisation/HVG/PCA have not run yet (use sc-preprocessing) or for marker ranking after clustering (use sc-markers).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- clustering
- leiden
- louvain
- umap
- tsne
- phate
requires:
- anndata
- scanpy
- numpy
---

# sc-clustering

## When to use

The user has a normalised AnnData with PCA / integrated embedding
already populated and wants the standard scRNA neighbour-graph →
embedding → cluster workflow.  Combinable in one call: pick an
embedding method (`umap` default, also `tsne` / `diffmap` / `phate`)
and a clustering method (`leiden` default, also `louvain`), with an
explicit resolution or auto-resolution search.  Designed to read from
`obsm["X_pca"]` / `obsm["X_harmony"]` / etc. via `--use-rep`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Normalised AnnData | `.h5ad` with `obsm["X_pca"]` (or `--use-rep <key>`) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Clustered AnnData | `processed.h5ad` | adds `obs["leiden"]` / `obs["louvain"]`, `obsm["X_<embedding>"]` |
| Per-cluster summary | `tables/cluster_summary.csv` | cells per cluster |
| Run-level summary | `tables/clustering_summary.csv` | resolution, n_clusters, modularity |
| Embedding points | `tables/embedding_points.csv` | per-cell embedding coordinates |
| Diagnostic figures | `figures/auto_resolution_search.png` (when auto-tuning), embedding gallery | rendered as gallery |
| Report | `report.md` + `result.json` | always written |

## Flow

1. Load AnnData; pick embedding source (`--use-rep` or default).
2. If `--resolution` is `auto` or a sweep range, run the auto-resolution search and write `figures/auto_resolution_search.png`.
3. Build the neighbour graph (`--n-neighbors` × `--n-pcs`).
4. Compute the chosen `--embedding-method` low-dim embedding.
5. Cluster with `--cluster-method` at the chosen `--resolution`.
6. Render the embedding gallery + cluster-summary tables; emit `report.md` + `result.json`.

## Gotchas

- **No embedding source → hard fail.** `sc_cluster.py:336` raises `ValueError("No embedding available for clustering.")` when neither `obsm["X_pca"]` is present nor `--use-rep` is set to a valid `obsm` key.  Run `sc-preprocessing` (or `sc-batch-integration` for a multi-sample dataset) before this skill, or pass `--use-rep X_pca` explicitly when the input has a non-default embedding name.
- **`--input` is required without `--demo`.** `sc_cluster.py:851` raises `ValueError("--input required when not using --demo")`.  Common when running in a pipeline where the upstream step didn't write a valid path.
- **`--resolution` accepts a string for sweep mode.** Numeric values run a single resolution; literal `auto` triggers the auto-resolution search; comma-separated like `0.3,0.6,1.0` runs each and picks via the silhouette criterion logged in `tables/clustering_summary.csv`.
- **The skill writes the chosen `--cluster-method` column verbatim into `obs`.** `obs["leiden"]` (or `obs["louvain"]`) overwrites any pre-existing column with that name.  Save the input separately if you need to compare the new clustering against a prior one.

## Key CLI

```bash
# Demo (built-in PBMC3K, Leiden + UMAP)
python omicsclaw.py run sc-clustering --demo --output /tmp/sc_cluster_demo

# Default Leiden on integrated embedding
python omicsclaw.py run sc-clustering \
  --input integrated.h5ad --output results/ \
  --use-rep X_harmony --resolution 1.0

# Auto-resolution sweep with t-SNE embedding
python omicsclaw.py run sc-clustering \
  --input preprocessed.h5ad --output results/ \
  --embedding-method tsne --resolution auto

# PHATE embedding + Louvain
python omicsclaw.py run sc-clustering \
  --input preprocessed.h5ad --output results/ \
  --embedding-method phate --cluster-method louvain --n-neighbors 30
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — embedding choice guide, auto-resolution heuristic
- `references/output_contract.md` — `obs` / `obsm` keys + table schemas
- Adjacent skills: `sc-preprocessing` (upstream — normalise/HVG/PCA before this), `sc-batch-integration` (parallel — produces the integrated embedding `--use-rep` reads from), `sc-markers` (downstream — rank cluster markers from `obs["leiden"]`)
