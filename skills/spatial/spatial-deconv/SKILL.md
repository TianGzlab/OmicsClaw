---
name: spatial-deconv
description: >-
  Cell type deconvolution for spatial transcriptomics using FlashDeconv,
  Cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, or CARD, with
  method-specific parameter hints and standardized proportion outputs.
version: 0.4.0
author: OmicsClaw Team
license: MIT
tags: [spatial, deconvolution, cell proportion, flashdeconv, cell2location, rctd, destvi, stereoscope, tangram, spotlight, card]
metadata:
  omicsclaw:
    domain: spatial
    allowed_extra_flags:
      - "--card-imputation"
      - "--card-ineibor"
      - "--card-min-count-gene"
      - "--card-min-count-spot"
      - "--card-num-grids"
      - "--card-sample-key"
      - "--cell-type-key"
      - "--cell2location-detection-alpha"
      - "--cell2location-n-cells-per-spot"
      - "--cell2location-n-epochs"
      - "--destvi-condscvi-epochs"
      - "--destvi-dropout-rate"
      - "--destvi-n-epochs"
      - "--destvi-n-hidden"
      - "--destvi-n-latent"
      - "--destvi-n-layers"
      - "--destvi-vamp-prior-p"
      - "--flashdeconv-lambda-spatial"
      - "--flashdeconv-n-hvg"
      - "--flashdeconv-n-markers-per-type"
      - "--flashdeconv-sketch-dim"
      - "--method"
      - "--no-gpu"
      - "--no-spotlight-scale"
      - "--rctd-mode"
      - "--reference"
      - "--spotlight-min-prop"
      - "--spotlight-model"
      - "--spotlight-n-top"
      - "--spotlight-scale"
      - "--spotlight-weight-id"
      - "--stereoscope-batch-size"
      - "--stereoscope-learning-rate"
      - "--stereoscope-rna-epochs"
      - "--stereoscope-spatial-epochs"
      - "--tangram-learning-rate"
      - "--tangram-mode"
      - "--tangram-n-epochs"
    param_hints:
      flashdeconv:
        priority: "flashdeconv_lambda_spatial → flashdeconv_sketch_dim → flashdeconv_n_hvg"
        params: ["reference", "cell_type_key", "flashdeconv_lambda_spatial", "flashdeconv_sketch_dim", "flashdeconv_n_hvg", "flashdeconv_n_markers_per_type"]
        defaults: {cell_type_key: "cell_type", flashdeconv_lambda_spatial: 5000.0, flashdeconv_sketch_dim: 512, flashdeconv_n_hvg: 2000, flashdeconv_n_markers_per_type: 50}
        requires: ["reference_h5ad", "obsm.spatial", "shared_genes"]
        tips:
          - "--flashdeconv-lambda-spatial: public FlashDeconv spatial regularization parameter; the upstream API also accepts `auto`."
          - "--flashdeconv-sketch-dim: public sketch size controlling approximation fidelity versus runtime."
          - "--flashdeconv-n-hvg / --flashdeconv-n-markers-per-type: public feature-selection controls passed directly to `flashdeconv.tl.deconvolve`."
      cell2location:
        priority: "cell2location_n_cells_per_spot → cell2location_detection_alpha → cell2location_n_epochs"
        params: ["reference", "cell_type_key", "cell2location_n_cells_per_spot", "cell2location_detection_alpha", "cell2location_n_epochs", "no_gpu"]
        defaults: {cell_type_key: "cell_type", cell2location_n_cells_per_spot: 30, cell2location_detection_alpha: 20.0, cell2location_n_epochs: 30000}
        requires: ["reference_h5ad", "counts_or_raw", "shared_genes"]
        tips:
          - "--cell2location-n-cells-per-spot: forwarded to `N_cells_per_location`, usually the first prior to tune."
          - "--cell2location-detection-alpha: public prior controlling how strongly technical sensitivity varies across locations."
          - "--cell2location-n-epochs: OmicsClaw wrapper training budget for the spatial mapping model; the reference regression stage is derived from it."
      rctd:
        priority: "rctd_mode"
        params: ["reference", "cell_type_key", "rctd_mode"]
        defaults: {cell_type_key: "cell_type", rctd_mode: "full"}
        requires: ["reference_h5ad", "counts_or_raw", "obsm.spatial", "Rscript"]
        tips:
          - "--rctd-mode: public spacexr mode; current public choices are `full`, `doublet`, or `multi`."
          - "Current OmicsClaw wrapper drops reference cell types with fewer than 25 cells before calling RCTD because spacexr needs enough cells per type."
      destvi:
        priority: "destvi_condscvi_epochs → destvi_n_epochs → destvi_n_latent/destvi_n_hidden"
        params: ["reference", "cell_type_key", "destvi_condscvi_epochs", "destvi_n_epochs", "destvi_n_hidden", "destvi_n_latent", "destvi_n_layers", "destvi_dropout_rate", "destvi_vamp_prior_p", "no_gpu"]
        defaults: {cell_type_key: "cell_type", destvi_condscvi_epochs: 300, destvi_n_epochs: 2500, destvi_n_hidden: 128, destvi_n_latent: 5, destvi_n_layers: 2, destvi_dropout_rate: 0.05, destvi_vamp_prior_p: 15}
        requires: ["reference_h5ad", "counts_or_raw", "shared_genes"]
        tips:
          - "--destvi-condscvi-epochs / --destvi-n-epochs: wrapper-exposed training budgets for the two public scvi-tools stages, `CondSCVI.train()` and `DestVI.train()`."
          - "--destvi-n-hidden / --destvi-n-latent / --destvi-n-layers / --destvi-dropout-rate: public CondSCVI architecture knobs."
          - "--destvi-vamp-prior-p: public `vamp_prior_p` / mixture-prior class count used when building DestVI from the reference model."
      stereoscope:
        priority: "stereoscope_rna_epochs → stereoscope_spatial_epochs → stereoscope_learning_rate"
        params: ["reference", "cell_type_key", "stereoscope_rna_epochs", "stereoscope_spatial_epochs", "stereoscope_learning_rate", "stereoscope_batch_size", "no_gpu"]
        defaults: {cell_type_key: "cell_type", stereoscope_rna_epochs: 400, stereoscope_spatial_epochs: 400, stereoscope_learning_rate: 0.01, stereoscope_batch_size: 128}
        requires: ["reference_h5ad", "counts_or_raw", "shared_genes"]
        tips:
          - "--stereoscope-rna-epochs / --stereoscope-spatial-epochs: direct public scvi-tools training budgets for `RNAStereoscope` and `SpatialStereoscope`."
          - "--stereoscope-learning-rate: forwarded through `plan_kwargs={'lr': ...}`."
          - "--stereoscope-batch-size: minibatch size used in both training stages."
      tangram:
        priority: "tangram_mode → tangram_n_epochs → tangram_learning_rate"
        params: ["reference", "cell_type_key", "tangram_mode", "tangram_n_epochs", "tangram_learning_rate", "no_gpu"]
        defaults: {cell_type_key: "cell_type", tangram_mode: "auto", tangram_n_epochs: 1000, tangram_learning_rate: 0.1}
        requires: ["reference_h5ad", "X_nonnegative_normalized", "obsm.spatial", "shared_genes"]
        tips:
          - "--tangram-mode: OmicsClaw exposes `auto`, `cells`, and `clusters`; `auto` resolves based on reference size."
          - "--tangram-n-epochs / --tangram-learning-rate: public `map_cells_to_space` optimization controls."
      spotlight:
        priority: "spotlight_weight_id → spotlight_n_top → spotlight_model → spotlight_min_prop"
        params: ["reference", "cell_type_key", "spotlight_weight_id", "spotlight_n_top", "spotlight_model", "spotlight_min_prop", "spotlight_scale"]
        defaults: {cell_type_key: "cell_type", spotlight_weight_id: "weight", spotlight_n_top: 50, spotlight_model: "ns", spotlight_min_prop: 0.01, spotlight_scale: true}
        requires: ["reference_h5ad", "X_nonnegative_normalized", "obsm.spatial", "Rscript"]
        tips:
          - "--spotlight-weight-id / --spotlight-model / --spotlight-min-prop / --spotlight-scale: public SPOTlight arguments."
          - "--spotlight-n-top: public SPOTlight `n_top` argument; current OmicsClaw default is a conservative first-pass wrapper choice of 50 markers per cell type."
          - "Current wrapper builds a marker table with a canonical `weight` column and also preserves `mean.AUC` when available from marker ranking."
      card:
        priority: "card_min_count_gene → card_min_count_spot → card_imputation"
        params: ["reference", "cell_type_key", "card_sample_key", "card_min_count_gene", "card_min_count_spot", "card_imputation", "card_num_grids", "card_ineibor"]
        defaults: {cell_type_key: "cell_type", card_min_count_gene: 100, card_min_count_spot: 5, card_imputation: false, card_num_grids: 2000, card_ineibor: 10}
        requires: ["reference_h5ad", "counts_or_raw", "obsm.spatial", "Rscript"]
        tips:
          - "--card-sample-key: OmicsClaw wrapper mapping to CARD `sample.varname`; only matters when the reference contains multiple samples."
          - "--card-min-count-gene / --card-min-count-spot: public `createCARDObject` filtering controls."
          - "--card-imputation / --card-num-grids / --card-ineibor: public `CARD.imputation` controls; current wrapper exports refined proportions when imputation is enabled."
    legacy_aliases: [deconv]
    saves_h5ad: true
    requires_preprocessed: true
    requires:
      bins:
        - python3
      env: []
      config: []
    emoji: "🧩"
    homepage: https://github.com/TianGzlab/OmicsClaw
    os: [macos, linux]
    install:
      - kind: pip
        package: scanpy
        bins: []
    trigger_keywords:
      - cell type deconvolution
      - spatial deconvolution
      - cell proportion
      - cell type proportion
      - cell2location
      - RCTD
      - DestVI
      - Stereoscope
      - Tangram
      - SPOTlight
      - CARD
