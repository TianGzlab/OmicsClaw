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

## Use from a step

```python
from skills._sdk.notebook import load_skill, read_input, write_output

atac = load_skill("scatac-preprocessing")
adata = read_input("data/peaks.h5", reader=atac.read_10x_peaks)
adata = atac.preprocess(adata, random_state=0)
write_output(adata, "intermediate/accessibility.h5ad")
write_output(atac.cluster_summary(adata), "tables/clusters.csv")
```

For H5AD use `read_input` without a reader. The API returns a copy and does
not write files. `examples/example_step.py` recovers three planted groups
from `load_demo("atac_synthetic")`; that tests computation, not biological validity.

## When to use

The user has a cell × peak scATAC AnnData (raw-count-like accessibility
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

- `tables/cluster_summary.csv`
- `tables/lsi_variance_ratio.csv`
- `tables/peak_summary.csv`
- `tables/preprocess_summary.csv`
- `tables/qc_metrics_per_cell.csv`
- `tables/umap_points.csv`
- `figures/umap_leiden.png`
- `figures/lsi_variance.png`
- `figures/qc_violin.png`
- `figures/top_accessible_peaks.png`
- `processed.h5ad`
- `report.md`
- `result.json`
- `figures/manifest.json`, `figure_data/manifest.json`, plot-data CSV files
- `reproducibility/commands.sh`, `reproducibility/requirements.txt`
- Processed AnnData (`saves_h5ad`) — adds `obs`: `leiden`; `obsm`: `X_lsi`, `X_umap`; `layers`: `counts`
- AnnData processing state after success: `preprocessed`

## Flow

1. Read cell × peak counts. The 10x reader uses `gex_only=False` and keeps Peaks in multiome inputs; other CLI formats use `smart_load`.
2. Validate `.X` is present, non-empty, non-negative.
3. Compute per-cell `n_peaks_by_counts` / `total_counts`; filter cells by `--min-peaks` and peaks by `--min-cells`.
4. Retain the globally most accessible peaks up to `--n-top-peaks`.
5. Run Signac-style TF-IDF (`--tfidf-scale-factor`); truncated-SVD LSI to `--n-lsi` components.
6. Build neighbour graph (`--n-neighbors`), UMAP, Leiden (`--leiden-resolution`).
7. Save `processed.h5ad`, tables, figures, `report.md`, `result.json`.

## Gotchas

- **Filtering can wipe everything.** `_api.py:preprocess` raises if `min_peaks` removes every cell or `min_cells` removes every peak. Inspect `n_peaks_by_counts` before tightening thresholds; the CLI defaults to `--min-peaks 200`.
- **LSI needs enough cells and peaks.** `_api.py:preprocess` raises when fewer than two LSI components can be computed after filtering.
- **Input must be non-negative count-like in `.X`.** `_api.py:preprocess` rejects missing, empty or negative matrices. Non-integer values only warn: TF-IDF values are usually non-negative and may pass this check, but preprocessing them again is not valid.
- **`processed.h5ad` keeps only retained peaks.** `_api.py:preprocess` selects the top `n_top_peaks` by total accessibility. Keep the input if you need the full peak space later.
- **`--input` mandatory unless `--demo`.** `scatac_preprocessing.py` raises `ValueError("--input required when not using --demo")`.
- **Single backend only.** `scatac_preprocessing.py` raises `ValueError(f"Unknown preprocessing method '{method}'")` for anything other than `tfidf_lsi`. The `--method` flag exists for forward compatibility; today it's effectively a no-op.
- `_api.py:qc_metrics_table` reports QC metrics calculated before selecting top peaks. Those totals can exceed the sums in the returned, peak-filtered `.X` or counts layer.
- `_api.py:read_10x_peaks` reads counts, not fragments or BAM. It raises when a multiome input contains no Peaks features; it never falls back to gene expression.

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

## API

<!-- api:begin generated from _api.py; regenerate with run.py api <skill dir> --write -->

### `preprocess(adata, *, min_peaks=200, min_cells=5, n_top_peaks=10000, tfidf_scale_factor=10000.0, n_lsi=30, n_neighbors=15, leiden_resolution=0.8, random_state=0)`

Return a filtered copy of .X accessibility counts with TF-IDF, LSI and Leiden.

Cells need min_peaks detected peaks; peaks need min_cells cells. Keep at
most n_top_peaks, ranked by total counts. Counts remain in layers['counts']
and .raw on retained peaks; .X becomes log1p TF-IDF. LSI uses scaled SVD
components, excluding the first component from the neighbor graph. UMAP
and Leiden use that graph. All stochastic operations use random_state.
No file is written and the input is not modified.

### `read_10x_peaks(path)`

Read 10x H5 or MTX peak counts; pass it as reader= to read_input.

Use gex_only=False, then keep Peaks when feature_types is present. No
gene-expression filtering is applied to a peak-only matrix lacking it.

### `qc_metrics_table(adata)`

Return cell identifiers and the QC metrics computed before top-peak selection.

### `peak_summary(adata, *, n_top=50)`

Return retained peaks ranked by total counts and number of cells.

### `lsi_variance_table(adata)`

Return variance ratios and their cumulative sum for every fitted LSI component.

### `cluster_summary(adata, *, cluster_key='leiden')`

Return cell counts and percentages for labels in obs[cluster_key].

### `umap_figure(adata, *, cluster_key='leiden')`

Return a cluster-colored Figure from obsm['X_umap']; do not write a file.

### `run_info(adata)`

Return the TF-IDF/LSI parameters recorded on the output AnnData.

<!-- api:end -->

## See also

- `references/parameters.md` — every CLI flag, per-method tunables
- `references/methodology.md` — TF-IDF + LSI math; Signac alignment
- `references/output_contract.md` — `obsm`/`var` schema + table layouts
- Adjacent skills: `sc-preprocessing` (parallel — scRNA, NOT scATAC), `sc-clustering` (downstream — re-cluster on `obsm["X_lsi"]` if you want a different resolution without re-running TF-IDF)

## Dependencies

Python packages this skill's script needs. They are not installed for you — check before a long run.

`anndata`, `igraph`, `matplotlib`, `numpy`, `pandas`, `scanpy`, `scikit-learn`, `scipy`, `seaborn`
