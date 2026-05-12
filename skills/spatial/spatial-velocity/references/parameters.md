<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--cluster-key`
- `--dynamical-fit-scaling`
- `--dynamical-fit-steady-states`
- `--dynamical-fit-time`
- `--dynamical-max-iter`
- `--dynamical-n-jobs`
- `--dynamical-n-top-genes`
- `--method`
- `--no-dynamical-fit-scaling`
- `--no-dynamical-fit-steady-states`
- `--no-dynamical-fit-time`
- `--no-velocity-fit-offset`
- `--no-velocity-fit-offset2`
- `--no-velocity-graph-approx`
- `--no-velocity-graph-sqrt-transform`
- `--no-velocity-use-highly-variable`
- `--no-velovi-early-stopping`
- `--velocity-fit-offset`
- `--velocity-fit-offset2`
- `--velocity-graph-approx`
- `--velocity-graph-n-neighbors`
- `--velocity-graph-sqrt-transform`
- `--velocity-min-likelihood`
- `--velocity-min-r2`
- `--velocity-min-shared-counts`
- `--velocity-n-neighbors`
- `--velocity-n-pcs`
- `--velocity-n-top-genes`
- `--velocity-use-highly-variable`
- `--velovi-batch-size`
- `--velovi-dropout-rate`
- `--velovi-early-stopping`
- `--velovi-lr`
- `--velovi-max-epochs`
- `--velovi-n-hidden`
- `--velovi-n-latent`
- `--velovi-n-layers`
- `--velovi-n-samples`
- `--velovi-weight-decay`

## Per-method parameter hints

### `deterministic`

**Tuning priority:** velocity_n_neighbors/n_pcs → velocity_fit_offset/min_r2 → velocity_graph_*

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `velocity_min_shared_counts` | `30` |
| `velocity_n_top_genes` | `2000` |
| `velocity_n_pcs` | `30` |
| `velocity_n_neighbors` | `30` |
| `velocity_use_highly_variable` | `True` |
| `velocity_fit_offset` | `False` |
| `velocity_fit_offset2` | `False` |
| `velocity_min_r2` | `0.01` |
| `velocity_min_likelihood` | `0.001` |
| `velocity_graph_n_neighbors` | `None` |
| `velocity_graph_sqrt_transform` | `None` |
| `velocity_graph_approx` | `None` |

**Requires:**
- `layers.spliced`
- `layers.unspliced`

**Tips:**
- `deterministic` uses the same scVelo engine as `stochastic` but switches to `mode='deterministic'`.
- The shared `velocity_*` preprocessing settings are wrapper-level controls around the official scVelo preprocessing recipe and materially affect the result.

### `dynamical`

**Tuning priority:** dynamical_n_top_genes/max_iter → velocity_min_r2/min_likelihood → velocity_graph_*

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `velocity_min_shared_counts` | `30` |
| `velocity_n_top_genes` | `2000` |
| `velocity_n_pcs` | `30` |
| `velocity_n_neighbors` | `30` |
| `velocity_use_highly_variable` | `True` |
| `velocity_min_r2` | `0.01` |
| `velocity_min_likelihood` | `0.001` |
| `dynamical_n_top_genes` | `None` |
| `dynamical_max_iter` | `10` |
| `dynamical_fit_time` | `True` |
| `dynamical_fit_scaling` | `True` |
| `dynamical_fit_steady_states` | `True` |
| `dynamical_n_jobs` | `None` |
| `velocity_graph_n_neighbors` | `None` |
| `velocity_graph_sqrt_transform` | `None` |
| `velocity_graph_approx` | `None` |

**Requires:**
- `layers.spliced`
- `layers.unspliced`

**Tips:**
- --dynamical-n-top-genes / --dynamical-max-iter / --dynamical-fit-time / --dynamical-fit-scaling / --dynamical-fit-steady-states / --dynamical-n-jobs: official `scv.tl.recover_dynamics()` controls.
- `dynamical` additionally exports latent-time support when `scv.tl.latent_time()` succeeds.

### `stochastic`

**Tuning priority:** velocity_n_neighbors/n_pcs → velocity_fit_offset/min_r2 → velocity_graph_*

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `velocity_min_shared_counts` | `30` |
| `velocity_n_top_genes` | `2000` |
| `velocity_n_pcs` | `30` |
| `velocity_n_neighbors` | `30` |
| `velocity_use_highly_variable` | `True` |
| `velocity_fit_offset` | `False` |
| `velocity_fit_offset2` | `False` |
| `velocity_min_r2` | `0.01` |
| `velocity_min_likelihood` | `0.001` |
| `velocity_graph_n_neighbors` | `None` |
| `velocity_graph_sqrt_transform` | `None` |
| `velocity_graph_approx` | `None` |

**Requires:**
- `layers.spliced`
- `layers.unspliced`

**Tips:**
- `stochastic` uses official `scv.tl.velocity(mode='stochastic')` after OmicsClaw rebuilds moments with the requested preprocessing controls.
- --velocity-fit-offset / --velocity-fit-offset2 / --velocity-min-r2 / --velocity-min-likelihood: official `scv.tl.velocity()` controls.
- --velocity-graph-n-neighbors / --velocity-graph-sqrt-transform / --velocity-graph-approx: official `scv.tl.velocity_graph()` controls.

### `velovi`

**Tuning priority:** velovi_max_epochs/n_samples → velovi_n_hidden/n_latent/n_layers → velocity_graph_*

**Core parameters:**

| name | default |
|---|---|
| `cluster_key` | `leiden` |
| `velocity_min_shared_counts` | `30` |
| `velocity_n_top_genes` | `2000` |
| `velocity_n_pcs` | `30` |
| `velocity_n_neighbors` | `30` |
| `velocity_use_highly_variable` | `True` |
| `velovi_n_hidden` | `256` |
| `velovi_n_latent` | `10` |
| `velovi_n_layers` | `1` |
| `velovi_dropout_rate` | `0.1` |
| `velovi_max_epochs` | `500` |
| `velovi_lr` | `0.01` |
| `velovi_weight_decay` | `0.01` |
| `velovi_batch_size` | `256` |
| `velovi_n_samples` | `25` |
| `velovi_early_stopping` | `True` |
| `velocity_graph_n_neighbors` | `None` |
| `velocity_graph_sqrt_transform` | `None` |
| `velocity_graph_approx` | `None` |

**Requires:**
- `layers.spliced`
- `layers.unspliced`
- `scvi_tools`

**Tips:**
- OmicsClaw still runs shared scVelo preprocessing first because VELOVI consumes moment-smoothed `Ms` / `Mu` layers.
- --velovi-n-hidden / --velovi-n-latent / --velovi-n-layers / --velovi-dropout-rate: official `scvi.external.VELOVI(...)` model controls.
- --velovi-max-epochs / --velovi-lr / --velovi-weight-decay / --velovi-batch-size / --velovi-early-stopping: official `VELOVI.train()` controls.
- --velovi-n-samples: official posterior-sampling control for `get_velocity()` and `get_latent_time()` extraction.
