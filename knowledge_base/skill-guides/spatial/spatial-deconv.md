---
doc_id: skill-guide-spatial-deconv
title: OmicsClaw Skill Guide — Spatial Deconvolution
doc_type: method-reference
domains: [spatial]
related_skills: [spatial-deconvolution, spatial-deconv, deconv]
search_terms: [spatial deconvolution, cell proportion, cell2location, RCTD, DestVI, Stereoscope, Tangram, SPOTlight, CARD, tuning]
priority: 0.8
---

# OmicsClaw Skill Guide — Spatial Deconvolution

**Status**: implementation-aligned guide derived from the current OmicsClaw
`spatial-deconv` skill. This is **not** one of the 28 already validated
end-to-end workflows. It is a living guide for method selection, parameter
reasoning, and wrapper-specific caveats.

## Purpose

Use this guide when you need to decide:
- which deconvolution backend is the best first pass for the current dataset
- which parameters matter first in the current OmicsClaw wrapper
- how to explain proportions without pretending that all deconvolution methods behave the same way
- how to separate the canonical Python gallery from later R-side visualization refinement

## Step 1: Inspect The Data First

If the dataset has not been inspected yet in this conversation, call
`inspect_data` first.

Key properties to check:
- **Reference metadata**:
  - does `obs[cell_type_key]` exist in the reference?
  - are the labels biologically meaningful enough to support deconvolution?
- **Shared genes**:
  - all current methods need a meaningful gene overlap
  - current wrapper fails below 50 shared genes
- **Spatial coordinates**:
  - `obsm["spatial"]` or an equivalent spatial key must exist
- **Expression representation**:
  - count-based methods need raw counts in `layers["counts"]`, `raw`, or counts in `X`
  - Tangram and SPOTlight need non-negative normalized expression in `adata.X`
  - do not describe scaled or centered matrices with negative values as valid Tangram input
- **Reference imbalance**:
  - current RCTD wrapper drops reference cell types with fewer than 25 cells
- **Dataset size / compute budget**:
  - large references push Tangram toward `clusters` mode
  - GPU availability changes the practicality of Cell2location, DestVI, Stereoscope, and Tangram
- **Multi-sample reference structure**:
  - `card_sample_key` only matters when the reference contains multiple samples and the user wants CARD to keep that sample structure

Important implementation notes in current OmicsClaw:
- `cell2location`, `rctd`, `destvi`, `stereoscope`, and `card` all restore raw counts when possible.
- `tangram` hard-fails on negative expression values because cosine-based mapping is not meaningful on scaled matrices.
- `spotlight` now forwards the real public `weight_id`, `n_top`, `model`, `min_prop`, and `scale` arguments to the R backend.
- `stereoscope` now exposes separate RNA and spatial training budgets instead of a misleading single epoch knob.
- `card_imputation` now runs an actual `CARD.imputation` step and exports refined proportions.
- `flashdeconv` parameters exposed by OmicsClaw are taken from the public Python API; current matrix-assumption guidance remains intentionally conservative because the package is newer.
- OmicsClaw emits a canonical Python gallery under `figures/` plus `figure_data/`
  CSV exports for dominant labels, entropy, assignment margin, and spatial /
  UMAP point tables.

## Step 2: Pick The Method Deliberately

Use this quick guide when the user has not explicitly chosen a method:

