<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--batch-key`
- `--method`
- `--n-epochs`
- `--no-gpu`
- `--n-latent`
- `--labels-key`
- `--harmony-theta`
- `--bbknn-neighbors-within-batch`
- `--scanorama-knn`
- `--integration-features`
- `--integration-pcs`
- `--simba-n-top-genes`
- `--simba-n-components`
- `--simba-k`
- `--simba-num-workers`
- `--r-enhanced`

## Per-method parameter hints

### `bbknn`

**Tuning priority:** batch_key

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |

**Advanced parameters:**

| name | default |
|---|---|
| `bbknn_neighbors_within_batch` | `3` |

**Requires:**
- `bbknn`
- `existing_PCA_or_computeable_PCA`

**Tips:**
- --method bbknn: Lightweight graph correction path.

### `fastmnn`

**Tuning priority:** batch_key

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |

**Advanced parameters:**

| name | default |
|---|---|
| `integration_features` | `2000` |
| `integration_pcs` | `30` |

**Requires:**
- `R_batchelor_stack`

**Tips:**
- --method fastmnn: R-backed batchelor fastMNN path via the shared H5AD bridge.

### `harmony`

**Tuning priority:** batch_key

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |

**Advanced parameters:**

| name | default |
|---|---|
| `harmony_theta` | `2.0` |
| `integration_pcs` | `50` |

**Requires:**
- `existing_PCA_or_computeable_PCA`
- `harmonypy`

**Tips:**
- --method harmony: Default integration path in the current wrapper.

### `scanorama`

**Tuning priority:** batch_key

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |

**Advanced parameters:**

| name | default |
|---|---|
| `scanorama_knn` | `20` |

**Requires:**
- `scanorama`

**Tips:**
- --method scanorama: Panorama-stitching integration path.

### `scanvi`

**Tuning priority:** batch_key -> n_epochs -> no_gpu

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |
| `labels_key` | `None` |
| `n_epochs` | `200` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_latent` | `30` |
| `no_gpu` | `False` |

**Requires:**
- `scvi`
- `torch`
- `labels_in_obs`

**Tips:**
- If no labels are available, the current wrapper falls back to `scvi`.

### `scvi`

**Tuning priority:** batch_key -> n_epochs -> no_gpu

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |
| `n_epochs` | `400` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_latent` | `30` |
| `no_gpu` | `False` |

**Requires:**
- `scvi`
- `torch`

**Tips:**
- --n-epochs: Main runtime/optimization knob for scVI.

### `seurat_cca`

**Tuning priority:** batch_key

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |

**Advanced parameters:**

| name | default |
|---|---|
| `integration_features` | `2000` |
| `integration_pcs` | `30` |

**Requires:**
- `R_Seurat_stack`

**Tips:**
- --method seurat_cca: R-backed Seurat CCA integration path via the shared H5AD bridge.

### `seurat_rpca`

**Tuning priority:** batch_key

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |

**Advanced parameters:**

| name | default |
|---|---|
| `integration_features` | `2000` |
| `integration_pcs` | `30` |

**Requires:**
- `R_Seurat_stack`

**Tips:**
- --method seurat_rpca: R-backed Seurat RPCA integration path via the shared H5AD bridge.
