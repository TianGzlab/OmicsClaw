<!-- Hand-written. `skill.yaml` and its generators were deleted with the old skill system. -->


# Parameters

## Allowed extra CLI flags

- `--batch-key`
- `--cluster-method`
- `--method`
- `--n-neighbors`
- `--n-pcs`
- `--n-top-genes`
- `--resolution`
- `--seed`

## Per-method parameter hints

### `default`

**Tuning priority:** method -> batch_key -> resolution

**Core parameters:**

| name | default |
|---|---|
| `method` | `none` |
| `batch_key` | `batch` |
| `resolution` | `1.0` |

**Advanced parameters:**

| name | default |
|---|---|
| `cluster_method` | `leiden` |
| `n_neighbors` | `15` |
| `n_pcs` | `50` |

**Requires:**
- `normalized_expression`
- `batch_key`

**Tips:**
- A consensus member: `--method` selects the batch-correction backend; `none` is the unintegrated X_pca baseline.
- scVI is GPU/stochastic — include it only when reproducible-within-tolerance is acceptable, and serialise GPU members.