| Method | Best first use | Strong starting parameters | Main caveat |
|--------|----------------|----------------------------|-------------|
| **Cell2location** | Strong default when raw counts, a good reference, and preferably GPU are available | `cell2location_n_cells_per_spot=30`, `cell2location_detection_alpha=20`, `cell2location_n_epochs=30000` | Heavier runtime and training cost than simpler methods |
| **FlashDeconv** | Fast first-pass screening when the user wants a lightweight Python method | `flashdeconv_lambda_spatial=5000` or `auto`, `flashdeconv_sketch_dim=512`, `flashdeconv_n_hvg=2000` | Newer method; keep matrix-assumption claims conservative |
| **RCTD** | Robust count-based R baseline when the user wants spacexr-style decomposition | `rctd_mode=full` or `doublet` | Needs enough cells per reference type and an R environment |
| **DestVI** | When within-cell-type heterogeneity matters, not just coarse proportions | `destvi_condscvi_epochs=300`, `destvi_n_epochs=2500`, `destvi_n_latent=5` | More modeling complexity and GPU demand |
| **Stereoscope** | Count-based probabilistic alternative to DestVI with simpler stage separation | `stereoscope_rna_epochs=400`, `stereoscope_spatial_epochs=400`, `stereoscope_learning_rate=0.01` | Still a two-stage deep model; slower than RCTD / SPOTlight |
| **Tangram** | When spatial and reference matrices are already normalized and non-negative | `tangram_mode=auto`, `tangram_n_epochs=1000`, `tangram_learning_rate=0.1` | Not a count model; input scaling mistakes are common |
| **SPOTlight** | R-based NMF deconvolution when marker weighting should be explicit | `spotlight_weight_id=weight`, `spotlight_n_top=50`, `spotlight_model=ns`, `spotlight_min_prop=0.01` | Marker weighting semantics matter a lot |
| **CARD** | Spatial-correlation-aware deconvolution, optionally followed by grid imputation | `card_min_count_gene=100`, `card_min_count_spot=5`, optional `card_imputation=true` | Requires R and should not be confused with base deconvolution-only output |

Practical default decision order:
1. If the user just says "run deconvolution" and the dataset clearly has raw counts plus a good reference, start with **Cell2location**.
2. Use **RCTD** when the user explicitly wants an R / spacexr baseline or a more classical count-based method.
3. Use **Tangram** when the user explicitly says the matrix is normalized already and wants mapping-based deconvolution.
4. Use **SPOTlight** when explicit marker weighting or NMF-style decomposition is the priority.
5. Use **CARD** when spatial smoothing or optional imputation is part of the scientific question.
6. Use **DestVI** when cell-state heterogeneity is central and the user accepts a heavier deep model.
7. Use **FlashDeconv** as a fast first-pass screen when turnaround matters more than richer posterior modeling.

## Step 3: Always Show A Parameter Summary Before Running

Before execution, tell the user what will be run in a short, concrete block:

```text
About to run spatial deconvolution
  Method: Cell2location
  Parameters: cell_type_key=cell_type, cell2location_n_cells_per_spot=30, cell2location_detection_alpha=20, cell2location_n_epochs=30000
  Dataset: 5,842 spots with 8 reference cell types and raw counts available
  Note: Cell2location is a strong first pass here because the data has counts, the reference looks usable, and the user wants a spatially aware Bayesian baseline.
```

## Step 4: Method-Specific Tuning Rules

### FlashDeconv

Tune in this order:
1. `flashdeconv_lambda_spatial`
2. `flashdeconv_sketch_dim`
3. `flashdeconv_n_hvg`
4. `flashdeconv_n_markers_per_type`

Guidance:
- Start with `flashdeconv_lambda_spatial=5000` or try `auto` when spatial smoothness is uncertain.
- Increase `flashdeconv_lambda_spatial` for broader tissue-scale smoothing.
- Reduce `flashdeconv_lambda_spatial` when local microenvironment boundaries matter more.
- Increase `flashdeconv_sketch_dim` when the approximation feels too coarse and runtime is acceptable.
- Keep `flashdeconv_n_hvg` and `flashdeconv_n_markers_per_type` in a moderate range first; extreme feature filtering can make proportions unstable.

Important warning:
- These are public package parameters, but FlashDeconv is still newer than older baselines like RCTD or CARD. Keep claims about matrix flexibility conservative.

### Cell2location

Tune in this order:
1. `cell2location_n_cells_per_spot`
2. `cell2location_detection_alpha`
3. `cell2location_n_epochs`

