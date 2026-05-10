---
name: bulkrna-trajblend
description: Load when placing bulk RNA-seq samples on a single-cell reference's pseudotime axis (NNLS deconvolution + nearest-neighbour mapping). Skip for plain cell-type proportions (use bulkrna-deconvolution alone) or for native single-cell trajectory inference (use sc-pseudotime).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- trajectory
- pseudotime
- deconvolution
- single-cell
---

# bulkrna-trajblend

## When to use

Run when you have a bulk RNA-seq cohort and a single-cell reference
with pre-computed pseudotime, and you want each bulk sample placed on
that pseudotime axis.  The current implementation is a sklearn-based
NNLS-plus-nearest-neighbour pipeline (PCA → kNN against ref); it does
*not* use VAE / GNN despite the skill name's connotation.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Bulk count matrix | `.csv` / `.tsv` (gene × sample) | yes (or `--demo`) |
| sc reference | `--reference` `.h5ad` or `.csv` (must include pseudotime in `obs` for h5ad) | yes (or `--demo`) |
| `--n-epochs` | int | default `50` — currently a no-op (the script's `argparse` help text already says "unused in fallback"); kept for forward-compat with a future training path |

| Output | Path | Notes |
|---|---|---|
| Cell-type fractions | `tables/cell_fractions.csv` | sample × cell_type proportions (NNLS weights) |
| Pseudotime estimates | `tables/pseudotime_estimates.csv` | per sample: pseudotime mean / std / mean_neighbor_dist / pc1 / pc2 |
| Figures | `figures/*.png` | trajectory projection on reference UMAP/PCA |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load bulk counts + sc reference.
2. Find common genes between bulk and reference (`bulkrna_trajblend.py:117` raises `ValueError` if `< 50` genes overlap).
3. Run NNLS deconvolution to estimate per-sample cell-type fractions.
4. Project bulk samples into the reference's PCA space; use `sklearn.neighbors.NearestNeighbors` to find each bulk sample's k nearest reference cells.
5. Estimate per-sample pseudotime as mean (and std) of the neighbour set's reference pseudotime values.
6. Render trajectory figures; emit fractions + pseudotime tables.

## Gotchas

- **Gene-namespace mismatch hard-fails at 50.**  `bulkrna_trajblend.py:117` raises if fewer than 50 gene IDs overlap between bulk and reference.  Most common cause: bulk uses Ensembl IDs while sc reference uses HGNC symbols.  Pre-run `bulkrna-geneid-mapping` to harmonise.
- **`--n-epochs` is currently a no-op.**  The argparse help text at `:354` reads `"VAE epochs (unused in fallback)"` — there is no VAE / GNN code path in this version (the script imports only `sklearn`, `numpy`, `pandas`).  The flag is preserved as a forward-compat hook; passing any value has no effect on output.  Do not report results as "VAE+GNN-derived" until that code lands.
- **Pseudotime placement is a kNN average, not a likelihood-based fit.**  Each bulk sample's `pseudotime` is the *mean* of its k nearest reference cells' pseudotimes — it doesn't carry uncertainty in the way a probabilistic model would.  Use `pseudotime_std` and `mean_neighbor_dist` (per `bulkrna_trajblend.py:184-188`) as crude confidence proxies; large neighbour distances mean the bulk sample doesn't cleanly resemble any reference cell.
- **Reference pseudotime values must be supplied externally.**  This skill consumes pseudotime; it does not compute it.  Run `sc-pseudotime` on the reference first (or use a published pre-pseudotimed reference) so the input AnnData has the relevant `obs` column.

## Key CLI

```bash
python omicsclaw.py run bulkrna-trajblend --demo
python omicsclaw.py run bulkrna-trajblend \
  --input bulk_counts.csv --reference scref.h5ad --output results/
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — NNLS deconvolution + kNN pseudotime mapping; the future-training path the `--n-epochs` flag anticipates
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-deconvolution` (parallel: same NNLS proportions, no pseudotime placement), `bulkrna-geneid-mapping` (run upstream to harmonise gene IDs), `sc-pseudotime` (run upstream on the reference to populate the pseudotime column this skill consumes)
