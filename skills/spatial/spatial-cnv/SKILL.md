---
name: spatial-cnv
description: Load when inferring copy-number variation per spot on a preprocessed spatial AnnData with chromosome-annotated genes via infercnvpy (default — log-ratio sliding-window) or Numbat (R, allele-aware clone deconvolution). Skip when `var["chromosome"]` / `var["start"]` / `var["end"]` gene-coord metadata is missing or when no normal-reference subset can be defined.
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- spatial
- cnv
- copy-number
- infercnvpy
- numbat
- tumor
requires:
- anndata
- scanpy
- numpy
- pandas
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

| Input | Format | Required |
|---|---|---|
| Preprocessed spatial AnnData | `.h5ad` with `obsm["spatial"]`, `var["chromosome"]` + `var["start"]` + `var["end"]` (gene-coord metadata); raw counts in `layers["counts"]` for Numbat | yes (unless `--demo`) |
| Reference subset | `--reference-key <obs col>` + `--reference-cat <category>` | strongly recommended (else inferred per-cell drift) |
| Numbat allele counts | `obsm["allele_counts"]` (DataFrame-like) | required for `--method numbat` |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | infercnvpy: `obs["cnv_score"]` (set by `cnv.tl.cnv_score`, `_lib/cnv.py:219`; NaNs filled at `_lib/cnv.py:226`), `obs["cnv_leiden"]` (set by `cnv.tl.leiden` at `_lib/cnv.py:210`; constant fallback `_lib/cnv.py:216`); Numbat: `uns["numbat_calls"]`, `uns["numbat_clone_post"]` (DataFrames as records), `obs["numbat_p_cnv"]`, `obs["numbat_clone"]`, `obs["numbat_entropy"]` (`_lib/cnv.py:344-366`) |
| Per-spot scores | `tables/cnv_scores.csv` | per-spot CNV score |
| Run summary | `tables/cnv_run_summary.csv` | params used |
| Group sizes | `tables/cnv_group_sizes.csv` | per-clone count + proportion |
| Bin profile | `tables/cnv_bin_summary.csv` | per-genomic-bin mean CNV |
| Numbat tables | `tables/numbat_calls.csv`, `tables/numbat_clone_post.csv` | Numbat only |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or build a demo with synthetic gene-coords (`spatial_cnv.py:982-991`). For Numbat, validate `obsm["allele_counts"]` (`_lib/cnv.py:93`).
2. Sync `obsm["spatial"]` ↔ `obsm["X_spatial"]`; cast `obs["cnv_leiden"]` and `obs["numbat_clone"]` outputs to Categorical (`spatial_cnv.py:84-86`). The user-supplied `--reference-key` column is NOT cast.
3. For `infercnvpy`: run `cnv.tl.infercnv` (`_lib/cnv.py:171`) → `cnv.tl.pca` (`_lib/cnv.py:188`) → `cnv.tl.leiden` (`_lib/cnv.py:210`) → `cnv.tl.cnv_score` (`_lib/cnv.py:219`).
4. For `numbat`: invoke R Numbat via the adapter; read clone posterior + per-cell entropy; write to `uns` + `obs` (`_lib/cnv.py:344-366`).
5. Compute per-clone group sizes + per-bin mean CNV (`spatial_cnv.py:175-177`).
6. Render heatmap / spatial / UMAP / clone-overlay / score-distribution / uncertainty plots.
7. Save tables + `processed.h5ad` + report.

## Gotchas

- **`var["chromosome"]` / `var["start"]` / `var["end"]` REQUIRED.** Without per-gene genomic coordinates, infercnvpy cannot bin genes by chromosome. The `--demo` path injects synthetic coords (`spatial_cnv.py:989-991`); for real data, run gene-coord lookup (Ensembl / GENCODE) upstream.
- **No `--reference-key` ⇒ per-cell baseline drift.** When no normal reference is set, infercnvpy treats the cohort mean as baseline, which inflates CNV calls in homogeneous tumour samples. Always pass `--reference-key cell_type --reference-cat Normal` (or analogous).
- **Numbat needs `obsm["allele_counts"]` AND raw counts.** `_lib/cnv.py:93` raises `ValueError` if allele counts are missing; raw counts come from `adata.layers["counts"]` (`_lib/cnv.py:67`). Build the allele-count DataFrame upstream from phased VCFs (Numbat docs).
- **`obs["cnv_leiden"]` has a no-cluster fallback.** `_lib/cnv.py:216` writes `pd.Categorical(np.repeat("cnv_all", adata.n_obs))` when leiden clustering fails (e.g. degenerate CNV PCA). Inspect `cnv_run_summary.csv` to distinguish "1 clone" (real) from "fallback" (failure).
- **`--step` must be ≤ `--window-size`.** `spatial_cnv.py:1001-1002` rejects with `parser.error` when violated. Default window 100, step 10 ≈ 90% overlap.
- **`obs["cnv_score"]` is set by infercnvpy's `cnv.tl.cnv_score`.** OmicsClaw only fills NaNs (`_lib/cnv.py:226`) — don't expect this column when `--method numbat`; Numbat writes `obs["numbat_p_cnv"]` instead.

## Key CLI

```bash
# Demo
python omicsclaw.py run spatial-cnv --demo --output /tmp/cnv_demo

# infercnvpy with explicit normal reference (default)
python omicsclaw.py run spatial-cnv \
  --input preprocessed.h5ad --output results/ \
  --method infercnvpy \
  --reference-key cell_type --reference-cat Normal Stromal \
  --window-size 100 --step 10 --infercnv-n-jobs 4

# Numbat (R, allele-aware) — requires obsm["allele_counts"]
python omicsclaw.py run spatial-cnv \
  --input preprocessed_with_alleles.h5ad --output results/ \
  --method numbat --numbat-genome hg38 \
  --numbat-min-llr 5.0 --numbat-min-cells 50 --numbat-ncores 4
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins; reference choice
- `references/output_contract.md` — per-method `obs` / `uns` keys
- Adjacent skills: `spatial-preprocess` (upstream), `spatial-domains` (upstream — provides `obs["leiden"]` for cluster overlays), `spatial-annotate` (upstream — provides `obs[cell_type]` for `--reference-cat`), `spatial-condition` (parallel — DE between conditions), `spatial-trajectory` (parallel — clonal lineage if combined with CNV)
