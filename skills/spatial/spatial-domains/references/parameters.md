<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--auto-k`
- `--auto-k-min`
- `--auto-k-max`
- `--data-type`
- `--dim-output`
- `--epochs`
- `--k-nn`
- `--lambda-param`
- `--method`
- `--n-domains`
- `--n-layers`
- `--num-neighbours`
- `--pre-resolution`
- `--rad-cutoff`
- `--refine`
- `--resolution`
- `--spagcn-p`
- `--spatial-weight`
- `--stagate-alpha`
- `--use-rep`

## Per-method parameter hints

### `banksy`

**Tuning priority:** lambda_param → num_neighbours → resolution / n_domains

**Core parameters:**

| name | default |
|---|---|
| `resolution` | `1.0` |
| `lambda_param` | `0.2` |
| `num_neighbours` | `15` |
| `n_domains` | `—` |

**Requires:**
- `obsm.spatial`

**Tips:**
- --lambda-param: 0.2 for cell-typing, 0.8 for domain-finding.
- --num-neighbours: Spatial geometry k_geom (default 15).
- --resolution: Leiden-mode clustering granularity (default 1.0 in the OmicsClaw CLI wrapper).
- --n-domains: Optional exact cluster count target; if omitted, BANKSY falls back to Leiden discovery mode.

### `cellcharter`

**Tuning priority:** n_domains/auto_k → n_layers → use_rep

**Core parameters:**

| name | default |
|---|---|
| `n_domains` | `7` |
| `auto_k` | `False` |
| `n_layers` | `3` |
| `use_rep` | `—` |
| `auto_k_min` | `—` |
| `auto_k_max` | `—` |

**Requires:**
- `obsm.spatial`

**Tips:**
- --n-layers: Number of spatial hops for feature aggregation (default 3).
- --auto-k: Enable automatic discovery of the most stable cluster count. If disabled, fixed-K mode defaults to 7 unless --n-domains is provided.
- --use-rep: Feature representation to use (defaults to X_pca or X).

### `graphst`

**Tuning priority:** data_type → epochs → dim_output → n_domains

**Core parameters:**

| name | default |
|---|---|
| `n_domains` | `7` |
| `epochs` | `100` |
| `dim_output` | `64` |
| `data_type` | `auto` |

**Requires:**
- `obsm.spatial`
- `raw_or_counts`

**Tips:**
- --data-type: Platform hint for GraphST routing (visium, slide_seq, stereo). Auto-inferred from metadata/path when omitted.
- --epochs: Default ~600 in official code. Lower to 50-100 for large datasets (>30k spots).
- --dim-output: Embedding dimension (default 64). Increase for complex tissues.
- --n-domains: Target cluster count.

### `leiden`

**Tuning priority:** resolution → spatial_weight

**Core parameters:**

| name | default |
|---|---|
| `resolution` | `1.0` |
| `spatial_weight` | `0.3` |

**Requires:**
- `obsm.spatial`

**Tips:**
- --resolution: Clustering granularity (default 1.0).
- --spatial-weight: Spatial graph influence (default 0.3).

### `louvain`

**Tuning priority:** resolution → spatial_weight

**Core parameters:**

| name | default |
|---|---|
| `resolution` | `1.0` |
| `spatial_weight` | `0.3` |

**Requires:**
- `obsm.spatial`

**Tips:**
- --resolution: Clustering granularity (default 1.0).
- --spatial-weight: Spatial graph influence (default 0.3).

### `spagcn`

**Tuning priority:** spagcn_p → n_domains → epochs

**Core parameters:**

| name | default |
|---|---|
| `n_domains` | `7` |
| `epochs` | `100` |
| `spagcn_p` | `0.5` |

**Requires:**
- `obsm.spatial`

**Tips:**
- --spagcn-p: Spatial neighborhood contribution (default 0.5).
- --n-domains: Target cluster count.
- --epochs: Training loops (default 100 in the OmicsClaw CLI wrapper).

### `stagate`

**Tuning priority:** rad_cutoff/k_nn → stagate_alpha → epochs

**Core parameters:**

| name | default |
|---|---|
| `n_domains` | `7` |
| `epochs` | `100` |
| `k_nn` | `6` |
| `rad_cutoff` | `—` |
| `stagate_alpha` | `0.0` |
| `pre_resolution` | `0.2` |

**Requires:**
- `obsm.spatial`

**Tips:**
- --rad-cutoff / --k-nn: Spatial network. Varies by platform (Visium~150, Slide-seq~50).
- --stagate-alpha: Cell type-aware module weight (0=disabled).
- --epochs: Training epochs (default 100 in the OmicsClaw CLI wrapper).