---

# 🧩 Spatial Deconv

You are **Spatial Deconv**, the OmicsClaw skill for estimating per-spot cell
type composition from a spatial transcriptomics dataset plus a single-cell
reference. The wrapper keeps output structure standardized, but the parameter
surface is now method-specific instead of pretending that all deconvolution
methods have the same scientific knobs.

## Why This Exists

- **Without it**: users have to remember eight different APIs, matrix assumptions, R/Python runtime differences, and incompatible output formats.
- **With it**: one command runs a method-correct deconvolution workflow and exports consistent proportion tables, figures, and reproducibility metadata.
- **Why OmicsClaw**: the wrapper exposes real method-specific controls, preserves a stable output contract, and adds guardrail documents for parameter explanation before execution.

## Core Capabilities

1. **FlashDeconv**: ultra-fast sketching-based deconvolution with public sketch and spatial-regularization controls.
2. **Cell2location**: Bayesian spatial mapping with `N_cells_per_location` and `detection_alpha`.
3. **RCTD**: R / spacexr count-based decomposition with public `doublet_mode`.
4. **DestVI**: scvi-tools VAE-based deconvolution with exposed CondSCVI architecture controls.
5. **Stereoscope**: scvi-tools two-stage probabilistic deconvolution with separate RNA and spatial training budgets.
6. **Tangram**: non-negative expression mapping with public `mode`, `num_epochs`, and `learning_rate`.
7. **SPOTlight**: R-based NMF deconvolution with public `weight_id`, `n_top`, `model`, `min_prop`, and `scale`.
8. **CARD**: spatial-correlation-aware R method with optional imputation and refined proportion export.
9. **Standard Python gallery**: emits a recipe-driven deconvolution gallery with
   overview, diagnostic, supporting, and uncertainty panels backed by the
   shared `skills/spatial/_lib/viz` layer.
