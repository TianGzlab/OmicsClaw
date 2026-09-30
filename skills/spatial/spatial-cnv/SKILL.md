---
name: spatial-cnv
description: Load when inferring copy-number variation per spot on a preprocessed spatial AnnData with
  chromosome-annotated genes via infercnvpy (default — log-ratio sliding-window) or Numbat (R, allele-aware
  clone deconvolution). Skip when `var["chromosome"]` / `var["start"]` / `var["end"]` gene-coord metadata
  is missing; no normal-reference subset can be defined.
trigger: copy number variation, CNV, inferCNV, infercnvpy, Numbat, aneuploidy, chromosomal aberration, tumor clone
tags:
- spatial
- cnv
- copy-number
- infercnvpy
- numbat
- tumor
---

# spatial-cnv

## When to use

The user has a preprocessed spatial AnnData with gene-coordinate
metadata in `var["chromosome"]` / `var["start"]` / `var["end"]` and
wants per-spot copy-number variation inferred for tumour / normal
deconvolution. Two backends:

- `infercnvpy` (default) — log-ratio sliding-window over chromosomes
  using `infercnvpy`. Tunables `--window-size`, `--step`,
  `--infercnv-lfc-clip`, `--infercnv-chunksize`, `--infercnv-n-jobs`.
- `numbat` — R-based, allele-aware clone deconvolution using
  phased SNP allele counts. Requires `obsm["allele_counts"]`.
  Tunables `--numbat-genome` (`hg19`/`hg38`), `--numbat-max-entropy`,
  `--numbat-min-llr`, `--numbat-min-cells`, `--numbat-ncores`.

`--reference-key <obs col>` + `--reference-cat <category>` define
the normal-reference subset (strongly recommended).

## Inputs & Outputs

**Inputs**

- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)
- Expects `obsm`: `spatial`, `allele_counts`

**Outputs**

- `tables/allele_counts.csv`
- `tables/cnv_bin_summary.csv`
- `tables/cnv_group_sizes.csv`
- `tables/cnv_run_summary.csv`
- `tables/cnv_scores.csv`
- `tables/cnv_spatial_points.csv`
- `tables/cnv_umap_points.csv`
- `tables/numbat_calls.csv`
- `tables/numbat_clone_post.csv`
- `tables/numbat_results.csv`
- `figures/cnv_bin_summary.png`
- `figures/cnv_group_sizes.png`
- `figures/cnv_groups_umap.png`
- `figures/cnv_heatmap.png`
- `figures/cnv_score_distribution.png`
- `figures/cnv_spatial.png`
- `figures/cnv_umap.png`
- `figures/cnv_uncertainty_distribution.png`
- `figures/cnv_uncertainty_spatial.png`
- `numbat_input.h5ad`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `cnv_score`, `cnv_leiden`, `numbat_p_cnv`, `numbat_clone`, `numbat_entropy`; `uns`: `numbat_calls`, `numbat_clone_post`

## Flow

1. Load AnnData (`--input`) or build a demo with synthetic gene-coords (`spatial_cnv.py`). For Numbat, validate `obsm["allele_counts"]` (`_lib/cnv.py`).
2. Sync `obsm["spatial"]` ↔ `obsm["X_spatial"]`; cast `obs["cnv_leiden"]` and `obs["numbat_clone"]` outputs to Categorical (`spatial_cnv.py`). The user-supplied `--reference-key` column is NOT cast.
3. For `infercnvpy`: run `cnv.tl.infercnv` → `cnv.tl.pca` → `cnv.tl.leiden` → `cnv.tl.cnv_score` (`_lib/cnv.py`).
4. For `numbat`: invoke R Numbat via the adapter; read clone posterior + per-cell entropy; write to `uns` + `obs` (`_lib/cnv.py`).
5. Compute per-clone group sizes + per-bin mean CNV (`spatial_cnv.py`).
6. Render heatmap / spatial / UMAP / clone-overlay / score-distribution / uncertainty plots.
7. Save tables + `processed.h5ad` + report.

## Gotchas

- **`var["chromosome"]` / `var["start"]` / `var["end"]` REQUIRED.** Without per-gene genomic coordinates, infercnvpy cannot bin genes by chromosome. The `--demo` path injects synthetic coords (`spatial_cnv.py`); for real data, run gene-coord lookup (Ensembl / GENCODE) upstream.
- **No `--reference-key` ⇒ per-cell baseline drift.** When no normal reference is set, infercnvpy treats the cohort mean as baseline, which inflates CNV calls in homogeneous tumour samples. Always pass `--reference-key cell_type --reference-cat Normal` (or analogous).
- **Numbat needs `obsm["allele_counts"]` AND raw counts.** `_lib/cnv.py` raises `ValueError` if allele counts are missing; raw counts come from `adata.layers["counts"]`. Build the allele-count DataFrame upstream from phased VCFs (Numbat docs).
- **`obs["cnv_leiden"]` has a no-cluster fallback.** `_lib/cnv.py` writes `pd.Categorical(np.repeat("cnv_all", adata.n_obs))` when leiden clustering fails (e.g. degenerate CNV PCA). Inspect `cnv_run_summary.csv` to distinguish "1 clone" (real) from "fallback" (failure).
- **`--step` must be ≤ `--window-size`.** `spatial_cnv.py` rejects with `parser.error` when violated. Default window 100, step 10 ≈ 90% overlap.
- **`obs["cnv_score"]` is set by infercnvpy's `cnv.tl.cnv_score`.** OmicsClaw only fills NaNs (`_lib/cnv.py`) — don't expect this column when `--method numbat`; Numbat writes `obs["numbat_p_cnv"]` instead.

## Key CLI

```bash
# Demo
python skills/spatial/spatial-cnv/spatial_cnv.py --demo --output /tmp/cnv_demo

# infercnvpy with explicit normal reference (default)
python skills/spatial/spatial-cnv/spatial_cnv.py \
  --input preprocessed.h5ad --output results/ \
  --method infercnvpy \
  --reference-key cell_type --reference-cat Normal Stromal \
  --window-size 100 --step 10 --infercnv-n-jobs 4

# Numbat (R, allele-aware) — requires obsm["allele_counts"]
python skills/spatial/spatial-cnv/spatial_cnv.py \
  --input preprocessed_with_alleles.h5ad --output results/ \
  --method numbat --numbat-genome hg38 \
  --numbat-min-llr 5.0 --numbat-min-cells 50 --numbat-ncores 4
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins; reference choice
- `references/output_contract.md` — per-method `obs` / `uns` keys
- Adjacent skills: `spatial-preprocess` (upstream), `spatial-domains` (upstream — provides `obs["leiden"]` for cluster overlays), `spatial-annotate` (upstream — provides `obs[cell_type]` for `--reference-cat`), `spatial-condition` (parallel — DE between conditions), `spatial-trajectory` (parallel — clonal lineage if combined with CNV)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `infercnvpy`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
