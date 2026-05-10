<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--leiden-resolution`
- `--method`
- `--min-cells`
- `--min-peaks`
- `--n-lsi`
- `--n-neighbors`
- `--n-top-peaks`
- `--tfidf-scale-factor`

## Per-method parameter hints

### `tfidf_lsi`

**Tuning priority:** min_peaks/min_cells -> n_top_peaks -> n_lsi/n_neighbors -> leiden_resolution

**Core parameters:**

| name | default |
|---|---|
| `min_peaks` | `200` |
| `min_cells` | `5` |
| `n_top_peaks` | `10000` |
| `tfidf_scale_factor` | `10000.0` |
| `n_lsi` | `30` |
| `n_neighbors` | `15` |
| `leiden_resolution` | `0.8` |

**Requires:**
- `count_like_peak_matrix_in_X`
- `scanpy`
- `sklearn`

**Tips:**
- --min-peaks / --min-cells: Wrapper-level sparsity filters for low-information cells and rarely observed peaks.
- --n-top-peaks: Wrapper-level feature-budget control using globally most accessible peaks after filtering.
- --n-lsi / --n-neighbors / --leiden-resolution: Main structure-learning controls for latent space, graph locality, and clustering granularity.
