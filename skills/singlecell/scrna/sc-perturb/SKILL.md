---
name: sc-perturb
description: >-
  Single-cell perturbation analysis for scRNA-seq perturbation screens using
  the official pertpy Mixscape workflow.
version: 0.1.0
author: OmicsClaw
license: MIT
tags: [singlecell, perturbation, perturb-seq, crispr, mixscape, pertpy]
metadata:
  omicsclaw:
    domain: singlecell
    allowed_extra_flags:
    - "--method"
    - "--pert-key"
    - "--control"
    - "--split-by"
    - "--n-neighbors"
    - "--logfc-threshold"
    - "--pval-cutoff"
    - "--perturbation-type"
    - "--r-enhanced"
    saves_h5ad: true
    script: sc_perturb.py
    param_hints: {}
    requires_preprocessed: false
---

# Single-Cell Perturbation

## Why This Exists

- Without it: perturbation screens often stop at naive grouping and miss responder versus non-responder structure.
- With it: the official pertpy Mixscape workflow computes perturbation signatures and classifies perturbed subpopulations.

## Current Methods

1. `mixscape`

## Key Inputs

- a perturbation-aware `AnnData`
- a perturbation column via `--pert-key`
- a control label via `--control`
- optional replicate / batch split via `--split-by`

## Public Parameters

| Parameter | Meaning |
|---|---|
| `--method` | currently `mixscape` |
| `--pert-key` | perturbation or guide label column in `adata.obs` |
| `--control` | control category in the perturbation column |
| `--split-by` | biological replicate or condition column |
| `--n-neighbors` | neighbors used for perturbation signature |
| `--logfc-threshold` | DE threshold used inside Mixscape |
| `--pval-cutoff` | DE p-value cutoff used inside Mixscape |
| `--perturbation-type` | expected perturbation label such as `KO` |

## Notes

- This wrapper uses the official `pertpy.tools.Mixscape` workflow.
- Mixscape is best suited for Perturb-seq or CRISPR perturbation screens with a clear control population.
- If the input AnnData does not already contain perturbation labels in `adata.obs`, prepare them upstream first; OmicsClaw now provides `sc-perturb-prep` for expression data plus barcode-to-guide mapping files.

## Data / State Requirements

- **Matrix**: expects normalized expression (log1p); if raw counts are detected, the skill normalizes automatically
- **Layers**: `layers["counts"]` preserved when present
- **Required metadata**: a perturbation label column in `adata.obs` (default: `perturbation`) with a control label (default: `NT`)
- **PCA**: if `X_pca` is missing, the skill computes it automatically

## Upstream Step

Run `sc-perturb-prep` first if you have raw expression + a barcode-to-sgRNA mapping file.
If your AnnData already has perturbation labels in `.obs`, you can use it directly.

## Workflow

1. Load input or generate demo data
2. Preflight: validate perturbation column and control label exist
3. Ensure PCA is available
4. Run Mixscape (perturbation signature + classification)
5. Detect degenerate output (all NP)
6. Persist results: `processed.h5ad` with contract metadata
7. Render gallery and export tables

## Outputs

- `processed.h5ad` (canonical output with contract metadata)
- `tables/mixscape_class_counts.csv`
- `tables/mixscape_global_class_counts.csv`
- `tables/mixscape_cell_classes.csv`
- `figures/mixscape_global_classes.png`
- `figure_data/` (plot-ready CSVs)
- `reproducibility/commands.sh`
- `result.json` and `report.md`

## CLI Parameters

| Flag | Type | Default | Description | Validation |
|------|------|---------|-------------|------------|
| `--input` | str | None | Input AnnData file (`.h5ad`) | Required unless `--demo` |
| `--output` | str | — | Output directory | Required |
| `--demo` | flag | off | Run with built-in demo data | — |
| `--method` | str | `mixscape` | Analysis method (currently only `mixscape`) | Choices: `mixscape` |
| `--pert-key` | str | `perturbation` | `adata.obs` column containing perturbation labels | Column must exist; perturbation + control values must be present |
| `--control` | str | `NT` | Control label value inside the `--pert-key` column | Must match a category in `adata.obs[pert_key]` |
| `--split-by` | str | `replicate` | `adata.obs` column for replicate/batch splitting | Optional |
| `--n-neighbors` | int | 20 | Neighbors used for perturbation signature computation | — |
| `--logfc-threshold` | float | 0.25 | Log fold-change threshold used inside Mixscape DE | — |
| `--pval-cutoff` | float | 0.05 | P-value cutoff used inside Mixscape DE | — |
| `--perturbation-type` | str | `KO` | Expected perturbation class label (e.g., `KO`, `overexpression`) | — |
| `--seed` | int | 0 | Random seed for reproducibility | — |
| `--r-enhanced` | flag | off | Generate R Enhanced plots (requires R + ggplot2) | — |

## R Enhanced Plots

| Renderer | Output file | Description |
|----------|-------------|-------------|
| `plot_embedding_discrete` | `figures/r_enhanced/r_embedding_discrete.png` | UMAP colored by Mixscape class assignment |
| `plot_embedding_feature` | `figures/r_enhanced/r_embedding_feature.png` | UMAP colored by perturbation score |

## Special Requirements

### Perturbation Labels in `adata.obs`

`--pert-key` and `--control` are the two critical parameters for a real run:

- `--pert-key` must name an existing column in `adata.obs` that contains perturbation group labels (e.g., gene names or guide targets).
- `--control` must match the exact string used to label non-targeting control cells in that column (default `NT`).

If these labels are absent, run `sc-perturb-prep` first to merge a barcode-to-guide mapping file into the expression object.

```bash
# Typical real-data run
python omicsclaw.py run sc-perturb \
  --input perturb_prep_output/processed.h5ad \
  --pert-key perturbation \
  --control NT \
  --output results/

# If the column names differ from defaults
python omicsclaw.py run sc-perturb \
  --input data.h5ad \
  --pert-key guide_target \
  --control non-targeting \
  --output results/
```

## Workflow Position

**Upstream:** sc-perturb-prep
**Downstream:** sc-de (DE between perturbed and control), sc-enrichment
