---
name: spatial-statistics
description: Load when running spatial autocorrelation / hotspot / co-occurrence / neighbourhood-enrichment / Ripley K stats on a clustered spatial AnnData via squidpy. Skip when ranking spatially variable genes (use spatial-genes) or for tissue domain detection (use spatial-domains).
version: 0.5.0
author: OmicsClaw
license: MIT
tags:
- spatial
- statistics
- moran
- geary
- ripley
- co-occurrence
- nhood-enrichment
- getis-ord
- squidpy
requires:
- anndata
- scanpy
- squidpy
- numpy
- pandas
---

# spatial-statistics

## When to use

The user has a clustered spatial AnnData (`obs[--cluster-key]` for
cluster-aware analyses; `obsm["spatial"]` populated) and wants a
specific spatial-statistics analysis. Pick `--analysis-type` from
`VALID_ANALYSIS_TYPES`:

- `moran` / `geary` — global spatial autocorrelation per gene.
- `local_moran` — per-spot LISA + GeoDa quadrants (`--local-moran-geoda-quads`).
- `getis_ord` — per-spot hotspot Z-scores.
- `bivariate_moran` — exactly two genes (`--genes geneA,geneB`).
- `neighborhood_enrichment` — squidpy NES between cluster pairs.
- `ripley` — Ripley K / L / G / F (`--ripley-mode`, `--ripley-metric`).
- `co_occurrence` — pairwise label co-occurrence at distance bins
  (`--coocc-interval`, `--coocc-n-splits`).
- `spatial_centrality` — graph-centrality per spot.

For per-gene SVG ranking use `spatial-genes`; for tissue-domain
detection use `spatial-domains`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Clustered spatial AnnData | `.h5ad` with `obsm["spatial"]` + `obs[--cluster-key]` | yes (unless `--demo`) |
| Genes | `--genes geneA,geneB,...` (comma-separated) | required for `bivariate_moran` |

| Output | Path | Notes |
|---|---|---|
| Annotated AnnData | `processed.h5ad` | adds per-gene analysis-specific `obs` columns: `obs[f"local_moran_<gene>"]` / `obs[f"local_moran_pval_<gene>"]` / `obs[f"local_moran_q_<gene>"]` (`_lib/statistics.py:739-741`); `obs[f"getis_ord_<gene>"]` / `obs[f"getis_ord_pval_<gene>"]` (`:832-833`). Other analyses write to `uns`. |
| Analysis summary | `tables/analysis_summary.csv` | always |
| Neighbourhood Z-score matrix | `tables/neighborhood_zscore.csv` | when `--analysis-type neighborhood_enrichment` |
| Neighbourhood counts | `tables/neighborhood_counts.csv` | when `--analysis-type neighborhood_enrichment` |
| Bivariate-Moran summary | `tables/bivariate_moran_summary.csv` | when `--analysis-type bivariate_moran` |
| Per-analysis result tables | `tables/<analysis-specific>.csv` | dispatched per analysis-type |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load AnnData (`--input`) or chain through `spatial-preprocess --demo` via subprocess (`spatial_statistics.py:1499-1515`).
2. `parser.error` validates `--analysis-type` ∈ `VALID_ANALYSIS_TYPES`; per-analysis numeric ranges (lines `:1558-1601`).
3. Auto-resolve `--cluster-key` if unset; auto-leiden if no cluster column exists (with size guard at `:1546`).
4. Dispatch to analysis-type runner; squidpy graph build uses `--stats-n-neighs` / `--stats-n-rings` / `--stats-n-perms`.
5. Build standardised result tables; collect per-spot metrics.
6. Save tables, figures, `processed.h5ad`, `report.md`, `result.json`.

## Gotchas

