---
name: sc-gene-programs
description: >-
  Discover de novo gene programs and per-cell usage scores from scRNA-seq data
  using cNMF-compatible or NMF workflows.
version: 0.2.0
author: OmicsClaw
license: MIT
tags: [singlecell, gene-programs, cnmf, nmf]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
    - "--method"
    - "--n-programs"
    - "--n-iter"
    - "--seed"
    - "--layer"
    - "--top-genes"
    - "--r-enhanced"
    saves_h5ad: true
    requires_preprocessed: true
    script: sc_gene_programs.py
    legacy_aliases: [sc-programs]
    param_hints: {}
---

# Single-Cell Gene Programs

## Why This Exists

- Without it: users rely only on marker ranking and miss continuous programs.
- With it: coordinated expression modules and per-cell program usage become explicit outputs.

## Data / State Requirements

- **Input**: preprocessed AnnData (`.h5ad`) with normalized expression or raw counts
- **Matrix expectation**: NMF/cNMF require non-negative values. Normalized + log1p data is fine. Z-score scaled data with negatives is NOT fine.
- **cNMF**: prefers raw counts from `layers["counts"]` (auto-detected). If `layers["counts"]` is missing, uses `adata.X`.
- **NMF**: works on `adata.X` (normalized or counts). If `adata.X` is scaled with negatives, use `--layer counts`.
- **Upstream**: run `sc-preprocessing` first to get a normalized object with counts preserved in layers.
- **No clustering required**: gene programs are unsupervised and do not require cluster labels.

## Method Selection Table

| Scenario | Recommended method | Example |
|----------|-------------------|---------|
| Quick exploratory run | nmf | `--method nmf --n-programs 6` |
| Publication-quality consensus programs | cnmf | `--method cnmf --n-programs 10 --n-iter 400` |
| Small dataset (< 500 cells) | nmf | `--method nmf --n-programs 4` |
| Large dataset with counts layer | cnmf | `--method cnmf` (auto-uses counts layer) |

## Current Methods

1. `cnmf` -- consensus NMF via the official cNMF package (prepare, factorize, combine, consensus, load_results). Runs multiple replicates and filters outlier factorizations for robust programs.
2. `nmf` -- single-run NMF via scikit-learn. Fast baseline, no consensus filtering.

## Public Parameters

| Parameter | Meaning | Default |
|---|---|---|
| `--method` | `cnmf` or `nmf` | `cnmf` |
| `--n-programs` | number of latent programs | 6 |
| `--n-iter` | factorization iteration budget | 400 |
| `--seed` | random seed | 0 |
| `--layer` | optional expression layer to use | None (auto-detect) |
| `--top-genes` | top genes reported per program | 30 |

## Workflow

1. Load input AnnData (or generate demo data)
2. Preflight: validate matrix semantics (non-negative, layer existence)
3. Ensure input contract
4. Run factorization method (cnmf or nmf)
5. Detect degenerate output (collapsed programs, zero variance, empty results)
6. Persist results into adata (obsm, uns)
7. Render gallery figures (usage bar chart, correlation heatmap)
8. Write figure_data with manifest
9. Write contracts and analysis metadata
10. Export `processed.h5ad`
11. Write result.json, report.md, README.md

## Outputs

| File | Description |
|------|-------------|
| `processed.h5ad` | AnnData with `X_gene_programs` in obsm and contracts in uns |
| `tables/program_usage.csv` | Per-cell usage scores |
| `tables/program_weights.csv` | Gene weights matrix |
| `tables/top_program_genes.csv` | Top genes per program ranked by weight |
| `tables/program_tpm.csv` | TPM-normalized spectra (cNMF only) |
| `figures/mean_program_usage.png` | Bar chart of mean usage |
| `figures/program_correlation.png` | Program-program correlation heatmap |
| `figures/manifest.json` | Figure gallery manifest |
| `figure_data/manifest.json` | Plot-ready data manifest |
| `result.json` | Machine-readable results with contracts and diagnostics |
| `report.md` | Human-readable report with top genes and troubleshooting |

## Next Steps After This Skill

- Run `sc-enrichment` on top program genes to find enriched pathways per program
- Run `sc-de` to compare program usage between conditions
- Visualize program usage on UMAP embeddings

## References Inside OmicsClaw

- For short execution guardrails, see `knowledge_base/knowhows/KH-sc-gene-programs-guardrails.md`.
- For longer method and interpretation guidance, see `knowledge_base/skill-guides/singlecell/sc-gene-programs.md`.

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | None | Input AnnData file (`.h5ad`) | Required unless `--demo` |
| `--output` | str | — | Output directory | Required |
| `--demo` | flag | off | Run with built-in demo data | — |
| `--method` | str | `cnmf` | Factorization method: `cnmf` or `nmf` | Choices: `cnmf`, `nmf` |
| `--n-programs` | int | 6 | Number of latent gene programs to infer | Must be >= 2 |
| `--n-iter` | int | 400 | Factorization iteration budget | Must be >= 1 |
| `--seed` | int | 0 | Random seed for reproducibility | — |
| `--layer` | str | None | Expression layer to use (e.g., `counts`); auto-detected for cNMF if absent | Must exist in `adata.layers` if specified |
| `--top-genes` | int | 30 | Top genes reported per program (ranked by weight) | Must be >= 1 |
| `--r-enhanced` | flag | off | Generate R Enhanced plots (requires R + ggplot2) | — |

## R Enhanced Plots

| Renderer | Output file | Description |
|----------|-------------|-------------|
| `plot_embedding_discrete` | `figures/r_enhanced/r_embedding_discrete.png` | UMAP colored by discrete cluster labels |
| `plot_embedding_feature` | `figures/r_enhanced/r_embedding_feature.png` | UMAP colored by program usage score |
| `plot_feature_violin` | `figures/r_enhanced/r_feature_violin.png` | Violin plot of program usage per cell group |
| `plot_feature_cor` | `figures/r_enhanced/r_feature_cor.png` | Program correlation heatmap (R-rendered) |

## Workflow Position

**Upstream:** sc-clustering or sc-pseudotime
**Downstream:** sc-enrichment (enrich gene programs), sc-pseudotime (program dynamics)
