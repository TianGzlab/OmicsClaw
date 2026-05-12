<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--method`
- `--cluster-key`
- `--use-rep`
- `--root-cluster`
- `--root-cell`
- `--end-clusters`
- `--n-neighbors`
- `--n-pcs`
- `--n-dcs`
- `--n-genes`
- `--corr-method`
- `--palantir-knn`
- `--palantir-n-components`
- `--palantir-num-waypoints`
- `--palantir-max-iterations`
- `--palantir-seed`
- `--via-knn`
- `--via-seed`
- `--cellrank-n-states`
- `--cellrank-schur-components`
- `--cellrank-frac-to-keep`
- `--cellrank-use-velocity`
- `--r-enhanced`

## Per-method parameter hints

### `cellrank`

**Tuning priority:** cluster_key -> use_rep -> root_cluster/root_cell -> cellrank_n_states

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `use_rep` | `—` |
| `root_cluster` | `—` |
| `root_cell` | `—` |
| `cellrank_n_states` | `3` |

**Advanced parameters:**

| name | default |
|---|---|
| `cellrank_schur_components` | `20` |
| `cellrank_frac_to_keep` | `0.3` |
| `cellrank_use_velocity` | `False` |
| `n_genes` | `50` |
| `corr_method` | `pearson` |

**Requires:**
- `normalized_expression`
- `cellrank`
- `explicit_root_choice`

### `dpt`

**Tuning priority:** cluster_key -> use_rep -> root_cluster/root_cell

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `use_rep` | `—` |
| `root_cluster` | `—` |
| `root_cell` | `—` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_neighbors` | `15` |
| `n_pcs` | `50` |
| `n_dcs` | `10` |
| `n_genes` | `50` |
| `corr_method` | `pearson` |

**Requires:**
- `normalized_expression`
- `cluster_labels_in_obs`
- `trajectory_representation`

### `monocle3_r`

**Tuning priority:** cluster_key -> use_rep -> root_cluster

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `use_rep` | `—` |
| `root_cluster` | `None` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_genes` | `50` |
| `corr_method` | `pearson` |

**Requires:**
- `normalized_expression`
- `monocle3`
- `SingleCellExperiment`
- `zellkonverter`

### `palantir`

**Tuning priority:** cluster_key -> use_rep -> root_cluster/root_cell

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `use_rep` | `—` |
| `root_cluster` | `—` |
| `root_cell` | `—` |

**Advanced parameters:**

| name | default |
|---|---|
| `palantir_knn` | `30` |
| `palantir_n_components` | `10` |
| `palantir_num_waypoints` | `1200` |
| `palantir_max_iterations` | `25` |
| `palantir_seed` | `20` |
| `n_genes` | `50` |
| `corr_method` | `pearson` |

**Requires:**
- `normalized_expression`
- `palantir`
- `explicit_root_choice`

### `slingshot_r`

**Tuning priority:** cluster_key -> use_rep -> root_cluster -> end_clusters

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `use_rep` | `—` |
| `root_cluster` | `—` |
| `end_clusters` | `None` |

**Advanced parameters:**

| name | default |
|---|---|
| `n_genes` | `50` |
| `corr_method` | `pearson` |

**Requires:**
- `normalized_expression`
- `slingshot`
- `SingleCellExperiment`
- `zellkonverter`
- `explicit_root_choice`

### `via`

**Tuning priority:** cluster_key -> use_rep -> root_cluster/root_cell

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `use_rep` | `—` |
| `root_cluster` | `—` |
| `root_cell` | `—` |

**Advanced parameters:**

| name | default |
|---|---|
| `via_knn` | `30` |
| `via_seed` | `20` |
| `n_genes` | `50` |
| `corr_method` | `pearson` |

**Requires:**
- `normalized_expression`
- `pyVIA`
- `explicit_root_choice`