- **All input + parameter validation goes through `parser.error` (exit code 2).** `spatial_statistics.py:1530` for missing `--input`; `:1546` for too-small dataset to auto-leiden; `:1558` for invalid `--analysis-type`; `:1560-1601` for numeric / multi-value flag validation. Wrappers expecting `ValueError` need to catch exit-2.
- **`bivariate_moran` requires exactly TWO genes.** `spatial_statistics.py:1601` raises `parser.error("--analysis-type bivariate_moran requires exactly two genes via --genes geneA,geneB")`. Pass them comma-separated, no spaces.
- **Demo chains through `spatial-preprocess` via subprocess.** `spatial_statistics.py:1499` raises `FileNotFoundError(f"spatial-preprocess not found at {preprocess_script}")` if the sibling skill is missing; `:1510` raises `RuntimeError("spatial-preprocess --demo failed (exit ...)")` on chained failure; `:1515` raises `FileNotFoundError(f"Expected {processed}")` when the demo output isn't where expected.
- **`--cluster-key` auto-leiden has a size guard.** `spatial_statistics.py:1546` raises `parser.error("Dataset is too small to auto-compute `leiden` clusters.")` when the auto-fallback can't run. Pass `--cluster-key <existing-column>` for small datasets.
- **`local_moran` writes `n_significant_spots`; `getis_ord` writes `n_hotspots`.** `spatial_statistics.py:555` documents the value-column divergence. Downstream tools reading "spatially significant cell count" need to branch on `--analysis-type`.
- **`neighborhood_enrichment` consumes `<cluster_key>_nhood_enrichment` from `uns`.** Computed lazily within squidpy; if you re-run with a different `--cluster-key`, the previous `uns` key remains and won't be reused for the new cluster column. Clean `adata.uns` between runs or expect stale keys.
- **`spatial_centrality` is graph-only.** It produces per-spot centrality without any cluster-key dependency — useful when `--cluster-key` is unavailable.

## Key CLI

```bash
# Demo (chained from spatial-preprocess --demo)
python omicsclaw.py run spatial-statistics --demo --analysis-type moran --output /tmp/spatial_stats_demo

# Global Moran's I on a clustered AnnData
python omicsclaw.py run spatial-statistics \
  --input clustered.h5ad --output results/ \
  --analysis-type moran --cluster-key spatial_domain --stats-n-perms 100

# Local Moran with GeoDa quadrants
python omicsclaw.py run spatial-statistics \
  --input clustered.h5ad --output results/ \
  --analysis-type local_moran --local-moran-geoda-quads --n-top-genes 20

# Neighbourhood enrichment between clusters
python omicsclaw.py run spatial-statistics \
  --input clustered.h5ad --output results/ \
  --analysis-type neighborhood_enrichment --cluster-key spatial_domain

# Ripley K on a labelled object
python omicsclaw.py run spatial-statistics \
  --input clustered.h5ad --output results/ \
  --analysis-type ripley --ripley-mode K --ripley-n-simulations 100 --ripley-n-steps 50

# Co-occurrence at increasing distance bins
python omicsclaw.py run spatial-statistics \
  --input clustered.h5ad --output results/ \
  --analysis-type co_occurrence --cluster-key cell_type --coocc-interval 30 --coocc-n-splits 5

# Bivariate Moran between two genes
python omicsclaw.py run spatial-statistics \
  --input clustered.h5ad --output results/ \
  --analysis-type bivariate_moran --genes EGFR,BRCA1
```

## See also

- `references/parameters.md` — every CLI flag, per-analysis numeric ranges
- `references/methodology.md` — when each analysis-type wins; squidpy mapping
- `references/output_contract.md` — per-analysis table / `obs` / `uns` schema
- Adjacent skills: `spatial-preprocess` (upstream — produces `obsm["spatial"]` + cluster column), `spatial-domains` / `spatial-annotate` (upstream — produce `obs["spatial_domain"]` / cell-type labels for `--cluster-key`), `spatial-genes` (parallel — per-gene SVG ranking, NOT statistics on labels), `spatial-de` (downstream — DE between clusters identified by neighbourhood-enrichment hotspots)
