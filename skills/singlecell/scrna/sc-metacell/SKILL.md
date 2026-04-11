---
name: sc-metacell
description: >-
  Compress scRNA-seq data into metacell-level summaries using SEACells or a
  lightweight k-means aggregation fallback.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, metacell, seacells, compression]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
      - "--method"
      - "--use-rep"
      - "--n-metacells"
      - "--celltype-key"
      - "--min-iter"
      - "--max-iter"
    saves_h5ad: true
    requires_preprocessed: true
---

# Single-Cell Metacell

## Why This Exists

- Without it: large noisy single-cell datasets are hard to summarize stably.
- With it: cells are compressed into metacell-level profiles for downstream DE, trajectory, and visualization.

## Data / State Requirements

- **Input matrix**: normalized expression in `adata.X` (log-normalized preferred)
- **Raw counts**: `adata.layers["counts"]` is used for metacell aggregation when available; otherwise `adata.X` is used
- **Embedding**: `adata.obsm["X_pca"]` (or another embedding specified via `--use-rep`) must exist
- **Neighbors graph**: required for SEACells; computed automatically if missing
- **Upstream step**: run `sc-preprocessing` first to obtain normalized expression + PCA

## Current Methods

| Method | When to use | Needs neighbors? | Example |
|--------|-------------|-------------------|---------|
| `seacells` | Structure-aware aggregation; preserves manifold topology | Yes (auto-computed) | `--method seacells` |
| `kmeans` | Lightweight baseline; fast compression | No | `--method kmeans` |

## Key Parameters

| Parameter | Meaning | Default |
|---|---|---|
| `--method` | `seacells` or `kmeans` | `seacells` |
| `--use-rep` | embedding in `adata.obsm` used for aggregation | `X_pca` |
| `--n-metacells` | target metacell count (must be < n_cells) | `30` |
| `--celltype-key` | label column for dominant-type summary (SEACells) | `leiden` |
| `--min-iter` / `--max-iter` | SEACells optimization iteration bounds | `10` / `30` |
| `--seed` | random seed for reproducibility | `0` |

## Workflow

1. Load data (`--input` or `--demo`)
2. Preflight: validate embedding, n_metacells, matrix semantics
3. Run metacell construction (SEACells or k-means)
4. Assign metacell labels to original cells
5. Aggregate expression per metacell
6. Render gallery (centroid plot, size distribution)
7. Export `processed.h5ad` (original cells + metacell labels + contracts)

## Outputs

| File | Description |
|------|-------------|
| `processed.h5ad` | Original cell-level object with `obs["metacell"]` assignment and OmicsClaw contracts |
| `tables/metacells.h5ad` | Aggregated metacell expression profiles |
| `tables/cell_to_metacell.csv` | Cell-to-metacell mapping |
| `tables/metacell_summary.csv` | Metacell-level summary (n_cells, dominant label) |
| `figures/metacell_centroids.png` | Centroid overlay on embedding |
| `figures/metacell_size_distribution.png` | Histogram of cells per metacell |
| `figures/manifest.json` | Figure manifest for gallery rendering |
| `figure_data/manifest.json` | Plot-ready data manifest |
| `report.md` | Human-readable analysis report |
| `result.json` | Machine-readable result envelope |

## Matrix Contract (Output)

- `X` = `normalized_expression`
- `layers["counts"]` = `raw_counts` (when available from input)
- `raw` = `raw_counts_snapshot` (when available from input)
- `producer_skill` = `sc-metacell`

## Usual Next Steps

After metacell construction, common next steps include:
- **Differential expression** (`sc-de`) on metacell-level profiles
- **Trajectory analysis** (`sc-pseudotime`) using metacell-smoothed data
- **Visualization** of metacell-level gene expression patterns

## References Inside OmicsClaw

- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-metacell-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-metacell.md`.

## Workflow Position

**Upstream:** sc-clustering or sc-cell-annotation
**Downstream:** sc-de, sc-enrichment (using metacell AnnData)
