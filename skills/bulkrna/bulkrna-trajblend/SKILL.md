---
name: bulkrna-trajblend
description: Load when bridging bulk RNA-seq samples to a single-cell reference via VAE+GNN trajectory interpolation, generating synthetic single-cell profiles per bulk sample. Skip for cell-type proportion estimation (use bulkrna-deconvolution) or for native single-cell trajectory inference (use sc-pseudotime).
version: 0.3.0
author: OmicsClaw
license: MIT
tags:
- bulkrna
- trajectory
- interpolation
- VAE
- GNN
- deconvolution
- single-cell
---

# bulkrna-trajblend

## When to use

Run when you have a bulk RNA-seq cohort and a paired single-cell
reference, and you want richer information than per-sample cell-type
proportions (which is bulkrna-deconvolution's job).  TrajBlend uses a
VAE + GNN to embed bulk samples into the single-cell trajectory space —
each bulk sample becomes a synthetic single-cell distribution that can
be projected onto the reference's developmental axes.

## Inputs & Outputs

| Input | Format | Required |
|---|---|---|
| Bulk count matrix | `.csv` / `.tsv` (gene × sample) | yes (or `--demo`) |
| sc reference | `--reference` `.h5ad` or `.csv` | yes (or `--demo`) |
| `--n-epochs` | int | default `50` (ignored in fallback path) |

| Output | Path | Notes |
|---|---|---|
| Synthetic sc profiles | `tables/synthetic_sc.csv` | per bulk sample, blended cell distribution |
| Trajectory projection | `figures/trajectory_projection.png` | bulk samples on sc reference UMAP |
| Embedding stats | `result.json["embedding"]` | dimensions, training loss curve |
| Report | `report.md` + `result.json` | always |

## Flow

1. Load bulk counts + sc reference.
2. Find common genes between bulk and reference (`bulkrna_trajblend.py:117` raises `ValueError` if `< 50` genes overlap).
3. If PyTorch available: train VAE for `--n-epochs` epochs, then GNN for graph-aware refinement.
4. If PyTorch unavailable: pure-NumPy fallback (no training; uses linear interpolation between sc reference centroids).  `--n-epochs` is silently ignored.
5. Project bulk samples into the reference's UMAP space.
6. Render projection + emit synthetic profiles.

## Gotchas

- **Gene-namespace mismatch hard-fails at 50.**  `bulkrna_trajblend.py:117` raises if fewer than 50 gene IDs overlap between bulk and reference.  Most common cause: bulk uses Ensembl IDs while sc reference uses HGNC symbols.  Pre-run `bulkrna-geneid-mapping` to harmonise — the error message names the offending sets.
- **Pure-NumPy fallback is qualitatively different from the VAE+GNN path.**  When `torch` is unimportable, the wrapper silently switches to a centroid-interpolation fallback (no training, no graph awareness).  `--n-epochs` becomes a no-op (`:354`'s help text already says "unused in fallback").  Verify `result.json["backend"]` — `"vae_gnn"` for the real path, `"numpy_fallback"` for centroid interpolation; results from the fallback are useful as a sanity check but should not be reported as VAE+GNN output.
- **The "synthetic single-cell" profiles are interpretation aids, not real cells.**  Each bulk sample maps to a *distribution* over the reference cell types; treating any single row of `synthetic_sc.csv` as if it represents one cell will mislead downstream analyses that expect real single-cell variability.  Use the projection plots, not the synthetic matrix, for biological reasoning.
- **VAE training is stochastic across runs.**  Each run with PyTorch picks a fresh random seed (no `--seed` flag); two runs on the same input produce slightly different projections.  The resemblance to the reference manifold is robust; the absolute coordinate values are not.

## Key CLI

```bash
python omicsclaw.py run bulkrna-trajblend --demo
python omicsclaw.py run bulkrna-trajblend \
  --input bulk_counts.csv --reference scref.h5ad --output results/
python omicsclaw.py run bulkrna-trajblend \
  --input bulk_counts.csv --reference scref.h5ad --output results/ \
  --n-epochs 200
```

## See also

- `references/parameters.md` — every CLI flag and tuning hint
- `references/methodology.md` — VAE+GNN architecture, NumPy fallback, gene-overlap requirement
- `references/output_contract.md` — exact output directory layout
- Adjacent skills: `bulkrna-deconvolution` (parallel: simpler cell-type proportion path; use this skill when you also want trajectory placement), `bulkrna-geneid-mapping` (run upstream to harmonise gene IDs), `sc-pseudotime` (the single-cell-native trajectory inference this skill bridges to)
