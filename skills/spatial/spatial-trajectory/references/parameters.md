<!-- Hand-written. `skill.yaml` and its generators were deleted with the old skill system. -->


# Parameters

## Allowed extra CLI flags

- `--cellrank-frac-to-keep`
- `--cellrank-n-states`
- `--cellrank-schur-components`
- `--cellrank-use-velocity`
- `--cluster-key`
- `--dpt-n-dcs`
- `--method`
- `--palantir-knn`
- `--palantir-max-iterations`
- `--palantir-n-components`
- `--palantir-num-waypoints`
- `--root-cell`
- `--root-cell-type`

## Per-method parameter hints

### `cellrank`

**Tuning priority:** cluster_key/root_cell/root_cell_type → cellrank_use_velocity → cellrank_n_states → cellrank_schur_components → cellrank_frac_to_keep

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `auto` |
| `root_cell` | `None` |
| `root_cell_type` | `None` |
| `dpt_n_dcs` | `10` |
| `cellrank_use_velocity` | `False` |
| `cellrank_n_states` | `3` |
| `cellrank_schur_components` | `20` |
| `cellrank_frac_to_keep` | `0.3` |

**Requires:**
- `obsm.X_pca`
- `uns.neighbors`
- `cellrank`

**Tips:**
- --cellrank-use-velocity: current OmicsClaw wrapper-level preference for `VelocityKernel`; if velocity is unavailable the wrapper falls back to pseudotime/connectivity or connectivity only and reports the actual kernel mode.
- --cellrank-n-states: public `GPCCA.compute_macrostates(n_states=...)` control.
- --cellrank-schur-components: public `GPCCA.compute_schur(n_components=...)` control.
- --cellrank-frac-to-keep: public `PseudotimeKernel.compute_transition_matrix(frac_to_keep=...)` control when the pseudotime kernel path is used.

### `dpt`

**Tuning priority:** cluster_key/root_cell/root_cell_type → dpt_n_dcs

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `auto` |
| `root_cell` | `None` |
| `root_cell_type` | `None` |
| `dpt_n_dcs` | `10` |

**Requires:**
- `obsm.X_pca`
- `uns.neighbors`

**Tips:**
- --cluster-key: wrapper control used for root-cell-type selection and per-cluster pseudotime summaries; current OmicsClaw auto-detects common cluster columns if omitted.
- --root-cell: exact barcode wrapper control; overrides automatic root selection.
- --root-cell-type: wrapper control that selects the root from a specified annotation group.
- --dpt-n-dcs: public `scanpy.tl.dpt` parameter controlling how many diffusion components enter pseudotime.

### `palantir`

**Tuning priority:** cluster_key/root_cell/root_cell_type → palantir_knn → palantir_num_waypoints → palantir_n_components → palantir_max_iterations

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `auto` |
| `root_cell` | `None` |
| `root_cell_type` | `None` |
| `palantir_n_components` | `10` |
| `palantir_knn` | `30` |
| `palantir_num_waypoints` | `1200` |
| `palantir_max_iterations` | `25` |

**Requires:**
- `obsm.X_pca`
- `uns.neighbors`
- `palantir`

**Tips:**
- --palantir-n-components / --palantir-knn: public `scanpy.external.tl.palantir(...)` controls for diffusion-space construction.
- --palantir-num-waypoints / --palantir-max-iterations: public `scanpy.external.tl.palantir_results(...)` controls for waypoint sampling and pseudotime refinement.
- Current OmicsClaw stores Palantir pseudotime and entropy back into AnnData instead of pretending the Scanpy wrapper writes them automatically.
