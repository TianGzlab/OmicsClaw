---
name: spatial-deconv
description: Load when deconvolving spot-level cell-type proportions on a Visium-style spatial AnnData using a labelled scRNA reference (FlashDeconv / Cell2location / RCTD / DestVI / Tangram / others). Skip when each spot is a single cell already (Xenium / MERFISH — use spatial-annotate) or for tissue-domain detection (use spatial-domains).
version: 0.5.0
author: OmicsClaw
license: MIT
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
requires:
- anndata
- scanpy
- numpy
- pandas
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

| Input | Format | Required |
|---|---|---|
| Spatial AnnData | `.h5ad` with `obsm["spatial"]` | yes (unless `--demo`) |
| scRNA reference | `.h5ad` with cell-type labels in `obs` (`--reference`) | required for all real-data methods |

| Output | Path | Notes |
|---|---|---|
| Annotated spatial AnnData | `processed.h5ad` | adds `obsm[f"deconvolution_{method}"]` (spots × cell-types; `spatial_deconv.py:592`) and per-method obs columns prefixed `deconv_{method}_` (e.g., `deconv_flashdeconv_dominant_cell_type`, `deconv_flashdeconv_dominant_proportion`; `:692-697`) |
| Proportions table | `tables/proportions.csv` | wide: rows = spots, cols = cell types |
| Per-spot metrics | `tables/deconv_spot_metrics.csv` | dominant celltype + diversity per spot |
| Dominant per-celltype | `tables/dominant_celltype_counts.csv` | always |
| Diversity index | `tables/celltype_diversity.csv` | Shannon-style per spot |
| Cross-method auxiliaries | `tables/dominant_celltype.csv`, `tables/mean_proportions.csv` | always |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load spatial AnnData + reference (`--reference` `.h5ad` with cell-type labels). For `flashdeconv` reference is optional (uses internal heuristic).
2. `parser.error` validates `--input` / `--reference` / numeric flags (lines `:300-350`).
3. Dispatch to method; method-specific kwargs from `METHOD_PARAM_DEFAULTS`.
4. Build proportions matrix; compute per-spot dominant cell-type + Shannon diversity.
5. Save `processed.h5ad` (with `obsm["proportions"]`), tables, figures, `report.md`, `result.json`.

## Gotchas

- **All input + parameter validation goes through `parser.error` (exit code 2).** `spatial_deconv.py:300` for missing `--input`; `:302` for missing input path; `:306` for missing `--reference` on methods that need one; `:308` for missing reference path; `:335` and `:338-350` for per-method numeric flag validation. Wrappers expecting `ValueError` need to catch exit-2.
- **`--reference` is required for almost every method** (only `flashdeconv` can run without it). `spatial_deconv.py:306` raises `parser.error(f"--reference is required for method '{args.method}'")` for the others. The reference must have cell-type labels in `obs` (key auto-resolved from common names).
- **Stored deconvolution-matrix lookup raises post-load.** `spatial_deconv.py:594` raises `ValueError(f"Stored deconvolution matrix '<prop_key>' not found in adata.obsm")` when re-rendering an already-deconvolved AnnData and the obsm key is missing. Used by the replot workflow.
- **`obsm["spatial"]` ↔ `obsm["X_spatial"]` sync at `:534-536`.** Same dual-key pattern as spatial-domains — both keys exist after a run.
- **`--cell2location-detection-alpha` must be > 0.** `spatial_deconv.py:340` enforces. The cell2location default (typically 200) is a regularisation strength — lower values mean less spatial smoothing.
- **`--destvi-dropout-rate` is in `[0, 1)`, not `[0, 1]`.** `spatial_deconv.py:342` enforces strict-less-than-1. dropout=1 would zero out everything.
- **R-backed methods (`rctd`, `card`) need a working R env.** Both rely on R packages (`spacexr` for RCTD, `CARD` for CARD). Missing R deps surface as ImportError at runtime, not at preflight.

## Key CLI

```bash
# Demo (synthetic; flashdeconv default)
python omicsclaw.py run spatial-deconv --demo --output /tmp/spatial_deconv_demo

# FlashDeconv (CPU-only, fastest)
python omicsclaw.py run spatial-deconv \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method flashdeconv

# Cell2location (Bayesian, GPU)
python omicsclaw.py run spatial-deconv \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method cell2location --cell2location-n-epochs 30000 \
  --cell2location-n-cells-per-spot 8 --cell2location-detection-alpha 200

# RCTD (R-backed)
python omicsclaw.py run spatial-deconv \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method rctd --rctd-mode full

# Tangram (gradient mapping)
python omicsclaw.py run spatial-deconv \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method tangram --tangram-n-epochs 1000 --tangram-learning-rate 0.1

# CARD (Conditional Autoregressive R deconv)
python omicsclaw.py run spatial-deconv \
  --input visium.h5ad --reference scrna_atlas.h5ad --output results/ \
  --method card
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when each backend wins; reference-data prep
- `references/output_contract.md` — `obsm["proportions"]` / `obs["dominant_celltype"]` schema
- Adjacent skills: `spatial-preprocess` (upstream — produces the input AnnData), `sc-cell-annotation` (upstream — labels the scRNA reference passed via `--reference`), `spatial-annotate` (parallel — for single-cell-per-spot platforms NOT spot deconvolution), `spatial-domains` (parallel — finds tissue regions WITHOUT a reference; complementary to deconv), `spatial-de` (downstream — DE between deconv-defined dominant-celltype groups)