10. **Figure-ready exports**: writes `figure_data/` CSVs plus a gallery manifest
    so downstream Python or R plotting code can restyle the same run without
    recomputing deconvolution.
11. **Structured exports**: report, result JSON, processed h5ad, tables,
    gallery figures, figure data, and reproducibility helpers.

## Input Formats

| Format | Extension | Required Fields | Example |
|--------|-----------|-----------------|---------|
| Spatial AnnData | `.h5ad` | `X`, `obsm["spatial"]` | `processed.h5ad` |
| Reference AnnData | `.h5ad` | `X`, `obs["cell_type"]` or other label column | `reference_sc.h5ad` |

## Input Matrix Convention

Different deconvolution methods assume different matrix representations:

| Method | Main Expression Input | Notes |
|--------|-----------------------|-------|
| `cell2location` | raw counts (`layers["counts"]`, `raw`, or counts in `X`) | Count model; current wrapper restores counts when possible |
| `rctd` | raw counts | Requires spatial coordinates and enough reference cells per type |
| `destvi` | raw counts | Count-based scvi model on shared genes |
| `stereoscope` | raw counts | Count-based scvi model on shared genes |
| `card` | raw counts | Requires spatial coordinates; optional imputation step |
| `tangram` | normalized, non-negative expression in `adata.X` | Do not pass scaled / z-scored matrices with negative values |
| `spotlight` | normalized, non-negative expression | Current wrapper builds marker weights and forwards SPOTlight args |
| `flashdeconv` | flexible in current wrapper | Keep gene identifiers aligned and spatial coordinates present |