Guidance:
- Start with `cell2location_n_cells_per_spot=30` on Visium-like data unless there is a clear reason to expect much denser or sparser spots.
- Raise `cell2location_n_cells_per_spot` when spots clearly capture many cells.
- Lower it when spots are biologically sparse or near single-cell resolution.
- Start with `cell2location_detection_alpha=20`.
- Increase `cell2location_detection_alpha` when technical sensitivity variation across spots should be modeled more strongly.
- Use `cell2location_n_epochs` as a runtime / convergence budget, not as the first biological tuning parameter.

Important warning:
- `cell2location_n_epochs` is wrapper-level training budget language in OmicsClaw; the public biological priors that users usually care about first are `N_cells_per_location` and `detection_alpha`.

### RCTD

Tune in this order:
1. `rctd_mode`

Guidance:
- Start with `rctd_mode=full` for a conservative first pass when the user has no specific preference.
- Use `doublet` when the user expects most spots to contain one or two dominant cell types.
- Use `multi` when richer mixtures per spot are biologically plausible.

Important warnings:
- Current wrapper drops cell types with fewer than 25 reference cells before calling RCTD.
- If that filtering removes biologically important rare types, the right fix is usually to revisit the reference, not to hide the warning.

### DestVI

Tune in this order:
1. `destvi_condscvi_epochs`
2. `destvi_n_epochs`
3. `destvi_n_latent`
4. `destvi_n_hidden`
5. `destvi_n_layers`

Guidance:
- Start with the current defaults unless the user explicitly wants more training or a different latent capacity.
- Increase `destvi_condscvi_epochs` when the reference model is clearly underfit.
- Increase `destvi_n_epochs` when the spatial model appears unstable or under-converged.
- Increase `destvi_n_latent` only when the user specifically wants richer within-cell-type variation.
- Treat `destvi_n_hidden`, `destvi_n_layers`, and `destvi_dropout_rate` as architecture controls, not first-pass biology knobs.

Important warning:
- DestVI is the right tool when sub-state variation matters; it is overkill for every basic proportion-estimation request.

### Stereoscope

Tune in this order:
1. `stereoscope_rna_epochs`
2. `stereoscope_spatial_epochs`
3. `stereoscope_learning_rate`
4. `stereoscope_batch_size`

Guidance:
- Start with `stereoscope_rna_epochs=400` and `stereoscope_spatial_epochs=400`.
- Increase RNA epochs if the reference stage is unstable.
- Increase spatial epochs when proportions remain noisy after a clearly stable reference fit.
- Keep `stereoscope_learning_rate=0.01` first unless there is a specific optimization issue.
- Increase batch size only when hardware allows it and throughput is the main concern.

Important warning:
- These are direct wrappers over the two scvi-tools training stages; do not explain them as one generic epoch knob anymore.

### Tangram

Tune in this order:
1. `tangram_mode`
2. `tangram_n_epochs`
3. `tangram_learning_rate`

Guidance:
- Start with `tangram_mode=auto`.
- `auto` resolves to `clusters` for large references and `cells` for smaller ones.
- Use `clusters` when memory pressure matters or the reference is very large.
- Use `cells` when single-cell granularity is scientifically important and compute is acceptable.
- Increase `tangram_n_epochs` only after confirming the input matrix is appropriate.

Important warnings:
- Tangram should not be described as a count-based model.
- If the matrix contains negative values, fix preprocessing first instead of tuning Tangram harder.

### SPOTlight

Tune in this order:
1. `spotlight_weight_id`
2. `spotlight_n_top`
3. `spotlight_model`
4. `spotlight_min_prop`
5. `spotlight_scale`

Guidance:
- Start with `spotlight_weight_id=weight` in the current wrapper.
- Use `mean.AUC` only if the marker table clearly contains it and the user wants that exact weighting.
- Start with `spotlight_n_top=50` in OmicsClaw for a modest first pass.
- Increase `spotlight_n_top` when more markers per cell type are needed.
- Keep `spotlight_model=ns` first.
- Raise `spotlight_min_prop` when tiny fractional assignments are dominating the result.
- Consider `--no-spotlight-scale` only when the user explicitly wants to skip internal scaling.

