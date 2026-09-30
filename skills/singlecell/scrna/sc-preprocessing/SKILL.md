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

The user has a filtered, QC-annotated AnnData and wants the standard
"normalise → HVG → PCA" pipeline before clustering or batch
integration. Four interchangeable backends are available: `scanpy`
(default; CP10k log + HVG seurat flavour), `seurat` (R-backed
LogNormalize / CLR / RC), `sctransform` (R-backed regularised NB), and
`pearson_residuals` (raw-count HVG selection plus Pearson residual
transformation). The skill stops at PCA — UMAP / clustering live in
`sc-clustering`, multi-sample correction in `sc-batch-integration`.

## Inputs & Outputs

**Inputs**

- Modalities: scrna
- File types: `.h5ad`

**Outputs**

- `tables/X_norm.csv`
- `tables/cell_metadata.csv`
- `tables/cluster_summary.csv`
- `tables/embedding_points.csv`
- `tables/gene_expression.csv`
- `tables/hvg.csv`
- `tables/hvg_summary.csv`
- `tables/obs.csv`
- `tables/pca.csv`
- `tables/pca_embedding.csv`
- `tables/pca_variance_ratio.csv`
- `tables/preprocess_summary.csv`
- `tables/qc_metrics_per_cell.csv`
- `figures/highly_variable_genes.png`
- `figures/pca_variance.png`
- `figures/qc_violin.png`
- `figures/r_hvg_violin.png`
- `analysis_summary.txt`
- `info.json`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obsm`: `X_pca`; `var`: `highly_variable`; `layers`: `counts`
- AnnData processing state after success: `preprocessed`

## Flow

1. Load AnnData; infer species; canonicalise gene-name / expression layout via the shared single-cell standardiser.
2. Reuse existing QC if `n_genes_by_counts` / `total_counts` / `pct_counts_mt` are present in `obs`; otherwise compute them.
3. Apply shared filtering (`--min-genes`, `--min-cells`, `--max-mt-pct`); drop doublets when `predicted_doublet` / `doublet_score` columns are present (opt out via `--no-remove-doublets`).
4. Run the chosen normalisation backend (`scanpy` / `seurat` / `sctransform` / `pearson_residuals`).
5. Select HVGs (`--n-top-hvg`) and compute PCA (`--n-pcs`).
6. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **`result.json["n_pcs_used"]` may be smaller than the requested `--n-pcs`.** `sc_preprocess.py` reads `obsm["X_pca"].shape[1]` after PCA — small matrices cap the count below the request. Trust `n_pcs_used`, not the input flag, when handing off to `sc-clustering --n-pcs`.
- **R-backed `seurat` / `sctransform` need a working `Rscript` env.** `sc_preprocess.py` raises `RuntimeError("Seurat preprocessing returned no overlapping cells or genes")` when the R round-trip empties the matrix; raises `RuntimeError("Seurat preprocessing returned PCA rows that do not align with exported cells")` when the R-side PCA shape disagrees with the cell list. Confirm `Seurat`, `SingleCellExperiment`, `zellkonverter` (and `sctransform` for that method) are installed before picking these methods.
- **Doublet filter is on-by-default whenever `sc-doublet-detection` ran.** `sc_preprocess.py` passes `filter_doublets=True` and `doublet_score_threshold=0.25` when those columns exist in `obs`. To keep the called-doublet rows, pass `--no-remove-doublets`.
- **`figure_data/gene_expression.csv` write failures are silent.** `sc_preprocess.py` catches the exception and only logs a warning — `figure_data/manifest.json` is the source of truth for which figure-data files actually landed.
- **`--input` is mandatory unless `--demo`.** `sc_preprocess.py` raises `ValueError("--input required when not using --demo")`.

## Key CLI

```bash
# Demo (built-in synthetic data)
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py --demo --output /tmp/sc_preprocess_demo

# Default scanpy backend
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input filtered.h5ad --output results/

# R-backed Seurat LogNormalize
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input filtered.h5ad --output results/ \
  --method seurat --seurat-normalize-method LogNormalize

# Pearson residuals (recommended for very sparse / heterogeneous data)
python skills/singlecell/scrna/sc-preprocessing/sc_preprocess.py \
  --input filtered.h5ad --output results/ \
  --method pearson_residuals --n-top-hvg 3000
```

## See also

- `references/parameters.md` — every CLI flag and per-method tuning hint
- `references/methodology.md` — when each backend wins; canonicalisation contract
- `references/output_contract.md` — `obs` / `obsm` / `layers` / `uns` schema + table layouts
- Adjacent skills: `sc-qc` / `sc-filter` (upstream — produce the input), `sc-batch-integration` (parallel — multi-sample alternative path; consumes `obsm["X_pca"]`), `sc-clustering` (downstream — consumes `obsm["X_pca"]` for neighbour-graph + UMAP + Leiden)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `phate`, `scanpy`, `scipy`, `seaborn`
