<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--batch-key`
- `--method`
- `--harmony-theta`
- `--harmony-lambda`
- `--harmony-max-iter`
- `--bbknn-neighbors-within-batch`
- `--bbknn-n-pcs`
- `--bbknn-trim`
- `--scanorama-knn`
- `--scanorama-sigma`
- `--scanorama-alpha`
- `--scanorama-batch-size`

## Per-method parameter hints

### `bbknn`

**Tuning priority:** bbknn_neighbors_within_batch → bbknn_n_pcs → bbknn_trim

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |
| `bbknn_neighbors_within_batch` | `3` |
| `bbknn_n_pcs` | `50` |
| `bbknn_trim` | `None` |

**Requires:**
- `obsm.X_pca`
- `obs.batch_key`

**Tips:**
- --bbknn-neighbors-within-batch: Main integration knob controlling how many neighbors BBKNN draws from each batch.
- --bbknn-n-pcs: Number of PCs used to build the batch-balanced graph; OmicsClaw clamps it to the PCs actually available in `X_pca`.
- --bbknn-trim: Optional edge trimming after graph construction; leave unset to keep the package default.

### `harmony`

**Tuning priority:** harmony_theta → harmony_lambda → harmony_max_iter

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |
| `harmony_theta` | `2.0` |
| `harmony_lambda` | `1.0` |
| `harmony_max_iter` | `10` |

**Requires:**
- `obsm.X_pca`
- `obs.batch_key`

**Tips:**
- --harmony-theta: Diversity penalty; raise it to encourage stronger batch mixing.
- --harmony-lambda: Ridge penalty; smaller values increase correction strength, while `-1` enables Harmony auto-lambda estimation.
- --harmony-max-iter: Maximum Harmony outer iterations before convergence.

### `scanorama`

**Tuning priority:** scanorama_knn → scanorama_sigma → scanorama_alpha → scanorama_batch_size

**Core parameters:**

| name | default |
|---|---|
| `batch_key` | `batch` |
| `scanorama_knn` | `20` |
| `scanorama_sigma` | `15.0` |
| `scanorama_alpha` | `0.1` |
| `scanorama_batch_size` | `5000` |

**Requires:**
- `obsm.X_pca`
- `obs.batch_key`

**Tips:**
- --scanorama-knn: Number of nearest neighbors used while matching batches.
- --scanorama-sigma: Gaussian kernel width for smoothing Scanorama correction vectors.
- --scanorama-alpha: Alignment-score cutoff controlling which batch matches are accepted.
- --scanorama-batch-size: Incremental alignment batch size for large datasets.