Important warning:
- `spotlight_n_top` is the public SPOTlight argument, but the current default of 50 is an OmicsClaw first-pass wrapper choice rather than the package's only defensible setting.

### CARD

Tune in this order:
1. `card_min_count_gene`
2. `card_min_count_spot`
3. `card_sample_key`
4. `card_imputation`
5. `card_num_grids`
6. `card_ineibor`

Guidance:
- Start with `card_min_count_gene=100` and `card_min_count_spot=5`.
- Raise these thresholds when extremely sparse genes or spots are destabilizing the run.
- Set `card_sample_key` only when the reference truly contains multiple biological or technical samples that should stay distinct.
- Treat `card_imputation` as a second step, not the same thing as base deconvolution.
- Only tune `card_num_grids` and `card_ineibor` after deciding that imputation is actually needed.

Important warning:
- Do not oversell CARD imputation as if it were the same output as the base `Proportion_CARD` estimate; it is a refinement step on a denser grid.

## Step 5: What To Say After The Run

- If the run fails on too few shared genes: say the gene-space mismatch is the blocker and suggest harmonizing gene identifiers.
- If RCTD drops several cell types: report that explicitly and explain that the reference was too sparse for those labels.
- If Tangram fails because of negative values: explain that the matrix representation is invalid for Tangram rather than calling it a generic runtime error.
- If Cell2location or DestVI is very slow: point to GPU availability and training-budget parameters, not just "the method is heavy."
- If CARD imputation was enabled: mention that `tables/card_refined_proportions.csv` is an additional refinement output beyond the base proportions table.
- If proportions look uniformly diffuse across spots: suggest revisiting reference label granularity or method choice rather than only increasing epochs.
- If one method returns much sharper boundaries than another: explain that the methods differ in their priors and optimization stories instead of implying that one is automatically wrong.

## Step 6: Use The Visualization Layers Deliberately

Current OmicsClaw `spatial-deconv` separates visualization into two layers:

- **Python standard gallery**:
  - canonical analysis output
  - emitted under `figures/` with `figures/manifest.json`
  - should be the default artifact used in interactive analysis and routine
    reporting
- **R customization layer**:
  - optional refinement layer
  - should consume `figure_data/*.csv`
  - should not rerun Cell2location, RCTD, Tangram, or CARD just to restyle the
    same result

Practical rule:

1. Use the Python gallery to confirm the science and the narrative structure.
2. Use the R layer only when the user explicitly wants publication styling,
   panel composition, or deeper aesthetic control.
3. If an R script needs extra inputs, export them from Python first instead of
   embedding scientific recomputation inside the plotting layer.

The most important deconvolution-specific exports for downstream plotting are:

- `figure_data/proportions.csv`
- `figure_data/deconv_spot_metrics.csv`
- `figure_data/dominant_celltype_counts.csv`
- `figure_data/deconv_run_summary.csv`
- `figure_data/deconv_spatial_points.csv`
- `figure_data/deconv_umap_points.csv`

## Step 7: Explain Results Using Method-Correct Language

When summarizing results to the user:
- For **Cell2location**, describe the output as Bayesian spatial cell abundance estimates converted to proportions.
- For **RCTD**, describe the output as spacexr / RCTD deconvolution weights normalized to proportions.
- For **DestVI**, describe the output as DestVI-inferred cell-type proportions from a latent variable model.
- For **Stereoscope**, describe the output as scvi-tools Stereoscope proportions from a two-stage probabilistic model.
- For **Tangram**, describe the output as Tangram projected cell-type fractions from non-negative expression mapping.
- For **SPOTlight**, describe the output as SPOTlight NMF-based deconvolution under the chosen marker weighting.
- For **CARD**, describe the output as CARD spatially correlated deconvolution proportions, plus refined proportions if imputation was enabled.
- For **FlashDeconv**, describe the output as FlashDeconv sketching-based deconvolution proportions under the chosen approximation and spatial-regularization settings.

Do **not** collapse all methods into a generic "deconvolution score" story.
They expose different assumptions, training behaviors, and interpretation
constraints in current OmicsClaw.
