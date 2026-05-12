---
name: spatial-preprocess
description: Load when running the foundational spatial transcriptomics QC + filtering + normalisation + HVG + PCA + neighbour-graph + Leiden pipeline on a Visium / Xenium / generic spatial AnnData. Skip when raw FASTQs need converting first (use spatial-raw-processing) or for tissue-domain detection on already-preprocessed data (use spatial-domains).
version: 0.6.0
author: OmicsClaw
license: MIT
tags:
- spatial
- visium
- xenium
- preprocessing
- qc
- normalization
- hvg
- pca
- leiden
requires:
- anndata
- scanpy
- numpy
- pandas
---

# spatial-preprocess

## When to use

The user has a spatial AnnData (Visium / Xenium / SpaceRanger output /
generic) — either freshly loaded or coming out of
`spatial-raw-processing` — and wants the canonical
"QC → filter → normalise → HVG → PCA → neighbours → Leiden" path
producing a downstream-ready `processed.h5ad`. This is the **foundation
skill** — most other spatial analyses (`spatial-domains`,
`spatial-de`, `spatial-genes`, `spatial-deconv`,
`spatial-communication`, ...) consume its output. Single backend:
`scanpy_standard`.

For raw FASTQ → matrix conversion use `spatial-raw-processing`. For
explicit tissue-domain detection (SpaGCN / STAGATE) on top of this
output use `spatial-domains`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Spatial AnnData | `.h5ad` (Visium / Xenium / generic, with `obsm["spatial"]` recommended) | yes (unless `--demo`) |
| Tissue preset | `--tissue` (one of `TISSUE_PRESETS`) | optional — overrides QC defaults |

| Output | Path | Notes |
|---|---|---|
| Processed AnnData | `processed.h5ad` | `X = normalised`, `layers["counts"] = raw`, `obsm["X_pca"]`, `obsm["X_umap"]`, `var["highly_variable"]`, `obs["leiden"]` |
| Run summary | `tables/preprocess_summary.csv` | always |
| Cluster sizes | `tables/cluster_summary.csv` | always |
| QC summary | `tables/qc_summary.csv` | per-cluster QC metrics |
| PCA variance | `tables/pca_variance_ratio.csv` | per-PC variance |
| Multi-resolution sweep | `tables/multi_resolution_summary.csv` | when `--resolutions` is provided |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or build a synthetic spatial demo.
2. Apply tissue preset if `--tissue <preset>` is given (overrides default `--min-genes` / `--min-cells` / `--max-mt-pct` / `--max-genes`).
3. QC + filter spots / genes; mitochondrial-percentage filter uses `--species` for gene prefix (`MT-` for human, `mt-` for mouse).
4. Normalise (CP10k log) → HVG (`--n-top-hvg`) → PCA (`--n-pcs`).
5. Build neighbour graph (`--n-neighbors`) → Leiden at `--leiden-resolution`.
6. If `--resolutions a,b,c,...` is set, sweep additional Leiden resolutions and write the multi-resolution table.
7. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **All input + parameter validation goes through `parser.error` (exit code 2), not `ValueError` / `SystemExit(1)`.** `spatial_preprocess.py:1006` for missing `--input`; `:1008` for missing path; `:1010` for unknown `--tissue`; `:1012-1028` for negative / out-of-range numeric flags. Wrappers expecting standard `ValueError` need to handle exit code 2 separately.
- **`result.json["n_pcs_used"]` may be smaller than the requested `--n-pcs`.** The dimensionality is clipped in the helper at `skills/spatial/_lib/preprocessing.py:307` (cross-file anchor — lint skips). The clipped value is surfaced into the per-row metrics CSV at `spatial_preprocess.py:193` (`n_pcs_used`) and `:191` (`n_pcs_requested`). Pass `n_pcs_used` (not `n_pcs_requested`) to downstream skills like `spatial-domains --n-pcs`.
- **`--tissue` overrides numeric defaults silently.** When a preset matches, `TISSUE_PRESETS` rewrites `--min-genes` / `--min-cells` / `--max-mt-pct` / `--max-genes` from the preset table. Pass values explicitly to override; `result.json["effective_params"]` records what was actually applied.
- **No UMAP fallback — missing `umap-learn` aborts the run.** `sc.tl.umap` is called unconditionally; if `umap-learn` (or igraph for Leiden) isn't installed, the run raises `ImportError` and exits non-zero. There is no `_safe_umap` shim in the script — install `umap-learn` and `igraph` before running on a fresh env.
- **`--resolutions` parsing errors via `parser.error`.** `spatial_preprocess.py:1026` raises on malformed comma-separated values; `:1028` raises if any value is `<= 0`. Format: `0.4,0.6,0.8,1.0` (no spaces inside the value).
- **Default `--tissue` is `None` (no preset).** When unset, the skill uses the generic defaults from `defaults` dict at `:956-958` — typically the right call. Tissue presets (`brain`, `tumor`, etc.) tighten thresholds and may filter aggressively on tissues with low UMI counts.

## Key CLI

```bash
# Demo (synthetic Visium)
python omicsclaw.py run spatial-preprocess --demo --output /tmp/spatial_pp_demo

# Visium with default presets
python omicsclaw.py run spatial-preprocess \
  --input visium.h5ad --output results/

# Tissue preset + custom resolution
python omicsclaw.py run spatial-preprocess \
  --input visium.h5ad --output results/ \
  --data-type visium --tissue brain --leiden-resolution 1.2

# Multi-resolution sweep for picking optimal clustering
python omicsclaw.py run spatial-preprocess \
  --input visium.h5ad --output results/ \
  --resolutions 0.4,0.6,0.8,1.0,1.4

# Mouse Xenium
python omicsclaw.py run spatial-preprocess \
  --input xenium.h5ad --output results/ \
  --data-type xenium --species mouse --max-mt-pct 15
```

## See also

- `references/parameters.md` — every CLI flag, tissue-preset table
- `references/methodology.md` — when to override defaults; multi-resolution heuristic
- `references/output_contract.md` — `obs` / `obsm` / `var` schema written by this skill
- Adjacent skills: `spatial-raw-processing` (upstream — produces the input from FASTQ / SpaceRanger output), `spatial-integrate` (parallel — multi-sample alternative when batch effects need correction first), `spatial-domains` (downstream — consumes `obsm["X_pca"]` / `obs["leiden"]` for SpaGCN / STAGATE), `spatial-de` (downstream — DE between Leiden clusters)