**Important**:
- Count-based methods should not be described as valid on scaled or centered matrices.
- Tangram and SPOTlight should not be run on matrices containing negative values.
- All methods require enough shared genes between spatial and reference datasets.

## Workflow

1. **Load**: read the spatial h5ad plus the single-cell reference.
2. **Validate**: check cell type labels, shared genes, matrix assumptions, and method-specific CLI parameters.
3. **Run the selected backend**.
4. **Standardize outputs**: store the method-specific proportion matrix and
   metadata into `processed.h5ad`.
5. **Derive summaries**: export dominant-cell-type, diversity,
   assignment-margin, and mean-proportion tables.
6. **Render the standard gallery**: build the OmicsClaw narrative gallery with
   spatial proportion overviews, diversity diagnostics, supporting composition
   summaries, and uncertainty panels.
7. **Export figure-ready data**: write `figure_data/*.csv` and
   `figure_data/manifest.json` for downstream customization.
8. **Report and export**: write `report.md`, `result.json`, `processed.h5ad`,
   tables, gallery figures, and reproducibility helpers.

## Visualization Contract

OmicsClaw treats `spatial-deconv` visualization as a two-layer system:

1. **Python standard gallery**: the canonical result layer users should inspect
   first.
2. **R customization layer**: an optional styling and publication layer that
   reads `figure_data/` and does not rerun Cell2location, RCTD, Tangram, or
   other deconvolution backends.

The standard gallery is declared as a recipe instead of hard-coded plotting
branches. Current gallery roles include:

- `overview`: multi-panel spatial proportions and dominant cell-type maps
- `diagnostic`: tissue diversity maps and UMAP composition views
- `supporting`: mean proportion summaries and dominant-type distributions
- `uncertainty`: assignment-margin maps and confidence histograms

## CLI Reference

```bash
# Default alias used by OmicsClaw
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --output <dir>

# FlashDeconv
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --method flashdeconv \
  --flashdeconv-lambda-spatial auto --flashdeconv-sketch-dim 1024 --output <dir>

# Cell2location
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --method cell2location \
  --cell2location-n-cells-per-spot 30 --cell2location-detection-alpha 20 --output <dir>

# RCTD
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --method rctd \
  --rctd-mode doublet --output <dir>

# DestVI
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --method destvi \
  --destvi-condscvi-epochs 300 --destvi-n-epochs 2500 --destvi-n-latent 8 --output <dir>

# Stereoscope
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --method stereoscope \
  --stereoscope-rna-epochs 400 --stereoscope-spatial-epochs 400 \
  --stereoscope-learning-rate 0.01 --output <dir>

# Tangram
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --method tangram \
  --tangram-mode clusters --tangram-n-epochs 1000 --output <dir>

# SPOTlight
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --method spotlight \
  --spotlight-weight-id weight --spotlight-n-top 50 --spotlight-model ns --output <dir>

# CARD with imputation
oc run spatial-deconvolution \
  --input <spatial.h5ad> --reference <ref.h5ad> --method card \
  --card-imputation --card-num-grids 2000 --card-ineibor 10 --output <dir>

# Direct script entrypoint
python skills/spatial/spatial-deconv/spatial_deconv.py \
  --input <spatial.h5ad> --reference <ref.h5ad> --method rctd --output <dir>
```

