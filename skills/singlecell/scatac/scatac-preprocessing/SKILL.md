---
name: scatac-preprocessing
description: Load when preprocessing a single-cell ATAC peak × cell AnnData via Signac-style TF-IDF +
  LSI + Leiden, producing a clustered UMAP-ready object. Skip when input is fragments; BAM (peak calling
  not implemented here); scRNA preprocessing (use sc-preprocessing).
trigger: scATAC preprocessing, single-cell ATAC preprocessing, ATAC TF-IDF LSI, chromatin accessibility clustering, scATAC UMAP Leiden
tags:
- singlecell
- scatac
- atac
- preprocessing
- tfidf
- lsi
- clustering
- leiden
---

# scatac-preprocessing

## When to use

The user has a peak × cell scATAC AnnData (raw-count-like accessibility
matrix in `.X`) and wants the standard "filter → TF-IDF → LSI → graph →
UMAP → Leiden" pipeline in one shot. Currently a single backend:
`tfidf_lsi` (Signac-style). The skill stops at clustered UMAP — no
fragment QC, no peak calling, no motif / gene-activity scoring, no
multi-sample integration. For scRNA preprocessing use `sc-preprocessing`.

## Inputs & Outputs

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: scatac
- File types: `.h5ad`, `.h5`, `.loom`, `.csv`, `.tsv`

**Outputs**

- `tables/cell_metadata.csv`
- `tables/cluster_summary.csv`
- `tables/lsi_variance_ratio.csv`
- `tables/peak_summary.csv`
- `tables/preprocess_summary.csv`
- `tables/qc_metrics_per_cell.csv`
- `tables/umap_points.csv`
- `figures/clustering_comparison.png`
- `figures/feature_umap.png`
- `figures/lsi_variance.png`
- `figures/pca_loadings.png`
- `figures/pca_scatter.png`
- `figures/pca_variance.png`
- `figures/qc_violin.png`
- `figures/top_accessible_peaks.png`
- `analysis_summary.txt`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `leiden`; `obsm`: `X_lsi`, `X_umap`; `layers`: `counts`
- AnnData processing state after success: `preprocessed`

## Flow

1. Load the peak × cell input via the shared `smart_load` (AnnData / 10x H5 / loom / CSV / 10x dir).
2. Validate `.X` is present, non-empty, non-negative.
3. Compute per-cell `n_peaks_by_counts` / `total_counts`; filter cells by `--min-peaks` and peaks by `--min-cells`.
4. Retain the globally most accessible peaks up to `--n-top-peaks`.
5. Run Signac-style TF-IDF (`--tfidf-scale-factor`); truncated-SVD LSI to `--n-lsi` components.
6. Build neighbour graph (`--n-neighbors`), UMAP, Leiden (`--leiden-resolution`).
7. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **Filtering can wipe everything.** `scatac_preprocessing.py` raises `RuntimeError("All cells were removed by `min_peaks`. Lower the threshold.")` and raises `RuntimeError("All peaks were removed by `min_cells`. Lower the threshold.")` — both are hard fails. Inspect `n_peaks_by_counts` distribution before tightening these thresholds; `--min-peaks 200` (default) assumes a typical 10x scATAC depth.
- **LSI hard-fails on a degenerate matrix.** `scatac_preprocessing.py` raises `RuntimeError("Not enough cells or peaks remain to compute a stable LSI embedding.")` when the matrix is too sparse / small after filtering. Either lower QC thresholds or feed a richer dataset.
- **Input must be non-negative count-like in `.X`.** `scatac_preprocessing.py` raises `ValueError("Input AnnData has no matrix in adata.X.")`; raises `ValueError("Input matrix is empty.")`; raises `ValueError("scATAC preprocessing requires a non-negative accessibility matrix.")`. Already-TF-IDF-transformed data will fail the non-negativity check.
- **`processed.h5ad` keeps only retained peaks.** `scatac_preprocessing.py` does `adata = adata[:, keep].copy()` — `var` is filtered to the top `n_top_peaks` accessible. The original peak universe is **not** preserved in `X` (the deleted peaks are gone). Snapshot the input before running if you need the full peak space later.
- **`--input` mandatory unless `--demo`.** `scatac_preprocessing.py` raises `ValueError("--input required when not using --demo")`.
- **Single backend only.** `scatac_preprocessing.py` raises `ValueError(f"Unknown preprocessing method '{method}'")` for anything other than `tfidf_lsi`. The `--method` flag exists for forward compatibility; today it's effectively a no-op.

## Key CLI

```bash
# Demo (built-in synthetic scATAC)
python skills/singlecell/scatac/scatac-preprocessing/scatac_preprocessing.py --demo --output /tmp/scatac_demo

# Standard run on a 10x scATAC h5
python skills/singlecell/scatac/scatac-preprocessing/scatac_preprocessing.py \
  --input atac_peaks.h5 --output results/

# Tune QC + feature budget
python skills/singlecell/scatac/scatac-preprocessing/scatac_preprocessing.py \
  --input atac_peaks.h5ad --output results/ \
  --min-peaks 300 --min-cells 10 --n-top-peaks 20000

# Tune latent space + clustering
python skills/singlecell/scatac/scatac-preprocessing/scatac_preprocessing.py \
  --input atac_peaks.h5ad --output results/ \
  --n-lsi 40 --n-neighbors 20 --leiden-resolution 1.0
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — TF-IDF + LSI math; Signac alignment
- `references/output_contract.md` — `obsm`/`var` schema + table layouts
- Adjacent skills: `sc-preprocessing` (parallel — scRNA, NOT scATAC), `sc-clustering` (downstream — re-cluster on `obsm["X_lsi"]` if you want a different resolution without re-running TF-IDF)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `phate`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`
