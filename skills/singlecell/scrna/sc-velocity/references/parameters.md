<!-- AUTO-GENERATED from parameters.yaml — do not edit by hand. -->
<!-- Regenerate: python scripts/generate_parameters_md.py <skill_dir> -->


# Parameters

## Allowed extra CLI flags

- `--method`
- `--mode`
- `--n-jobs`
- `--r-enhanced`

## Per-method parameter hints

### `scvelo_dynamical`

**Tuning priority:** n_jobs

**Core parameters:**

| name | default |
|---|---|
| `n_jobs` | `4` |

**Requires:**
- `scvelo`
- `layers.spliced`
- `layers.unspliced`

**Tips:**
- --method scvelo_dynamical or --mode dynamical: computes latent time when the fit succeeds.

### `scvelo_steady_state`

**Tuning priority:** n_jobs

**Core parameters:**

| name | default |
|---|---|
| `n_jobs` | `4` |

**Requires:**
- `scvelo`
- `layers.spliced`
- `layers.unspliced`

**Tips:**
- --method scvelo_steady_state or --mode steady_state: steady-state approximation path.

### `scvelo_stochastic`

**Tuning priority:** n_jobs

**Core parameters:**

| name | default |
|---|---|
| `n_jobs` | `4` |

**Requires:**
- `scvelo`
- `layers.spliced`
- `layers.unspliced`

**Tips:**
- --method scvelo_stochastic or --mode stochastic: default velocity path.
