---
name: spatial-preprocess
description: Load when running the foundational spatial transcriptomics QC + filtering + normalisation
  + HVG + PCA + neighbour-graph + Leiden pipeline on a Visium / Xenium / generic spatial AnnData. Skip
  when raw FASTQs need converting first (use spatial-raw-processing); tissue-domain detection on already-preprocessed
  data (use spatial-domains).
trigger: preprocess, spatial preprocessing, spatial QC, normalize, visium, xenium, merfish, slide-seq, load spatial data, leiden, umap
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

**Inputs**

- Input kinds: `file`, `directory`
- Modalities: visium, xenium
- File types: `.h5ad`, `.h5`, `.hdf5`, `.zarr`
- Expects `obsm`: `spatial`

**Outputs**

- `tables/cluster_summary.csv`
- `tables/multi_resolution_summary.csv`
- `tables/pca_variance_ratio.csv`
- `tables/preprocess_run_summary.csv`
- `tables/preprocess_spatial_points.csv`
- `tables/preprocess_umap_points.csv`
- `tables/qc_metric_distributions.csv`
- `tables/qc_summary.csv`
- `figures/cluster_size_barplot.png`
- `figures/leiden_resolution_sweep.png`
- `figures/pca_variance_curve.png`
- `figures/qc_metric_distributions.png`
- `figures/qc_metrics_spatial.png`
- `figures/spatial_leiden.png`
- `figures/umap_leiden.png`
- `processed.h5ad`
- `report.md`
- `result.json`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `leiden`; `obsm`: `spatial`, `X_pca`, `X_umap`; `var`: `highly_variable`; `layers`: `counts`
- AnnData processing state after success: `preprocessed`

## Flow

1. Load AnnData (`--input`) or build a synthetic spatial demo.
2. Apply tissue preset if `--tissue <preset>` is given (overrides default `--min-genes` / `--min-cells` / `--max-mt-pct` / `--max-genes`).
3. QC + filter spots / genes; mitochondrial-percentage filter uses `--species` for gene prefix (`MT-` for human, `mt-` for mouse).
4. Normalise (CP10k log) → HVG (`--n-top-hvg`) → PCA (`--n-pcs`).
5. Build neighbour graph (`--n-neighbors`) → Leiden at `--leiden-resolution`.
6. If `--resolutions a,b,c,...` is set, sweep additional Leiden resolutions and write the multi-resolution table.
7. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **All input + parameter validation goes through `parser.error` (exit code 2), not `ValueError` / `SystemExit(1)`.** `spatial_preprocess.py` for missing `--input`; for missing path; for unknown `--tissue`; for negative / out-of-range numeric flags. Wrappers expecting standard `ValueError` need to handle exit code 2 separately.
- **`result.json["n_pcs_used"]` may be smaller than the requested `--n-pcs`.** The dimensionality is clipped in the helper at `skills/spatial/_lib/preprocessing.py`. The clipped value is surfaced into the per-row metrics CSV at `spatial_preprocess.py` (`n_pcs_used` and `n_pcs_requested`). Pass `n_pcs_used` (not `n_pcs_requested`) to downstream skills like `spatial-domains --n-pcs`.
- **`--tissue` overrides numeric defaults silently.** When a preset matches, `TISSUE_PRESETS` rewrites `--min-genes` / `--min-cells` / `--max-mt-pct` / `--max-genes` from the preset table. Pass values explicitly to override; `result.json["effective_params"]` records what was actually applied.
- **No UMAP fallback — missing `umap-learn` aborts the run.** `sc.tl.umap` is called unconditionally; if `umap-learn` (or igraph for Leiden) isn't installed, the run raises `ImportError` and exits non-zero — install `umap-learn` and `igraph` before running on a fresh env.
- **`--resolutions` parsing errors via `parser.error`.** `spatial_preprocess.py` raises on malformed comma-separated values; raises if any value is `<= 0`. Format: `0.4,0.6,0.8,1.0` (no spaces inside the value).
- **Default `--tissue` is `None` (no preset).** When unset, the skill uses the generic defaults from `defaults` dict — typically the right call. Tissue presets (`brain`, `tumor`, etc.) tighten thresholds and may filter aggressively on tissues with low UMI counts.

## Key CLI

```bash
# Demo (synthetic Visium)
python skills/spatial/spatial-preprocess/spatial_preprocess.py --demo --output /tmp/spatial_pp_demo

# Visium with default presets
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input visium.h5ad --output results/

# Tissue preset + custom resolution
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input visium.h5ad --output results/ \
  --data-type visium --tissue brain --leiden-resolution 1.2

# Multi-resolution sweep for picking optimal clustering
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input visium.h5ad --output results/ \
  --resolutions 0.4,0.6,0.8,1.0,1.4

# Mouse Xenium
python skills/spatial/spatial-preprocess/spatial_preprocess.py \
  --input xenium.h5ad --output results/ \
  --data-type xenium --species mouse --max-mt-pct 15
```

## See also

- `references/parameters.md` — every CLI flag, tissue-preset table
- `references/methodology.md` — when to override defaults; multi-resolution heuristic
- `references/output_contract.md` — `obs` / `obsm` / `var` schema written by this skill
- Adjacent skills: `spatial-raw-processing` (upstream — produces the input from FASTQ / SpaceRanger output), `spatial-integrate` (parallel — multi-sample alternative when batch effects need correction first), `spatial-domains` (downstream — consumes `obsm["X_pca"]` / `obs["leiden"]` for SpaGCN / STAGATE), `spatial-de` (downstream — DE between Leiden clusters)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scipy`, `seaborn`
