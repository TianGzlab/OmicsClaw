---
name: spatial-register
description: Load when aligning multiple spatial slices into a common coordinate frame on a multi-slice spatial AnnData via PASTE optimal transport or STalign image-aware registration. Skip when data is single-slice (no registration needed) or for cross-sample integration in the gene-expression space (use spatial-integrate).
version: 0.4.0
author: OmicsClaw
license: MIT
tags:
- spatial
- registration
- alignment
- paste
- stalign
- multi-slice
requires:
- anndata
- scanpy
- numpy
- pandas
---

# spatial-register

## When to use

The user has a multi-slice spatial AnnData (slices stacked into one
object with a `--slice-key` column) and wants the slices registered
into a shared coordinate frame so a downstream analysis can use the
common axes. Two methods:

- `paste` (default) — PASTE optimal-transport alignment based on gene
  expression similarity + spatial proximity (`--paste-alpha`,
  `--paste-dissimilarity`). Requires `paste-bio` + `pot` (+ optional
  `torch` for GPU).
- `stalign` — STalign image-aware diffeomorphic registration; best
  when histology images are available (`--stalign-niter`,
  `--stalign-image-size`, `--stalign-a`). Requires `STalign` + `torch`.

For *expression-space* batch correction across slices use
`spatial-integrate`. For aligning a single slice to a reference atlas
use the same skill with that atlas as the reference slice.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Multi-slice AnnData | `.h5ad` with `obs[--slice-key]` (≥ 2 slices) | yes (unless `--demo`) |
| Histology images | `obsm` keys (`stalign` only) | conditional |

| Output | Path | Notes |
|---|---|---|
| Registered AnnData | `processed.h5ad` | adds `obsm["spatial_aligned"]` (registered coords from `_lib/register.py:184/476`); the original `obsm["spatial"]` is preserved as-is (the script does NOT overwrite it). A legacy duplicate also lives at `obsm["X_spatial"]` (`spatial_register.py:80/83`). |
| Registration summary | `tables/registration_summary.csv` | per-slice shift / disparity stats |
| Per-slice metrics | `tables/registration_metrics.csv` | always |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or build a multi-slice demo via the bundled `spatial-preprocess` runner (chains across slices).
2. `parser.error` validates numeric flag ranges (`--paste-alpha` ∈ [0, 1]; `--stalign-niter`/`-image-size`/`-a` > 0).
3. Resolve `--slice-key` (auto-pick from `slice` / `sample` / `library_id` if unset); raise if `< 2` slices.
4. Pick a reference slice (largest by default) and align all others to it.
5. For PASTE: compute pairwise transport plans using `--paste-alpha` (gene-vs-spatial weight); apply translations.
6. For STalign: run iterative image-aware diffeomorphism with `--stalign-niter` iterations.
7. Save `processed.h5ad` (registered coords in `obsm["spatial_aligned"]`; original `obsm["spatial"]` preserved unchanged), tables, figures, `report.md`, `result.json`.

## Gotchas

- **All input + parameter validation goes through `parser.error` (exit code 2).** `spatial_register.py:896` for missing `--input`; `:898` for missing path; `:901` for `--paste-alpha` out of [0, 1]; `:903-907` for non-positive STalign params. Wrappers expecting `ValueError` need to catch exit-2 separately.
- **Slice-key validation raises `ValueError` post-argparse.** `spatial_register.py:913` raises `ValueError(f"Slice key '<requested_key>' not found in adata.obs")`; `:915` raises `ValueError(f"Slice key '<requested_key>' must contain at least 2 slices")`. These fire after argparse, so they're real Python `ValueError`s — different from the `parser.error` group above.
- **`paste` requires `paste-bio` + `pot`; `stalign` requires `STalign` + `torch`.** `spatial_register.py:827-829` lists the optional packages by method; the actual import sites raise `ImportError` if missing. The skill records what's installed in `reproducibility/environment.txt`.
- **Registered coordinates land in `obsm["spatial_aligned"]`, NOT in `obsm["spatial"]`.** The original `obsm["spatial"]` is preserved unchanged; the aligned coords are added as a separate key. Downstream tools that consume `obsm["spatial"]` will keep using the *original* coords unless they explicitly switch to `obsm["spatial_aligned"]`. The legacy duplicate `obsm["X_spatial"]` also exists (`spatial_register.py:80/83`) for back-compat.
- **Demo mode chains through `spatial-preprocess` first.** `spatial_register.py:988` raises `FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")` if the sibling skill is missing from the install; `:1005` raises `FileNotFoundError(f"Expected {processed}")` when the demo preprocess output isn't where expected. Real runs skip this chain.
- **Disparity / shift metrics are best-effort.** When `paste-bio` or `STalign` doesn't expose disparity scores, the metric columns in `tables/registration_metrics.csv` will be NaN — `:178` documents the column initialisation. Quote the per-slice shifts (`mean_shift`, `median_shift`, `max_shift`) instead.

## Key CLI

```bash
# Demo (multi-slice synthetic; chains through spatial-preprocess)
python omicsclaw.py run spatial-register --demo --output /tmp/spatial_reg_demo

# PASTE alignment on a multi-slice Visium object
python omicsclaw.py run spatial-register \
  --input multi_slice.h5ad --output results/ \
  --slice-key library_id --method paste --paste-alpha 0.1

# STalign with strong image regularisation
python omicsclaw.py run spatial-register \
  --input multi_slice.h5ad --output results/ \
  --slice-key sample --method stalign \
  --stalign-niter 200 --stalign-image-size 256 --stalign-a 100

# PASTE on GPU
python omicsclaw.py run spatial-register \
  --input multi_slice.h5ad --output results/ \
  --method paste --paste-alpha 0.1 --paste-use-gpu
```

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — when PASTE vs STalign wins; reference-slice heuristic
- `references/output_contract.md` — `obsm["spatial"]` preserved + `obsm["spatial_aligned"]` registered coords + legacy `obsm["X_spatial"]`
- Adjacent skills: `spatial-raw-processing` / `spatial-preprocess` (upstream — produce per-slice AnnData), `spatial-integrate` (parallel — corrects in expression space, NOT spatial coords), `spatial-domains` (downstream — domain detection works better on registered coords), `spatial-condition` (downstream — cross-condition comparison after alignment)
