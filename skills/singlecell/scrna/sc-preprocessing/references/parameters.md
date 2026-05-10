<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--method`
- `--min-genes`
- `--min-cells`
- `--max-mt-pct`
- `--n-top-hvg`
- `--n-pcs`
- `--normalization-target-sum`
- `--scanpy-hvg-flavor`
- `--pearson-hvg-flavor`
- `--pearson-theta`
- `--seurat-normalize-method`
- `--seurat-scale-factor`
- `--seurat-hvg-method`
- `--sctransform-regress-mt`
- `--no-sctransform-regress-mt`
- `--confirmed-preflight`
- `--r-enhanced`

## Per-method parameter hints

### `pearson_residuals`

**Tuning priority:** min_genes/max_mt_pct -> n_top_hvg -> n_pcs

**Core parameters:**

| name | default |
|---|---|
| `min_genes` | `200` |
| `max_mt_pct` | `20.0` |
| `n_top_hvg` | `2000` |
| `n_pcs` | `50` |

**Advanced parameters:**

| name | default |
|---|---|
| `min_cells` | `3` |
| `pearson_hvg_flavor` | `seurat_v3` |
| `pearson_theta` | `100.0` |

**Requires:**
- `raw_counts`
- `scanpy`

**Tips:**
- --method pearson_residuals: raw-count HVG selection plus Pearson residual modeling, while exporting a normalized public matrix and PCA.

### `scanpy`

**Tuning priority:** min_genes/max_mt_pct -> n_top_hvg -> n_pcs

**Core parameters:**

| name | default |
|---|---|
| `min_genes` | `200` |
| `max_mt_pct` | `20.0` |
| `n_top_hvg` | `2000` |
| `n_pcs` | `50` |

**Advanced parameters:**

| name | default |
|---|---|
| `min_cells` | `3` |
| `normalization_target_sum` | `10000.0` |
| `scanpy_hvg_flavor` | `seurat` |

**Requires:**
- `raw_counts`
- `scanpy`

**Tips:**
- --method scanpy: Python-native base preprocessing up to PCA.
- Use `sc-clustering` after this if batch integration is not needed.

### `sctransform`

**Tuning priority:** max_mt_pct -> n_top_hvg -> n_pcs

**Core parameters:**

| name | default |
|---|---|
| `min_genes` | `200` |
| `max_mt_pct` | `20.0` |
| `n_top_hvg` | `3000` |
| `n_pcs` | `50` |

**Advanced parameters:**

| name | default |
|---|---|
| `min_cells` | `3` |
| `sctransform_regress_mt` | `True` |

**Requires:**
- `raw_counts`
- `Rscript`
- `Seurat`
- `SingleCellExperiment`
- `zellkonverter`
- `sctransform`

**Tips:**
- --method sctransform: R-backed SCTransform workflow up to PCA export.

### `seurat`

**Tuning priority:** min_genes/max_mt_pct -> n_top_hvg -> n_pcs

**Core parameters:**

| name | default |
|---|---|
| `min_genes` | `200` |
| `max_mt_pct` | `20.0` |
| `n_top_hvg` | `2000` |
| `n_pcs` | `50` |

**Advanced parameters:**

| name | default |
|---|---|
| `min_cells` | `3` |
| `seurat_normalize_method` | `LogNormalize` |
| `seurat_scale_factor` | `10000.0` |
| `seurat_hvg_method` | `vst` |

**Requires:**
- `raw_counts`
- `Rscript`
- `Seurat`
- `SingleCellExperiment`
- `zellkonverter`

**Tips:**
- --method seurat: R-backed LogNormalize workflow up to PCA export.
