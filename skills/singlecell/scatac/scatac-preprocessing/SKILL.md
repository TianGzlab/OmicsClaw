---
name: scatac-preprocessing
description: Load when preprocessing a single-cell ATAC peak × cell AnnData via Signac-style TF-IDF + LSI + Leiden, producing a clustered UMAP-ready object. Skip when input is fragments or BAM (peak calling not implemented here) or for scRNA preprocessing (use sc-preprocessing).
version: 0.2.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scatac
- atac
- preprocessing
- tfidf
- lsi
- clustering
- leiden
requires:
- anndata
- scanpy
- numpy
- pandas
- scipy
- scikit-learn
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

| Input | Format | Required |
|---|---|---|
| Peak × cell AnnData | `.h5ad` (`.X` non-negative count-like) | yes (unless `--demo`) |
| Alternates | `.h5` (10x), `.loom`, `.csv`/`.tsv`, 10x directory | yes (loaded via `smart_load`) |

| Output | Path | Notes |
|---|---|---|
| Processed AnnData | `processed.h5ad` | retained peak space; `obsm["X_lsi"]`, `obsm["X_umap"]`, `obs["leiden"]`; raw counts kept in `layers["counts"]` |
| Run summary | `tables/preprocess_summary.csv` | always |
| Cluster sizes | `tables/cluster_summary.csv` | always |
| Top peaks | `tables/peak_summary.csv` | most accessible retained peaks |
| LSI variance | `tables/lsi_variance_ratio.csv` | per-component |
| Per-cell QC | `tables/qc_metrics_per_cell.csv` | always |
| Figures | `figures/umap_leiden.png`, `figures/qc_violin.png`, `figures/top_accessible_peaks.png`, `figures/lsi_variance.png` | always |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load the peak × cell input via the shared `smart_load` (AnnData / 10x H5 / loom / CSV / 10x dir).
2. Validate `.X` is present, non-empty, non-negative.
3. Compute per-cell `n_peaks_by_counts` / `total_counts`; filter cells by `--min-peaks` and peaks by `--min-cells`.
4. Retain the globally most accessible peaks up to `--n-top-peaks`.
5. Run Signac-style TF-IDF (`--tfidf-scale-factor`); truncated-SVD LSI to `--n-lsi` components.
6. Build neighbour graph (`--n-neighbors`), UMAP, Leiden (`--leiden-resolution`).
7. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **Filtering can wipe everything.** `scatac_preprocessing.py:149` raises `RuntimeError("All cells were removed by `min_peaks`. Lower the threshold.")` and `:154` raises `RuntimeError("All peaks were removed by `min_cells`. Lower the threshold.")` — both are hard fails. Inspect `n_peaks_by_counts` distribution before tightening these thresholds; `--min-peaks 200` (default) assumes a typical 10x scATAC depth.
- **LSI hard-fails on a degenerate matrix.** `scatac_preprocessing.py:228` raises `RuntimeError("Not enough cells or peaks remain to compute a stable LSI embedding.")` when the matrix is too sparse / small after filtering. Either lower QC thresholds or feed a richer dataset.
- **Input must be non-negative count-like in `.X`.** `scatac_preprocessing.py:118` raises `ValueError("Input AnnData has no matrix in adata.X.")`; `:122` raises `ValueError("Input matrix is empty.")`; `:124` raises `ValueError("scATAC preprocessing requires a non-negative accessibility matrix.")`. Already-TF-IDF-transformed data will fail the non-negativity check.
- **`processed.h5ad` keeps only retained peaks.** `scatac_preprocessing.py:176` does `adata = adata[:, keep].copy()` — `var` is filtered to the top `n_top_peaks` accessible. The original peak universe is **not** preserved in `X` (the deleted peaks are gone). Snapshot the input before running if you need the full peak space later.
- **`--input` mandatory unless `--demo`.** `scatac_preprocessing.py:809` raises `ValueError("--input required when not using --demo")`.
- **Single backend only.** `scatac_preprocessing.py:272` raises `ValueError(f"Unknown preprocessing method '{method}'")` for anything other than `tfidf_lsi`. The `--method` flag exists for forward compatibility; today it's effectively a no-op.

## Key CLI

```bash
# Demo (built-in synthetic scATAC)
python omicsclaw.py run scatac-preprocessing --demo --output /tmp/scatac_demo

# Standard run on a 10x scATAC h5
python omicsclaw.py run scatac-preprocessing \
  --input atac_peaks.h5 --output results/

# Tune QC + feature budget
python omicsclaw.py run scatac-preprocessing \
  --input atac_peaks.h5ad --output results/ \
  --min-peaks 300 --min-cells 10 --n-top-peaks 20000

# Tune latent space + clustering
python omicsclaw.py run scatac-preprocessing \
  --input atac_peaks.h5ad --output results/ \
  --n-lsi 40 --n-neighbors 20 --leiden-resolution 1.0
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — TF-IDF + LSI math; Signac alignment
- `references/output_contract.md` — `obsm`/`var` schema + table layouts
- Adjacent skills: `sc-preprocessing` (parallel — scRNA, NOT scATAC), `sc-clustering` (downstream — re-cluster on `obsm["X_lsi"]` if you want a different resolution without re-running TF-IDF)
