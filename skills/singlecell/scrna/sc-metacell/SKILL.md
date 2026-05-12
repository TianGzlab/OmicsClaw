---
name: sc-metacell
description: Load when aggregating single cells into metacells (sample-aware coarse-grained pseudo-cells) on a normalised scRNA AnnData via SEACells or KMeans on a low-D embedding. Skip when ranking marker genes per cluster (use sc-markers) or for trajectory pseudotime ordering (use sc-pseudotime).
version: 0.2.0
author: OmicsClaw
license: MIT
tags:
- singlecell
- scrna
- metacell
- seacells
- aggregation
- pseudo-cells
requires:
- anndata
- scanpy
- numpy
- pandas
- scikit-learn
---

# sc-metacell

## When to use

The user has a normalised scRNA AnnData with a low-D embedding
(`obsm["X_pca"]` by default) and wants compact metacell aggregates
suitable for downstream GRN inference, slow-RNA-velocity analysis, or
robust cluster-level statistics that need fewer but higher-coverage
units. Two methods:

- `seacells` (default) — kernel archetypal analysis with iterative
  refinement (`--min-iter` / `--max-iter`). Aggregates similar cells
  into archetypes. Auto-falls back to `kmeans` if the SEACells package
  isn't installed.
- `kmeans` — KMeans clustering on the embedding; faster, no SEACells
  dependency.

Output is a new AnnData (`madata`) where each row is one metacell.
For per-cluster marker discovery on the original AnnData, use
`sc-markers`. For ordering cells, use `sc-pseudotime`.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Normalised AnnData | `.h5ad` with `obsm[--use-rep]` (default `X_pca`) | yes (unless `--demo`) |

| Output | Path | Notes |
|---|---|---|
| Cell-level AnnData with metacell labels | `processed.h5ad` | **rows = original cells**; adds `obs["metacell"]` holding the metacell ID. This is the primary downstream object — `sc-de` / `sc-enrichment` expect this shape. |
| Metacell-aggregated AnnData | `tables/metacells.h5ad` | rows = metacells; per-metacell aggregated expression for cluster-level / GRN downstream |
| Metacell summary | `tables/metacell_summary.csv` | per-metacell `obs` (size, dominant celltype, etc.) |
| Cell → metacell map | `tables/cell_to_metacell.csv` | always |
| Figures | `figures/metacell_centroids.png`, `figures/metacell_size_distribution.png` | first only when an embedding is plottable |
| Report | `report.md` + `result.json` | always |

## Flow

1. SEACells fallback check: try `import SEACells`; if it fails, silently switch `--method` to `kmeans`.
2. Load AnnData (`--input`) or build a demo.
3. Preflight: `obsm[--use-rep]` exists; `--n-metacells` is `< n_cells` and `≥ 2`; warn if no `layers["counts"]`.
4. For SEACells: run kernel archetypal analysis with `--min-iter` / `--max-iter`; for KMeans: cluster the embedding.
5. Aggregate cell-level expression into metacell-level expression (sum over `layers["counts"]` if present, else `.X`).
6. Build per-metacell summary (size, dominant `--celltype-key` label).
7. Save metacell AnnData, tables, figures, `report.md`, `result.json`.

## Gotchas

- **`--method seacells` silently auto-falls back to `kmeans` if SEACells isn't installed.** `sc_metacell.py:326-332` catches `ImportError` from `import SEACells` and logs a warning, then sets `args.method = "kmeans"`. The actually-used method is recorded in `result.json["method"]` (the post-fallback value), but the request-vs-execute distinction isn't preserved as separate keys here. Inspect logs / report.md to confirm.
- **All preflight failures `raise SystemExit(1)`, not `ValueError`.** `sc_metacell.py:113` raises `SystemExit(1)` when `obsm[--use-rep]` is missing (with available-embedding hint); `:123` raises when `--n-metacells >= n_cells` (with a sane suggested value); `:128` raises when `--n-metacells < 2`; `:340` raises `SystemExit("Provide --input or use --demo")`. Wrappers expecting `ValueError` need to catch `SystemExit`.
- **`processed.h5ad` is the cell-level AnnData with metacell labels — NOT the metacell-aggregated AnnData.** `sc_metacell.py:463` saves the original `adata` (with `obs["metacell"]` added) to `processed.h5ad`; `sc_metacell.py:393` writes the aggregated metacell-shape `madata` to `tables/metacells.h5ad`. Downstream skills like `sc-de` / `sc-enrichment` (advertised in the next-step block at `sc_metacell.py:534-535`) consume `processed.h5ad`, not the aggregated shape — pass `tables/metacells.h5ad` explicitly when you actually need per-metacell rows.
- **Aggregation prefers `layers["counts"]` over `.X`.** The preflight warns if `layers["counts"]` is absent (`sc_metacell.py:131-134`); when it's missing the script aggregates from `.X` (typically log-normalised) which is mathematically less defensible than summing raw counts.
- **`--celltype-key` defaults to `leiden`.** `sc_metacell.py:77` defaults to `leiden`; if your AnnData has labels under a different key (e.g., `cell_type`), pass `--celltype-key cell_type` so the per-metacell "dominant cell type" column is meaningful.

## Key CLI

```bash
# Demo
python omicsclaw.py run sc-metacell --demo --output /tmp/sc_metacell_demo

# Default SEACells, 30 metacells
python omicsclaw.py run sc-metacell \
  --input clustered.h5ad --output results/

# KMeans (fast, no SEACells dependency)
python omicsclaw.py run sc-metacell \
  --input clustered.h5ad --output results/ \
  --method kmeans --n-metacells 50

# Use Harmony-corrected embedding + custom celltype key
python omicsclaw.py run sc-metacell \
  --input integrated.h5ad --output results/ \
  --use-rep X_harmony --celltype-key cell_type --n-metacells 100

# More refinement iterations for SEACells (slower, smoother archetypes)
python omicsclaw.py run sc-metacell \
  --input clustered.h5ad --output results/ \
  --min-iter 20 --max-iter 60
```

## See also

- `references/parameters.md` — every CLI flag, SEACells vs KMeans tunables
- `references/methodology.md` — when metacells help; SEACells archetypal math
- `references/output_contract.md` — `madata.obs` schema; cell-to-metacell map columns
- Adjacent skills: `sc-clustering` (upstream — produces `obs["leiden"]` for the celltype-key default), `sc-batch-integration` (upstream — produces `X_harmony` embedding for `--use-rep`), `sc-grn` (downstream — GRN inference is more stable on metacells than single cells), `sc-de` (parallel — sample-aware DE between conditions; complements per-metacell aggregation)