Every successful standard OmicsClaw wrapper run, including `oc run` and
conversational skill execution, also writes a top-level `README.md` and
`reproducibility/analysis_notebook.ipynb` to make the output directory easier
to inspect and rerun. Direct script execution primarily produces the skill
outputs plus `reproducibility/commands.sh`.

## Example Queries

- "Run Cell2location on my spatial data and explain the prior settings before running."
- "Use RCTD instead, but tell me whether `doublet` or `full` is more appropriate."
- "Try Tangram first because my matrix is normalized already."
- "Use CARD and also enable imputation."

## Output Structure

```text
output_dir/
├── README.md                                 # wrapper mode
├── report.md
├── result.json
├── processed.h5ad
├── figures/
│   ├── manifest.json
│   ├── spatial_proportions.png
│   ├── dominant_celltype.png
│   ├── celltype_diversity.png
│   ├── mean_proportions.png
│   ├── dominant_celltype_distribution.png
│   ├── assignment_margin_spatial.png
│   ├── assignment_margin_distribution.png
│   └── umap_proportions.png
├── figure_data/
│   ├── manifest.json
│   ├── proportions.csv
│   ├── deconv_spot_metrics.csv
│   ├── dominant_celltype.csv
│   ├── celltype_diversity.csv
│   ├── mean_proportions.csv
│   ├── dominant_celltype_counts.csv
│   ├── deconv_run_summary.csv
│   ├── deconv_spatial_points.csv
│   ├── deconv_umap_points.csv
│   └── card_refined_proportions.csv          # CARD imputation only
├── tables/
│   ├── proportions.csv
│   ├── dominant_celltype.csv
│   ├── celltype_diversity.csv
│   ├── mean_proportions.csv
│   ├── deconv_spot_metrics.csv
│   ├── dominant_celltype_counts.csv
│   └── card_refined_proportions.csv          # CARD imputation only
└── reproducibility/
    ├── analysis_notebook.ipynb               # wrapper mode
    ├── commands.sh
    ├── environment.txt
    └── r_visualization.sh
```

The repository also bundles starter R templates under:

```text
skills/spatial/spatial-deconv/r_visualization/
├── README.md
└── deconv_publication_template.R
```

## Dependencies

**Required**: scanpy, anndata, numpy, pandas, scipy, matplotlib

**Optional**:
- `flashdeconv` — FlashDeconv Python package
- `cell2location` + `scvi-tools` + `torch` — Cell2location
- `scvi-tools` + `torch` — DestVI and Stereoscope
- `tangram-sc` — Tangram
- `Rscript` + packages `spacexr`, `SPOTlight`, `CARD` — R-based methods

## Safety

- **Local-first**: no external upload.
- **Method-aware matrix assumptions**: counts-only and normalized-expression methods are documented separately and should be explained separately to users.
- **Audit trail**: reports, result JSON, and reproducibility scripts keep only the parameters relevant to the chosen method.
- **Two-layer visualization design**: Python plots are the canonical standard gallery; the optional R layer consumes `figure_data/` for publication-style refinement without recomputing the science.

## Integration with Orchestrator

**Trigger conditions**:
- cell type deconvolution
- cell proportion estimation
- spatial cell composition

**Chaining partners**:
- `spatial-preprocess` — preprocessing and count preservation
- `spatial-domains` — summarize tissue domains using deconvolution outputs
- `spatial-annotate` — compare reference-driven annotation with deconvolution proportions

## Citations

- [Cell2location](https://doi.org/10.1038/s41587-021-01139-4) — Kleshchevnikov et al., *Nature Biotechnology* 2022
- [RCTD](https://doi.org/10.1038/s41587-021-00830-w) — Cable et al., *Nature Biotechnology* 2022
- [DestVI](https://doi.org/10.1038/s41587-022-01272-8) — Lopez et al., *Nature Biotechnology* 2022
- [Stereoscope](https://doi.org/10.1038/s42003-020-01247-y) — Andersson et al., *Communications Biology* 2020
- [Tangram](https://doi.org/10.1038/s41592-021-01264-7) — Biancalani et al., *Nature Methods* 2021
- [SPOTlight](https://doi.org/10.1093/nar/gkab043) — Elosua-Bayes et al., *Nucleic Acids Research* 2021
- [CARD](https://doi.org/10.1038/s41587-022-01273-7) — Ma and Zhou, *Nature Biotechnology* 2022
