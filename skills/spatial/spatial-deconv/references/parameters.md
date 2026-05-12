<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--card-imputation`
- `--card-ineibor`
- `--card-min-count-gene`
- `--card-min-count-spot`
- `--card-num-grids`
- `--card-sample-key`
- `--cell-type-key`
- `--cell2location-detection-alpha`
- `--cell2location-n-cells-per-spot`
- `--cell2location-n-epochs`
- `--cpu`
- `--destvi-condscvi-epochs`
- `--destvi-dropout-rate`
- `--destvi-n-epochs`
- `--destvi-n-hidden`
- `--destvi-n-latent`
- `--destvi-n-layers`
- `--destvi-vamp-prior-p`
- `--flashdeconv-lambda-spatial`
- `--flashdeconv-n-hvg`
- `--flashdeconv-n-markers-per-type`
- `--flashdeconv-sketch-dim`
- `--method`
- `--n-epochs`
- `--no-gpu`
- `--rctd-mode`
- `--reference`
- `--spotlight-min-prop`
- `--spotlight-model`
- `--spotlight-n-top`
- `--spotlight-scale`
- `--spotlight-weight-id`
- `--stereoscope-batch-size`
- `--stereoscope-learning-rate`
- `--stereoscope-rna-epochs`
- `--stereoscope-spatial-epochs`
- `--tangram-learning-rate`
- `--tangram-mode`
- `--tangram-n-epochs`
- `--use-gpu`

## Per-method parameter hints

### `card`

**Tuning priority:** card_min_count_gene → card_min_count_spot → card_imputation

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `card_sample_key` | `—` |
| `card_min_count_gene` | `100` |
| `card_min_count_spot` | `5` |
| `card_imputation` | `False` |
| `card_num_grids` | `2000` |
| `card_ineibor` | `10` |

**Requires:**
- `reference_h5ad`
- `counts_or_raw`
- `obsm.spatial`
- `Rscript`

**Tips:**
- --card-sample-key: OmicsClaw wrapper mapping to CARD `sample.varname`; only matters when the reference contains multiple samples.
- --card-min-count-gene / --card-min-count-spot: public `createCARDObject` filtering controls.
- --card-imputation / --card-num-grids / --card-ineibor: public `CARD.imputation` controls; current wrapper exports refined proportions when imputation is enabled.

### `cell2location`

**Tuning priority:** cell2location_n_cells_per_spot → cell2location_detection_alpha → cell2location_n_epochs

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `cell2location_n_cells_per_spot` | `30` |
| `cell2location_detection_alpha` | `20.0` |
| `cell2location_n_epochs` | `30000` |
| `no_gpu` | `—` |

**Requires:**
- `reference_h5ad`
- `counts_or_raw`
- `shared_genes`

**Tips:**
- --cell2location-n-cells-per-spot: forwarded to `N_cells_per_location`, usually the first prior to tune.
- --cell2location-detection-alpha: public prior controlling how strongly technical sensitivity varies across locations.
- --cell2location-n-epochs: OmicsClaw wrapper training budget for the spatial mapping model; the reference regression stage is derived from it.

### `destvi`

**Tuning priority:** destvi_condscvi_epochs → destvi_n_epochs → destvi_n_latent/destvi_n_hidden

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `destvi_condscvi_epochs` | `300` |
| `destvi_n_epochs` | `2500` |
| `destvi_n_hidden` | `128` |
| `destvi_n_latent` | `5` |
| `destvi_n_layers` | `2` |
| `destvi_dropout_rate` | `0.05` |
| `destvi_vamp_prior_p` | `15` |
| `no_gpu` | `—` |

**Requires:**
- `reference_h5ad`
- `counts_or_raw`
- `shared_genes`

**Tips:**
- --destvi-condscvi-epochs / --destvi-n-epochs: wrapper-exposed training budgets for the two public scvi-tools stages, `CondSCVI.train()` and `DestVI.train()`.
- --destvi-n-hidden / --destvi-n-latent / --destvi-n-layers / --destvi-dropout-rate: public CondSCVI architecture knobs.
- --destvi-vamp-prior-p: public `vamp_prior_p` / mixture-prior class count used when building DestVI from the reference model.

### `flashdeconv`

**Tuning priority:** flashdeconv_lambda_spatial → flashdeconv_sketch_dim → flashdeconv_n_hvg

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `flashdeconv_lambda_spatial` | `5000.0` |
| `flashdeconv_sketch_dim` | `512` |
| `flashdeconv_n_hvg` | `2000` |
| `flashdeconv_n_markers_per_type` | `50` |

**Requires:**
- `reference_h5ad`
- `obsm.spatial`
- `shared_genes`

**Tips:**
- --flashdeconv-lambda-spatial: public FlashDeconv spatial regularization parameter; the upstream API also accepts `auto`.
- --flashdeconv-sketch-dim: public sketch size controlling approximation fidelity versus runtime.
- --flashdeconv-n-hvg / --flashdeconv-n-markers-per-type: public feature-selection controls passed directly to `flashdeconv.tl.deconvolve`.

### `rctd`

**Tuning priority:** rctd_mode

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `rctd_mode` | `full` |

**Requires:**
- `reference_h5ad`
- `counts_or_raw`
- `obsm.spatial`
- `Rscript`

**Tips:**
- --rctd-mode: public spacexr mode; current public choices are `full`, `doublet`, or `multi`.
- Current OmicsClaw wrapper drops reference cell types with fewer than 25 cells before calling RCTD because spacexr needs enough cells per type.

### `spotlight`

**Tuning priority:** spotlight_weight_id → spotlight_n_top → spotlight_model → spotlight_min_prop

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `spotlight_weight_id` | `weight` |
| `spotlight_n_top` | `50` |
| `spotlight_model` | `ns` |
| `spotlight_min_prop` | `0.01` |
| `spotlight_scale` | `True` |

**Requires:**
- `reference_h5ad`
- `X_nonnegative_normalized`
- `obsm.spatial`
- `Rscript`

**Tips:**
- --spotlight-weight-id / --spotlight-model / --spotlight-min-prop / --spotlight-scale: public SPOTlight arguments.
- --spotlight-n-top: public SPOTlight `n_top` argument; current OmicsClaw default is a conservative first-pass wrapper choice of 50 markers per cell type.
- Current wrapper builds a marker table with a canonical `weight` column and also preserves `mean.AUC` when available from marker ranking.

### `stereoscope`

**Tuning priority:** stereoscope_rna_epochs → stereoscope_spatial_epochs → stereoscope_learning_rate

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `stereoscope_rna_epochs` | `400` |
| `stereoscope_spatial_epochs` | `400` |
| `stereoscope_learning_rate` | `0.01` |
| `stereoscope_batch_size` | `128` |
| `no_gpu` | `—` |

**Requires:**
- `reference_h5ad`
- `counts_or_raw`
- `shared_genes`

**Tips:**
- --stereoscope-rna-epochs / --stereoscope-spatial-epochs: direct public scvi-tools training budgets for `RNAStereoscope` and `SpatialStereoscope`.
- --stereoscope-learning-rate: forwarded through `plan_kwargs={'lr': ...}`.
- --stereoscope-batch-size: minibatch size used in both training stages.

### `tangram`

**Tuning priority:** tangram_mode → tangram_n_epochs → tangram_learning_rate

**Core parameters:**

| name | default |
|---|---|
| `reference` | `—` |
| `cell_type_key` | `cell_type` |
| `tangram_mode` | `auto` |
| `tangram_n_epochs` | `1000` |
| `tangram_learning_rate` | `0.1` |
| `no_gpu` | `—` |

**Requires:**
- `reference_h5ad`
- `X_nonnegative_normalized`
- `obsm.spatial`
- `shared_genes`

**Tips:**
- --tangram-mode: OmicsClaw exposes `auto`, `cells`, and `clusters`; `auto` resolves based on reference size.
- --tangram-n-epochs / --tangram-learning-rate: public `map_cells_to_space` optimization controls.
