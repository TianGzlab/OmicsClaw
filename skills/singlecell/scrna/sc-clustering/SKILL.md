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
explicit resolution or auto-resolution search.  Designed to read from
`obsm["X_pca"]` / `obsm["X_harmony"]` / etc. via `--use-rep`.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)
- Expects `obsm`: `X_pca`

**Outputs**

- `tables/cell_metadata.csv`
- `tables/cluster_qc_summary.csv`
- `tables/cluster_summary.csv`
- `tables/clustering_summary.csv`
- `tables/embedding_points.csv`
- `figures/auto_resolution_search.png`
- `figures/cluster_qc_heatmap.png`
- `figures/cluster_size_summary.png`
- `figures/embedding_clusters.png`
- `figures/embedding_comparison.png`
- `figures/pca_scatter.png`
- `figures/pca_variance.png`
- `figures/r_cell_barplot.png`
- `figures/r_cell_proportion.png`
- `figures/r_embedding_discrete.png`
- `figures/r_embedding_feature.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `leiden`, `louvain`; `obsm`: `X_<embedding>`

## Flow

1. Load AnnData; pick embedding source (`--use-rep` or default).
2. If `--resolution` is `auto`, run the auto-resolution search and write `figures/auto_resolution_search.png`; otherwise parse it as a single float.
3. Build the neighbour graph (`--n-neighbors` × `--n-pcs`).
4. Compute the chosen `--embedding-method` low-dim embedding.
5. Cluster with `--cluster-method` at the chosen `--resolution`.
6. Render the embedding gallery + cluster-summary tables; emit `report.md` + `result.json`.

## Gotchas

- **No embedding source → hard fail.** `sc_cluster.py` raises `ValueError("No embedding available for clustering.")` when neither `obsm["X_pca"]` is present nor `--use-rep` is set to a valid `obsm` key.  Run `sc-preprocessing` (or `sc-batch-integration` for a multi-sample dataset) before this skill, or pass `--use-rep X_pca` explicitly when the input has a non-default embedding name.
- **`--input` is required without `--demo`.** `sc_cluster.py` raises `ValueError("--input required when not using --demo")`.  Common when running in a pipeline where the upstream step didn't write a valid path.
- **`--resolution` is either a single float or the literal `auto`.** `sc_cluster.py` parses `args.resolution`: if `lower() == "auto"` it triggers the auto-resolution search; otherwise it calls `float(args.resolution)`.  Comma-separated values (`"0.3,0.6,1.0"`) raise `ValueError` from `float()` — there is no built-in multi-value sweep mode beyond `auto`.
- **The skill writes the chosen `--cluster-method` column verbatim into `obs`.** `obs["leiden"]` (or `obs["louvain"]`) overwrites any pre-existing column with that name.  Save the input separately if you need to compare the new clustering against a prior one.

## Key CLI

```bash
# Demo (built-in PBMC3K, Leiden + UMAP)
python skills/singlecell/scrna/sc-clustering/sc_cluster.py --demo --output /tmp/sc_cluster_demo

# Default Leiden on integrated embedding
python skills/singlecell/scrna/sc-clustering/sc_cluster.py \
  --input integrated.h5ad --output results/ \
  --use-rep X_harmony --resolution 1.0

# Auto-resolution search with t-SNE embedding
python skills/singlecell/scrna/sc-clustering/sc_cluster.py \
  --input preprocessed.h5ad --output results/ \
  --embedding-method tsne --resolution auto

# PHATE embedding + Louvain
python skills/singlecell/scrna/sc-clustering/sc_cluster.py \
  --input preprocessed.h5ad --output results/ \
  --embedding-method phate --cluster-method louvain --n-neighbors 30
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — embedding choice guide, auto-resolution heuristic
- `references/output_contract.md` — `obs` / `obsm` keys + table schemas
- Adjacent skills: `sc-preprocessing` (upstream — normalise/HVG/PCA before this), `sc-batch-integration` (parallel — produces the integrated embedding `--use-rep` reads from), `sc-markers` (downstream — rank cluster markers from `obs["leiden"]`)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `louvain`, `matplotlib`, `numpy`, `pandas`, `phate`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`
