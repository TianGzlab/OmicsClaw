<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--method`
- `--paste-alpha`
- `--paste-dissimilarity`
- `--paste-use-gpu`
- `--reference-slice`
- `--slice-key`
- `--stalign-a`
- `--stalign-image-size`
- `--stalign-niter`
- `--use-expression`

## Per-method parameter hints

### `paste`

**Tuning priority:** slice_key/reference_slice → paste_alpha → paste_dissimilarity

**Core parameters:**

| name | default |
|---|---|
| `slice_key` | `—` |
| `reference_slice` | `—` |
| `paste_alpha` | `0.1` |
| `paste_dissimilarity` | `kl` |
| `paste_use_gpu` | `False` |

**Requires:**
- `obsm.spatial`
- `obs.slice`
- `shared_genes`
- `X_expression`

**Tips:**
- --slice-key: practical wrapper control; OmicsClaw requires a real slice label column instead of fabricating one.
- --paste-alpha: public PASTE weight between expression dissimilarity and spatial distance in `pairwise_align`.
- --paste-dissimilarity: public PASTE expression dissimilarity choice; the wrapper exposes the documented `kl` / `euclidean` options.
- --paste-use-gpu: public PASTE backend switch; only matters when a compatible Torch backend is available.

### `stalign`

**Tuning priority:** slice_key/reference_slice → stalign_a → stalign_niter

**Core parameters:**

| name | default |
|---|---|
| `slice_key` | `—` |
| `reference_slice` | `—` |
| `stalign_niter` | `2000` |
| `stalign_a` | `500.0` |
| `stalign_image_size` | `400` |
| `use_expression` | `False` |

**Requires:**
- `obsm.spatial`
- `obs.slice`
- `pairwise_two_slices`
- `X_expression_optional`

**Tips:**
- --stalign-a / --stalign-niter: public STalign LDDMM controls that directly affect deformation smoothness and optimization depth.
- --stalign-image-size: current OmicsClaw wrapper rasterization resolution before calling LDDMM; this is wrapper-level, not the core scientific STalign parameter.
- --use-expression: current wrapper-level switch that uses PC1 of shared genes as image intensity instead of uniform weights.
