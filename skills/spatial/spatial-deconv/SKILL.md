---
name: spatial-deconv
description: Load when deconvolving spot-level cell-type proportions on a Visium-style spatial AnnData
  using a labelled scRNA reference (FlashDeconv / Cell2location / RCTD / DestVI / Tangram / others). Skip
  when each spot is a single cell already (Xenium / MERFISH) (use spatial-annotate); tissue-domain detection
  (use spatial-domains).
trigger: cell type deconvolution, spatial deconvolution, cell proportion, cell type proportion, cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, CARD
tags:
- spatial
- deconvolution
- cell2location
- rctd
- destvi
- stereoscope
- tangram
- spotlight
- card
- flashdeconv
---

# spatial-deconv

## When to use

The user has a Visium-style multi-cell-per-spot spatial AnnData PLUS a
labelled scRNA reference AnnData and wants per-spot cell-type
proportions. Eight backends:

- `flashdeconv` (default) — ultra-fast O(N) CPU sketching. No GPU.
- `cell2location` — Bayesian deep learning with spatial priors
  (`--cell2location-n-epochs`, `--cell2location-detection-alpha`,
  `--cell2location-n-cells-per-spot`). Requires `scvi-tools` +
  `cell2location` + `torch`.
- `rctd` — Robust Cell Type Decomposition (R / `spacexr`).
- `destvi` — multi-resolution VAE (`--destvi-n-epochs`,
  `--destvi-n-hidden` / `--destvi-n-latent` / `--destvi-n-layers`).
  Requires `scvi-tools` + `torch`.
- `stereoscope` — two-stage probabilistic VAE
  (`--stereoscope-learning-rate`). Requires `scvi-tools` + `torch`.
- `tangram` — gradient-based mapping (`--tangram-n-epochs`,
  `--tangram-learning-rate`). Requires `tangram`.
- `spotlight` — NMF-based with marker-gene priors
  (`--spotlight-n-top`, `--spotlight-min-prop`, `--spotlight-weight-id`).
- `card` — Conditional Autoregressive R-based deconvolution.

For single-cell-per-spot platforms (Xenium / MERFISH) use
`spatial-annotate`. For tissue-region detection (no reference needed)
use `spatial-domains`.

## Inputs & Outputs

**Inputs**

- File types: `.h5ad`
- Requires a preprocessed AnnData (`X` normalised, PCA/neighbours present)
- Expects `obsm`: `spatial`

**Outputs**

- `tables/card_proportions.csv`
- `tables/card_refined_proportions.csv`
- `tables/celltype_diversity.csv`
- `tables/deconv_run_summary.csv`
- `tables/deconv_spatial_points.csv`
- `tables/deconv_spot_metrics.csv`
- `tables/deconv_umap_points.csv`
- `tables/dominant_celltype.csv`
- `tables/dominant_celltype_counts.csv`
- `tables/mean_proportions.csv`
- `tables/proportions.csv`
- `tables/rctd_proportions.csv`
- `tables/ref_celltypes.csv`
- `tables/ref_counts.csv`
- `tables/ref_meta.csv`
- `tables/spatial_coords.csv`
- `tables/spatial_counts.csv`
- `tables/spotlight_proportions.csv`
- `figures/assignment_margin_distribution.png`
- `figures/assignment_margin_spatial.png`
- `figures/celltype_diversity.png`
- `figures/dominant_celltype.png`
- `figures/dominant_celltype_distribution.png`
- `figures/mean_proportions.png`
- `figures/spatial_proportions.png`
- `figures/umap_proportions.png`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `deconv_{method}_dominant_cell_type`, `deconv_{method}_dominant_proportion`; `obsm`: `deconvolution_{method}`

## Flow

1. Load spatial AnnData + reference (`--reference` `.h5ad` with cell-type labels). For `flashdeconv` reference is optional (uses internal heuristic).
2. `parser.error` validates `--input` / `--reference` / numeric flags.
3. Dispatch to method; method-specific kwargs from `METHOD_PARAM_DEFAULTS`.
4. Build proportions matrix; compute per-spot dominant cell-type + Shannon diversity.
5. Save `processed.h5ad` (with `obsm["proportions"]`), tables, figures, `report.md`, `result.json`.

## Gotchas

- **All input + parameter validation goes through `parser.error` (exit code 2).** `spatial_deconv.py` for missing `--input`; for missing input path; for missing `--reference` on methods that need one; for missing reference path; for per-method numeric flag validation. Wrappers expecting `ValueError` need to catch exit-2.
- **`--reference` is required for almost every method** (only `flashdeconv` can run without it). `spatial_deconv.py` raises `parser.error(f"--reference is required for method '{args.method}'")` for the others. The reference must have cell-type labels in `obs` (key auto-resolved from common names).
- **`obsm["spatial"]` ↔ `obsm["X_spatial"]` sync in `_prepare_deconv_plot_state`.** Same dual-key pattern as spatial-domains — both keys exist after a run.
- **`--cell2location-detection-alpha` must be > 0.** `spatial_deconv.py` enforces. The cell2location default (typically 200) is a regularisation strength — lower values mean less spatial smoothing.
- **`--destvi-dropout-rate` is in `[0, 1)`, not `[0, 1]`.** `spatial_deconv.py` enforces strict-less-than-1. dropout=1 would zero out everything.
- **R-backed methods (`rctd`, `card`) need a working R env.** Both rely on R packages (`spacexr` for RCTD, `CARD` for CARD). Missing R deps surface as ImportError at runtime, not at preflight.

## Key CLI

```bash
# Demo (synthetic; flashdeconv default)
python skills/spatial/spatial-deconv/spatial_deconv.py --demo --output /tmp/spatial_deconv_demo

# FlashDeconv (CPU-only, fastest)
python skills/spatial/spatial-deconv/spatial_deconv.py \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method flashdeconv

# Cell2location (Bayesian, GPU)
python skills/spatial/spatial-deconv/spatial_deconv.py \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method cell2location --cell2location-n-epochs 30000 \
  --cell2location-n-cells-per-spot 8 --cell2location-detection-alpha 200

# RCTD (R-backed)
python skills/spatial/spatial-deconv/spatial_deconv.py \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method rctd --rctd-mode full

# Tangram (gradient mapping)
python skills/spatial/spatial-deconv/spatial_deconv.py \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method tangram --tangram-n-epochs 1000 --tangram-learning-rate 0.1

# CARD (Conditional Autoregressive R deconv)
python skills/spatial/spatial-deconv/spatial_deconv.py \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method card
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins; reference-data prep
- `references/output_contract.md` — `obsm["proportions"]` / `obs["dominant_celltype"]` schema
- Adjacent skills: `spatial-preprocess` (upstream — produces the input AnnData), `sc-cell-annotation` (upstream — labels the scRNA reference passed via `--reference`), `spatial-annotate` (parallel — for single-cell-per-spot platforms NOT spot deconvolution), `spatial-domains` (parallel — finds tissue regions WITHOUT a reference; complementary to deconv), `spatial-de` (downstream — DE between deconv-defined dominant-celltype groups)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `cell2location`, `flashdeconv`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `scvi-tools`, `seaborn`, `tangram-sc`, `torch`
